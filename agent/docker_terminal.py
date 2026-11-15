from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from docker_workspace import DockerWorkspaceManager

logger = logging.getLogger("adri.docker_terminal")


@dataclass
class DockerTerminalSession:
    user_id: int
    workspace_id: int
    exec_id: str
    socket: Any
    reader_task: asyncio.Task | None = None
    closing: bool = False


class DockerTerminalManager:
    def __init__(self, docker_manager: DockerWorkspaceManager, send_message):
        self.docker_manager = docker_manager
        self.send_message = send_message
        self.sessions: dict[str, DockerTerminalSession] = {}
        self.lock = asyncio.Lock()

    async def open(
        self,
        session_id: str,
        user_id: int,
        workspace_id: int,
        rows: int = 30,
        cols: int = 100,
    ):
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
            raise ValueError("Invalid terminal session ID")

        if type(user_id) is not int or user_id < 1:
            raise ValueError("Invalid user ID")

        if type(workspace_id) is not int or workspace_id < 1:
            raise ValueError("Invalid workspace ID")

        rows = max(5, min(int(rows), 100))
        cols = max(20, min(int(cols), 300))

        async with self.lock:
            if session_id in self.sessions:
                return

            container = await asyncio.to_thread(
                self.docker_manager._get_owned_container,
                user_id,
                workspace_id,
            )

            if container is None:
                raise RuntimeError("Workspace container not found")

            if container.status != "running":
                raise RuntimeError("Workspace is not running")

            exec_data = await asyncio.to_thread(
                self.docker_manager.client.api.exec_create,
                container.id,
                cmd=["/bin/bash", "--login"],
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True,
                user="devops",
                workdir="/home/devops/workspace",
            )

            exec_id = exec_data["Id"]

            await asyncio.to_thread(
                self.docker_manager.client.api.exec_resize,
                exec_id,
                height=rows,
                width=cols,
            )

            docker_socket = await asyncio.to_thread(
                self.docker_manager.client.api.exec_start,
                exec_id,
                detach=False,
                tty=True,
                socket=True,
            )

            session = DockerTerminalSession(
                user_id=user_id,
                workspace_id=workspace_id,
                exec_id=exec_id,
                socket=docker_socket,
            )

            self.sessions[session_id] = session
            session.reader_task = asyncio.create_task(
                self._read_output(session_id, session)
            )

    async def _read_output(
        self,
        session_id: str,
        session: DockerTerminalSession,
    ):
        try:
            while not session.closing:
                data = await asyncio.to_thread(
                    session.socket.recv,
                    4096,
                )

                if not data:
                    break

                await self.send_message({
                    "type": "workspace.terminal.output",
                    "session_id": session_id,
                    "data": data.decode("utf-8", errors="replace"),
                })

        except (OSError, EOFError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Docker terminal output failed (session=%s)",
                session_id,
            )
        finally:
            notify_closed = False

            async with self.lock:
                current = self.sessions.get(session_id)

                if current is session:
                    self.sessions.pop(session_id, None)
                    notify_closed = not session.closing
                    session.closing = True

            try:
                session.socket.close()
            except Exception:
                pass

            if notify_closed:
                try:
                    await self.send_message({
                        "type": "workspace.terminal.closed",
                        "session_id": session_id,
                    })
                except Exception:
                    pass

    async def input(self, session_id: str, data: str):
        if not isinstance(data, str) or len(data) > 8192:
            raise ValueError("Invalid terminal input")

        session = self.sessions.get(session_id)

        if not session or session.closing:
            return

        await asyncio.to_thread(
            session.socket.sendall,
            data.encode("utf-8"),
        )

    async def resize(self, session_id: str, rows: int, cols: int):
        session = self.sessions.get(session_id)

        if not session or session.closing:
            return

        rows = max(5, min(int(rows), 100))
        cols = max(20, min(int(cols), 300))

        await asyncio.to_thread(
            self.docker_manager.client.api.exec_resize,
            session.exec_id,
            height=rows,
            width=cols,
        )

    async def close(self, session_id: str):
        async with self.lock:
            session = self.sessions.pop(session_id, None)

            if session:
                session.closing = True

        if not session:
            return

        try:
            session.socket.close()
        except Exception:
            pass

        if session.reader_task:
            try:
                await asyncio.wait_for(
                    asyncio.shield(session.reader_task),
                    timeout=3,
                )
            except asyncio.TimeoutError:
                session.reader_task.cancel()
                await asyncio.gather(
                    session.reader_task,
                    return_exceptions=True,
                )

    async def close_all(self):
        for session_id in list(self.sessions):
            await self.close(session_id)
