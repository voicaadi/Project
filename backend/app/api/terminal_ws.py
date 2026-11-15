import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.database.models import User, UserDevice, Workspace
from app.security.auth import decode_access_token
from app.services.device_connection import device_connections

router = APIRouter(tags=["Terminal"])
logger = logging.getLogger(__name__)


@router.websocket("/api/workspaces/{workspace_id}/terminal/ws")
async def terminal_websocket(websocket: WebSocket, workspace_id: int):
    await websocket.accept()

    db: Session = SessionLocal()
    device_id = None
    session_id = None

    try:
        # The first browser message must contain the JWT.
        auth_data = await websocket.receive_json()
        token = auth_data.get("token") if isinstance(auth_data, dict) else None

        if not token:
            await websocket.close(code=4401)
            return

        try:
            payload = decode_access_token(token)
            user_id = int(payload["sub"])
        except Exception:
            await websocket.close(code=4401)
            return

        user = db.query(User).filter(
            User.id == user_id,
            User.is_active.is_(True),
        ).first()

        workspace = db.query(Workspace).filter(
            Workspace.id == workspace_id,
            Workspace.user_id == user_id,
        ).first()

        if not user or not workspace:
            await websocket.close(code=4403)
            return

        if not workspace.device_id:
            await websocket.close(code=4409, reason="Workspace has no assigned device")
            return

        device = db.query(UserDevice).filter(
            UserDevice.id == workspace.device_id,
            UserDevice.user_id == user_id,
            UserDevice.is_active.is_(True),
        ).first()

        if not device:
            await websocket.close(code=4409, reason="Assigned device is unavailable")
            return

        device_id = device.id

        if not await device_connections.is_connected(device_id):
            await websocket.close(code=4409, reason="Local agent is offline")
            return

        session_id = str(uuid4())

        await device_connections.register_session(
            session_id,
            device_id,
            websocket,
        )

        await device_connections.send_to_device(
            device_id,
            {
                "type": "workspace.terminal.open",
                "session_id": session_id,
                "user_id": user_id,
                "workspace_id": workspace_id,
                "rows": 30,
                "cols": 100,
            },
        )

        # Preserve the existing browser protocol:
        # raw text for input, NUL + RESIZE:columns:rows for resize.
        while True:
            message = await websocket.receive_text()

            if message.startswith("\x00RESIZE:"):
                try:
                    _, cols_text, rows_text = message.split(":", 2)
                    cols = int(cols_text)
                    rows = int(rows_text)
                except (ValueError, TypeError):
                    continue

                if not (5 <= rows <= 100 and 20 <= cols <= 300):
                    continue

                await device_connections.send_to_device(
                    device_id,
                    {
                        "type": "workspace.terminal.resize",
                        "session_id": session_id,
                        "rows": rows,
                        "cols": cols,
                    },
                )
                continue

            await device_connections.send_to_device(
                device_id,
                {
                    "type": "workspace.terminal.input",
                    "session_id": session_id,
                    "data": message,
                },
            )

    except WebSocketDisconnect:
        pass

    except Exception:
        logger.exception(
            "Workspace terminal WebSocket failed (workspace_id=%s, device_id=%s)",
            workspace_id,
            device_id,
        )
        try:
            await websocket.close(code=1011)
        except Exception:
            pass

    finally:
        if session_id is not None:
            if device_id is not None:
                try:
                    if await device_connections.is_connected(device_id):
                        await device_connections.send_to_device(
                            device_id,
                            {
                                "type": "workspace.terminal.close",
                                "session_id": session_id,
                            },
                        )
                except Exception:
                    logger.warning("Could not send Docker terminal close request.")

            await device_connections.remove_session(session_id)

        db.close()
