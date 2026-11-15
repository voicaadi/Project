import asyncio
import hashlib
from collections import defaultdict
from dataclasses import dataclass

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.database.models import UserDevice


@dataclass
class PendingWorkspaceRequest:
    device_id: int
    future: asyncio.Future


class DeviceConnectionManager:
    def __init__(self):
        self.connections: dict[int, WebSocket] = {}
        self.sessions: dict[str, tuple[int, WebSocket]] = {}
        self.device_sessions: dict[int, set[str]] = defaultdict(set)
        self.lock = asyncio.Lock()
        self.pending_requests: dict[str, PendingWorkspaceRequest] = {}

    def _fail_pending_for_device_locked(self, device_id: int, reason: str):
        for request_id, pending in list(self.pending_requests.items()):
            if pending.device_id == device_id:
                self.pending_requests.pop(request_id, None)
                if not pending.future.done():
                    pending.future.set_exception(RuntimeError(reason))

    async def connect(self, device_id: int, websocket: WebSocket):
        browser_sockets = []

        async with self.lock:
            previous = self.connections.get(device_id)

            if previous is websocket:
                return

            self.connections[device_id] = websocket
            if previous is not None:
                self._fail_pending_for_device_locked(
                    device_id, "Device connection was replaced"
                )

            session_ids = list(self.device_sessions.pop(device_id, set()))
            for session_id in session_ids:
                entry = self.sessions.pop(session_id, None)
                if entry:
                    browser_sockets.append(entry[1])

        if previous:
            try:
                await previous.close(
                    code=4001,
                    reason="Replaced by a newer device connection",
                )
            except Exception:
                pass

        for browser_socket in browser_sockets:
            try:
                await browser_socket.close(
                    code=4001,
                    reason="Device connection was replaced",
                )
            except Exception:
                pass

    async def disconnect(self, device_id: int, websocket: WebSocket):
        browser_sockets = []

        async with self.lock:
            if self.connections.get(device_id) is not websocket:
                return

            self.connections.pop(device_id, None)
            self._fail_pending_for_device_locked(
                device_id, "Device disconnected"
            )

            session_ids = list(self.device_sessions.pop(device_id, set()))
            for session_id in session_ids:
                entry = self.sessions.pop(session_id, None)
                if entry:
                    browser_sockets.append(entry[1])

        for browser_socket in browser_sockets:
            try:
                await browser_socket.close(
                    code=4001,
                    reason="Device disconnected",
                )
            except Exception:
                pass

    async def revoke(self, device_id: int):
        async with self.lock:
            device_socket = self.connections.pop(device_id, None)
            self._fail_pending_for_device_locked(
                device_id, "Device access revoked"
            )
            session_ids = list(self.device_sessions.pop(device_id, set()))
            browser_sockets = []

            for session_id in session_ids:
                entry = self.sessions.pop(session_id, None)
                if entry:
                    browser_sockets.append(entry[1])

        if device_socket:
            try:
                await device_socket.close(
                    code=4403,
                    reason="Device access revoked",
                )
            except Exception:
                pass

        for browser_socket in browser_sockets:
            try:
                await browser_socket.close(
                    code=4001,
                    reason="Device access revoked",
                )
            except Exception:
                pass

    async def get_connection(self, device_id: int):
        async with self.lock:
            return self.connections.get(device_id)

    async def is_connected(self, device_id: int) -> bool:
        return await self.get_connection(device_id) is not None

    async def register_session(
        self,
        session_id: str,
        device_id: int,
        browser_socket: WebSocket,
    ):
        async with self.lock:
            if device_id not in self.connections:
                raise RuntimeError("Device is not connected")

            self.sessions[session_id] = (device_id, browser_socket)
            self.device_sessions[device_id].add(session_id)

    async def remove_session(self, session_id: str):
        async with self.lock:
            entry = self.sessions.pop(session_id, None)

            if entry:
                device_id, _ = entry
                self.device_sessions[device_id].discard(session_id)

    async def send_to_device(self, device_id: int, message: dict):
        websocket = await self.get_connection(device_id)

        if websocket is None:
            raise RuntimeError("Device is disconnected")

        await websocket.send_json(message)

    async def request_workspace(
        self,
        device_id: int,
        message: dict,
        timeout: float = 30.0,
    ):
        request_id = message.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("A valid request_id is required")

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async with self.lock:
            websocket = self.connections.get(device_id)
            if websocket is None:
                raise RuntimeError("Device is disconnected")
            if request_id in self.pending_requests:
                raise RuntimeError("Duplicate workspace request ID")

            self.pending_requests[request_id] = PendingWorkspaceRequest(
                device_id=device_id,
                future=future,
            )

        try:
            await websocket.send_json(message)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Workspace agent request timed out") from exc
        finally:
            async with self.lock:
                pending = self.pending_requests.get(request_id)
                if pending is not None and pending.future is future:
                    self.pending_requests.pop(request_id, None)

    async def resolve_workspace_response(
        self,
        device_id: int,
        message: dict,
    ) -> bool:
        request_id = message.get("request_id")
        if not isinstance(request_id, str):
            return False

        async with self.lock:
            pending = self.pending_requests.get(request_id)
            if pending is None or pending.device_id != device_id:
                return False

            if pending.future.done():
                return False

            if message.get("success") is True:
                pending.future.set_result(message.get("result"))
            else:
                error = message.get("error", "Workspace operation failed")
                pending.future.set_exception(RuntimeError(str(error)[:500]))

            return True

    async def send_to_browser(self, session_id: str, message: dict):
        async with self.lock:
            entry = self.sessions.get(session_id)

        if entry is None:
            return False

        _, browser_socket = entry
        await browser_socket.send_json(message)
        return True
    async def send_to_browser_for_device(
        self,
        device_id: int,
        session_id: str,
        message: dict,
    ):
        async with self.lock:
            entry = self.sessions.get(session_id)

        if entry is None or entry[0] != device_id:
            return False

        browser_socket = entry[1]

        try:
            await browser_socket.send_json(message)
            return True
        except Exception:
            await self.remove_session(session_id)

            try:
                await browser_socket.close(
                    code=4001,
                    reason="Browser terminal connection failed",
                )
            except Exception:
                pass

            return False


    async def send_text_to_browser_for_device(
        self,
        device_id: int,
        session_id: str,
        data: str,
    ):
        async with self.lock:
            entry = self.sessions.get(session_id)

        if entry is None or entry[0] != device_id:
            return False

        browser_socket = entry[1]

        try:
            await browser_socket.send_text(data)
            return True
        except Exception:
            await self.remove_session(session_id)

            try:
                await browser_socket.close(
                    code=4001,
                    reason="Browser terminal connection failed",
                )
            except Exception:
                pass

            return False

device_connections = DeviceConnectionManager()


def authenticate_device(db: Session, device_token: str):
    token_hash = hashlib.sha256(
        device_token.encode("utf-8")
    ).hexdigest()

    return (
        db.query(UserDevice)
        .filter(
            UserDevice.device_token_hash == token_hash,
            UserDevice.is_active.is_(True),
        )
        .first()
    )