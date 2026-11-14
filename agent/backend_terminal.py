from __future__ import annotations

import asyncio
import os
import platform
from pathlib import Path
import signal
import struct
from dataclasses import dataclass
from typing import Any


@dataclass
class TerminalSession:
    process: Any
    reader_task: asyncio.Task
    closing: bool = False


class BackendTerminalManager:
    def __init__(self, send_message):
        self.send_message = send_message
        self.sessions: dict[str, TerminalSession] = {}
        self.lock = asyncio.Lock()

    async def open(self, session_id: str):
        if not session_id:
            return

        async with self.lock:
            if session_id in self.sessions:
                return

            if platform.system().lower() == "windows":
                from winpty import PtyProcess

                process = PtyProcess.spawn(
                    "powershell.exe",
                    dimensions=(30, 100),
                )
            else:
                import fcntl
                import pty
                import termios

                master_fd, slave_fd = pty.openpty()

                try:
                    fcntl.ioctl(
                        slave_fd,
                        termios.TIOCSWINSZ,
                        struct.pack("HHHH", 30, 100, 0, 0),
                    )

                    shell = os.getenv("SHELL") or "/bin/bash"

                    process = await asyncio.create_subprocess_exec(
                        shell,
                        "-l",
                        "-i",
                        stdin=slave_fd,
                        stdout=slave_fd,
                        stderr=slave_fd,
                        start_new_session=True,
                        env={**os.environ, "TERM": "xterm-256color"},
                    )
                except BaseException:
                    os.close(master_fd)
                    raise
                finally:
                    os.close(slave_fd)

                process.master_fd = master_fd

            reader_task = asyncio.create_task(
                self._read_output(session_id, process)
            )

            self.sessions[session_id] = TerminalSession(
                process=process,
                reader_task=reader_task,
            )

    async def _read_fd(self, fd: int) -> bytes:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def readable():
            if future.done():
                return

            try:
                data = os.read(fd, 4096)
            except OSError as exc:
                future.set_exception(exc)
            else:
                future.set_result(data)

        loop.add_reader(fd, readable)

        try:
            return await future
        finally:
            loop.remove_reader(fd)

    async def _read_output(self, session_id: str, process: Any):
        try:
            while True:
                if platform.system().lower() == "windows":
                    if not process.isalive():
                        break

                    data = await asyncio.to_thread(process.read, 4096)

                    if not data:
                        await asyncio.sleep(0.02)
                        continue
                else:
                    data = await self._read_fd(process.master_fd)

                    if not data:
                        break

                if isinstance(data, bytes):
                    data = data.decode(errors="replace")

                await self.send_message({
                    "type": "terminal.output",
                    "session_id": session_id,
                    "data": data,
                })

        except (EOFError, OSError, asyncio.CancelledError):
            pass
        finally:
            notify_closed = False
            removed_naturally = False

            async with self.lock:
                session = self.sessions.get(session_id)

                if session and session.process is process:
                    notify_closed = not session.closing
                    session.closing = True
                    self.sessions.pop(session_id, None)
                    removed_naturally = True

            if (
                removed_naturally
                and platform.system().lower() != "windows"
            ):
                try:
                    os.close(process.master_fd)
                except OSError:
                    pass

            if notify_closed:
                try:
                    await self.send_message({
                        "type": "terminal.closed",
                        "session_id": session_id,
                    })
                except Exception:
                    pass

            if platform.system().lower() != "windows":
                try:
                    await process.wait()
                except Exception:
                    pass

    async def input(self, session_id: str, data: str):
        session = self.sessions.get(session_id)

        if not session or session.closing:
            return

        if platform.system().lower() == "windows":
            await asyncio.to_thread(session.process.write, data)
        else:
            await asyncio.to_thread(
                os.write,
                session.process.master_fd,
                data.encode(),
            )

    async def resize(self, session_id: str, rows: int, cols: int):
        session = self.sessions.get(session_id)

        if not session or session.closing:
            return

        rows = max(5, min(int(rows), 100))
        cols = max(20, min(int(cols), 300))

        if platform.system().lower() == "windows":
            try:
                session.process.setwinsize(rows, cols)
            except Exception:
                pass
        else:
            import fcntl
            import termios

            fcntl.ioctl(
                session.process.master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )

    @staticmethod
    def _process_groups_in_session(session_id: int) -> set[int]:
        groups = set()

        for stat_file in Path("/proc").glob("[0-9]*/stat"):
            try:
                stat = stat_file.read_text()
                fields = stat[stat.rfind(")") + 2:].split()

                state = fields[0]
                process_group = int(fields[2])
                process_session = int(fields[3])

                if process_session == session_id and state != "Z":
                    groups.add(process_group)
            except (OSError, ValueError, IndexError):
                continue

        return groups

    async def _terminate_session_processes(self, session_id: int):
        def signal_groups(sig):
            for group_id in self._process_groups_in_session(session_id):
                try:
                    os.killpg(group_id, sig)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    pass

        signal_groups(signal.SIGTERM)

        deadline = asyncio.get_running_loop().time() + 3

        while (
            self._process_groups_in_session(session_id)
            and asyncio.get_running_loop().time() < deadline
        ):
            await asyncio.sleep(0.1)

        signal_groups(signal.SIGKILL)

    async def close(self, session_id: str):
        async with self.lock:
            session = self.sessions.get(session_id)

            if session:
                session.closing = True
                self.sessions.pop(session_id, None)

        if not session:
            return

        process = session.process

        if platform.system().lower() == "windows":
            try:
                if process.isalive():
                    await asyncio.to_thread(process.terminate)
            except Exception:
                pass

            try:
                await asyncio.wait_for(
                    asyncio.shield(session.reader_task),
                    timeout=2,
                )
            except (asyncio.TimeoutError, Exception):
                session.reader_task.cancel()
                await asyncio.gather(
                    session.reader_task,
                    return_exceptions=True,
                )

        else:
            master_fd = process.master_fd

            await self._terminate_session_processes(process.pid)

            if process.returncode is None:
                await process.wait()

            session.reader_task.cancel()
            await asyncio.gather(
                session.reader_task,
                return_exceptions=True,
            )

            try:
                os.close(master_fd)
            except OSError:
                pass

    async def close_all(self):
        for session_id in list(self.sessions):
            await self.close(session_id)
