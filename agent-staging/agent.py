from __future__ import annotations

from dotenv import load_dotenv

import asyncio
import json
import os
import platform
import secrets
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from pydantic import BaseModel, Field
import httpx
from urllib.parse import urlsplit, urlunsplit
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from websockets.asyncio.client import connect
from contextlib import asynccontextmanager
from backend_connection import run_backend_connection

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
TOKEN_FILE = BASE_DIR / "agent-token.txt"
DEVICE_TOKEN_FILE = BASE_DIR / "device-token.txt"
HOST = "127.0.0.1"
PORT = 8766
BACKEND_WS_URL = os.getenv("DEVOPS_BACKEND_WS", "").strip()
DEVICE_TOKEN = os.getenv("DEVOPS_AGENT_TOKEN", "").strip()

def load_device_token() -> str:
    if DEVICE_TOKEN_FILE.exists():
        token = DEVICE_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    return DEVICE_TOKEN

def save_device_token(token: str) -> None:
    temporary_file = DEVICE_TOKEN_FILE.with_suffix(".tmp")
    temporary_file.write_text(token, encoding="utf-8")
    try:
        temporary_file.chmod(0o600)
    except OSError:
        pass
    temporary_file.replace(DEVICE_TOKEN_FILE)
HEARTBEAT_SECONDS = int(os.getenv("DEVOPS_HEARTBEAT_SECONDS", "25"))

def get_token() -> str:
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
} | {"https://devopsadi.com"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.connection_task = None
    app.state.pair_lock = asyncio.Lock()

    device_token = load_device_token()
    if BACKEND_WS_URL and device_token:
        app.state.connection_task = asyncio.create_task(
            run_backend_connection(
                BACKEND_WS_URL,
                device_token,
                HEARTBEAT_SECONDS,
            )
        )
        print("ADRI AI backend connection starting...")
    else:
        print("ADRI AI backend connection not configured yet.")

    yield

    if app.state.connection_task:
        app.state.connection_task.cancel()
        await asyncio.gather(
            app.state.connection_task,
            return_exceptions=True,
        )


app = FastAPI(
    title="DevOps AI Local Agent",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
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


class PairRequest(BaseModel):
    code: str = Field(
        min_length=32,
        max_length=32,
        pattern=r"^[A-Fa-f0-9]{32}$",
    )


@app.post("/pair")
async def pair_agent(data: PairRequest, request: Request):
    origin = request.headers.get("origin", "")
    if origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    if not BACKEND_WS_URL:
        raise HTTPException(
            status_code=503,
            detail="Backend WebSocket URL is not configured",
        )

    parsed = urlsplit(BACKEND_WS_URL)
    if parsed.scheme not in ("ws", "wss") or not parsed.path.endswith("/agent/connect"):
        raise HTTPException(
            status_code=500,
            detail="Backend WebSocket URL has an unexpected format",
        )

    claim_scheme = "https" if parsed.scheme == "wss" else "http"
    claim_path = parsed.path[:-len("/agent/connect")] + "/claim"
    claim_url = urlunsplit(
        (claim_scheme, parsed.netloc, claim_path, "", "")
    )

    async with request.app.state.pair_lock:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    claim_url,
                    json={
                        "code": data.code.upper(),
                        "device_name": platform.node() or "ADRI AI Agent",
                        "operating_system": platform.system(),
                    },
                )
                response.raise_for_status()
                result = response.json()

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (400, 429):
                detail = (
                    "Pairing code is invalid, expired, or already used."
                    if status == 400
                    else "Too many pairing attempts. Please wait and try again."
                )
                raise HTTPException(status_code=status, detail=detail)
            raise HTTPException(
                status_code=502,
                detail="The backend could not complete device pairing.",
            )
        except (httpx.RequestError, ValueError):
            raise HTTPException(
                status_code=502,
                detail="Could not reach the ADRI AI backend.",
            )

        if not isinstance(result, dict):
            raise HTTPException(
                status_code=502,
                detail="Backend returned an invalid pairing response.",
            )

        device_token = result.get("device_token")
        device_id = result.get("device_id")

        if not isinstance(device_token, str) or not device_token:
            raise HTTPException(
                status_code=502,
                detail="Backend returned an invalid device credential.",
            )

        try:
            save_device_token(device_token)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="Could not securely save the device credential.",
            )

        old_task = request.app.state.connection_task
        if old_task and not old_task.done():
            old_task.cancel()
            await asyncio.gather(old_task, return_exceptions=True)

        request.app.state.connection_task = asyncio.create_task(
            run_backend_connection(
                BACKEND_WS_URL,
                device_token,
                HEARTBEAT_SECONDS,
            )
        )

    return {
        "success": True,
        "device_id": device_id,
        "message": "Device paired. Backend connection is starting.",
    }

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
    print("Local terminal authentication: enabled.")
    print("Terminal mode: interactive PTY. Keep this window open.\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
