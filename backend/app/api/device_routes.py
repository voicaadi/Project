from uuid import uuid4
from app.security.auth import decode_access_token
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from app.database.connection import SessionLocal
from app.services.device_connection import (
    authenticate_device,
    device_connections,
)
from app.security.rate_limit import limiter
from fastapi import Request
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_routes import get_current_user
from app.database.connection import get_db
from app.database.models import DevicePairing, User, UserDevice

router = APIRouter(prefix="/api/devices", tags=["User Devices"])

PAIRING_MINUTES = 5


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PairingClaim(BaseModel):
    code: str = Field(min_length=32, max_length=32)
    device_name: str = Field(min_length=1, max_length=150)
    operating_system: str = Field(min_length=1, max_length=50)


@router.post("/pairing")
def create_pairing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = secrets.token_hex(16).upper()

    pairing = DevicePairing(
        user_id=current_user.id,
        code_hash=hash_value(code),
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=PAIRING_MINUTES),
    )

    db.add(pairing)
    db.commit()

    return {
        "code": code,
        "expires_in_seconds": PAIRING_MINUTES * 60,
    }



@router.post("/claim")
@limiter.limit("5/minute")
def claim_device(
    request: Request,
    data: PairingClaim,
    db: Session = Depends(get_db),
):
    device_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)

    with db.begin():
        pairing = (
            db.query(DevicePairing)
            .filter(
                DevicePairing.code_hash == hash_value(data.code.upper())
            )
            .with_for_update()
            .first()
        )

        if not pairing:
            raise HTTPException(
                status_code=400,
                detail="Invalid pairing code",
            )

        expires_at = pairing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if pairing.used_at is not None or expires_at <= now:
            raise HTTPException(
                status_code=400,
                detail="Pairing code expired or already used",
            )

        device = UserDevice(
            user_id=pairing.user_id,
            device_name=data.device_name,
            operating_system=data.operating_system,
            device_token_hash=hash_value(device_token),
            is_active=True,
        )

        pairing.used_at = now
        db.add(device)
        db.flush()

        device_id = device.id

    return {
        "device_id": device_id,
        "device_token": device_token,
        "message": "Device paired successfully",
    }


@router.get("/")
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = (
        db.query(UserDevice)
        .filter(UserDevice.user_id == current_user.id)
        .order_by(UserDevice.created_at.desc())
        .all()
    )

    return [
        {
            "id": device.id,
            "device_name": device.device_name,
            "operating_system": device.operating_system,
            "is_active": device.is_active,
            "last_seen_at": device.last_seen_at,
            "created_at": device.created_at,
        }
        for device in devices
    ]


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = (
        db.query(UserDevice)
        .filter(
            UserDevice.id == device_id,
            UserDevice.user_id == current_user.id,
        )
        .first()
    )

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.is_active = False
    db.commit()
@router.websocket("/agent/connect")
async def agent_connect(websocket: WebSocket):
    await websocket.accept()

    db = SessionLocal()
    device_id = None

    try:
        # Authenticate using the first WebSocket message.
        auth_message = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=10,
        )

        if auth_message.get("type") != "authenticate":
            await websocket.close(code=4401)
            return

        device_token = auth_message.get("device_token")

        if not isinstance(device_token, str) or not device_token:
            await websocket.close(code=4401)
            return

        device = authenticate_device(db, device_token)

        if not device:
            await websocket.close(code=4401)
            return

        device_id = device.id

        await device_connections.connect(device_id, websocket)

        device.last_seen_at = datetime.now(timezone.utc)
        db.commit()

        await websocket.send_json({
            "type": "authenticated",
            "device_id": device_id,
        })

        while True:
            message_type = message.get("type")

            if message_type == "heartbeat":
                device.last_seen_at = datetime.now(timezone.utc)
                db.commit()

                await websocket.send_json({
                    "type": "heartbeat_ack"
                })

            elif message_type == "terminal.output":
                session_id = message.get("session_id")
                data = message.get("data", "")

                if isinstance(session_id, str) and isinstance(data, str):
                    await device_connections.send_to_browser_for_device(
                        device_id,
                        session_id,
                        {
                            "type": "terminal.output",
                            "session_id": session_id,
                            "data": data,
                        },
                    )

            elif message_type == "terminal.closed":
                session_id = message.get("session_id")

                if isinstance(session_id, str):
                    await device_connections.send_to_browser_for_device(
                        device_id,
                        session_id,
                        {
                            "type": "terminal.closed",
                            "session_id": session_id,
                        },
                    )
                    await device_connections.remove_session(session_id)

    except asyncio.TimeoutError:
        await websocket.close(code=4401)

    except WebSocketDisconnect:
        pass

    except Exception:
        db.rollback()
        try:
            await websocket.close(code=1011)
        except Exception:
            pass

    finally:
        if device_id is not None:
            await device_connections.disconnect(
                device_id,
                websocket,
            )

        db.close()
@router.websocket("/{device_id}/terminal/ws")
async def device_terminal_websocket(
    websocket: WebSocket,
    device_id: int,
):
    await websocket.accept()

    db = SessionLocal()
    session_id = None

    try:
        # Authenticate the browser's first message.
        auth_message = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=10,
        )

        if auth_message.get("type") != "authenticate":
            await websocket.close(code=4401)
            return

        try:
            payload = decode_access_token(auth_message["token"])
            user_id = int(payload["sub"])
        except Exception:
            await websocket.close(code=4401)
            return

        user = db.query(User).filter(
            User.id == user_id,
            User.is_active.is_(True),
        ).first()

        device = db.query(UserDevice).filter(
            UserDevice.id == device_id,
            UserDevice.user_id == user_id,
            UserDevice.is_active.is_(True),
        ).first()

        if not user or not device:
            await websocket.close(code=4403)
            return

        if not await device_connections.is_connected(device_id):
            await websocket.close(code=4409)
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
                "type": "terminal.open",
                "session_id": session_id,
            },
        )

        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")

            if message_type == "terminal.input":
                data = message.get("data")

                if isinstance(data, str):
                    await device_connections.send_to_device(
                        device_id,
                        {
                            "type": "terminal.input",
                            "session_id": session_id,
                            "data": data,
                        },
                    )

            elif message_type == "terminal.resize":
                rows = message.get("rows", 30)
                cols = message.get("cols", 100)

                if (
                    isinstance(rows, int)
                    and isinstance(cols, int)
                    and 5 <= rows <= 100
                    and 20 <= cols <= 300
                ):
                    await device_connections.send_to_device(
                        device_id,
                        {
                            "type": "terminal.resize",
                            "session_id": session_id,
                            "rows": rows,
                            "cols": cols,
                        },
                    )

            elif message_type == "terminal.close":
                break

    except asyncio.TimeoutError:
        await websocket.close(code=4401)

    except WebSocketDisconnect:
        pass

    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass

    finally:
        if session_id is not None:
            await device_connections.remove_session(session_id)

            try:
                await device_connections.send_to_device(
                    device_id,
                    {
                        "type": "terminal.close",
                        "session_id": session_id,
                    },
                )
            except Exception:
                pass

        db.close()