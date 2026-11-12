from __future__ import annotations

import asyncio
import os
import platform
import secrets
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "agent-token.txt"
HOST = "127.0.0.1"
PORT = 8765

def get_token() -> str:
    token = os.getenv("DEVOPS_AGENT_TOKEN")
    if token:
        return token.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return token

TOKEN = get_token()
ALLOWED_ORIGINS = {
    value.strip()
    for value in os.getenv(
        "DEVOPS_AGENT_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"
    ).split(",")
    if value.strip()
}

app = FastAPI(title="DevOps AI Local Agent", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/health")
async def health():
    return {
        "status": "online",
        "agent": "devops-ai-local-agent",
        "version": "0.2.0",
        "os": platform.platform(),
        "machine": platform.machine(),
        "terminal": "pty",
    }

@app.get("/")
async def root():
    return {"service": "DevOps AI Local Agent", "health": "/health", "terminal": "/terminal/ws"}

def windows_shell():
    if platform.system().lower() == "windows":
        return "powershell.exe"
    if sys.platform == "darwin":
        return os.getenv("SHELL") or "/bin/zsh"
    return os.getenv("SHELL") or "/bin/bash"

async def run_windows_terminal(ws: WebSocket):
    # pywinpty provides a real Windows ConPTY/PTY-backed interactive shell.
    from winpty import PtyProcess

    proc = PtyProcess.spawn(windows_shell(), dimensions=(30, 100))

    async def read_output():
        while proc.isalive():
            try:
                data = await asyncio.to_thread(proc.read, 4096)
                if data:
                    await ws.send_text(data)
                else:
                    await asyncio.sleep(0.02)
            except EOFError:
                break
            except Exception:
                if not proc.isalive():
                    break
                await asyncio.sleep(0.02)

    reader = asyncio.create_task(read_output())
    try:
        while proc.isalive():
            message = await ws.receive_json()
            kind = message.get("type")
            if kind == "input":
                proc.write(str(message.get("data", "")))
            elif kind == "resize":
                rows = max(5, min(int(message.get("rows", 30)), 100))
                cols = max(20, min(int(message.get("cols", 100)), 300))
                try:
                    proc.setwinsize(rows, cols)
                except Exception:
                    pass
            elif kind == "close":
                break
    finally:
        if proc.isalive():
            proc.terminate()
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)

async def run_posix_terminal(ws: WebSocket):
    import fcntl
    import pty
    import struct
    import termios

    master_fd, slave_fd = pty.openpty()
    rows, cols = 30, 100
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    shell = windows_shell()
    proc = await asyncio.create_subprocess_exec(
        shell, "-l", "-i",
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        start_new_session=True,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    os.close(slave_fd)
    loop = asyncio.get_running_loop()

    async def read_output():
        while True:
            try:
                data = await asyncio.to_thread(os.read, master_fd, 4096)
                if not data:
                    break
                await ws.send_text(data.decode(errors="replace"))
            except OSError:
                break

    reader = asyncio.create_task(read_output())
    try:
        while proc.returncode is None:
            message = await ws.receive_json()
            kind = message.get("type")
            if kind == "input":
                data = str(message.get("data", "")).encode()
                await asyncio.to_thread(os.write, master_fd, data)
            elif kind == "resize":
                rows = max(5, min(int(message.get("rows", 30)), 100))
                cols = max(20, min(int(message.get("cols", 100)), 300))
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            elif kind == "close":
                break
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        os.close(master_fd)

@app.websocket("/terminal/ws")
async def terminal_ws(ws: WebSocket):
    origin = ws.headers.get("origin", "")
    token = ws.query_params.get("token", "")
    if origin not in ALLOWED_ORIGINS or not secrets.compare_digest(token, TOKEN):
        await ws.close(code=1008, reason="Origin or pairing token rejected")
        return

    await ws.accept()
    await ws.send_json({
        "type": "connected",
        "os": platform.system(),
        "machine": platform.node(),
        "shell": windows_shell(),
    })
    try:
        if platform.system().lower() == "windows":
            await run_windows_terminal(ws)
        else:
            await run_posix_terminal(ws)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass

if __name__ == "__main__":
    print(f"\nDevOps AI Local Agent listening on http://{HOST}:{PORT}")
    print(f"Pairing token: {TOKEN}")
    print("Terminal mode: interactive PTY. Keep this window open.\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
