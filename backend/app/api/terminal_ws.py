import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.database.models import User, Workspace
from app.security.auth import decode_access_token
from app.services.workspace_service import get_docker_client

router = APIRouter(tags=["Terminal"])


@router.websocket("/api/workspaces/{workspace_id}/terminal/ws")
async def terminal_websocket(websocket: WebSocket, workspace_id: int):
    await websocket.accept()

    db: Session = SessionLocal()
    docker_socket = None
    input_task = None
    output_task = None

    try:
        # First WebSocket message must contain the JWT.
        auth_data = await websocket.receive_json()
        token = auth_data.get("token")

        if not token:
            await websocket.close(code=4401)
            return

        try:
            payload = decode_access_token(token)
            user_id = int(payload["sub"])
        except Exception:
            await websocket.close(code=4401)
            return

        # Verify user and workspace ownership.
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

        client = get_docker_client()

        container_name = (
            f"devops-user-{user_id}-workspace-{workspace_id}"
        )

        container = client.containers.get(container_name)
        container.reload()

        if container.status != "running":
            await websocket.close(code=4409)
            return

        # Create a persistent interactive Bash session with a PTY.
        exec_data = client.api.exec_create(
            container.id,
            cmd=["/bin/bash", "--login"],
            stdin=True,
            stdout=True,
            stderr=True,
            tty=True,
            user="devops",
            workdir="/home/devops/workspace",
        )

        docker_socket = client.api.exec_start(
            exec_data["Id"],
            detach=False,
            tty=True,
            socket=True,
        )

        raw_socket = getattr(docker_socket, "_sock", docker_socket)

        async def send_to_container():
            while True:
                message = await websocket.receive_text()

                # Terminal resize message: NUL + RESIZE:columns:rows
                if message.startswith("\x00RESIZE:"):
                    _, cols, rows = message.split(":", 2)

                    await asyncio.to_thread(
                        client.api.exec_resize,
                        exec_data["Id"],
                        height=int(rows),
                        width=int(cols),
                    )
                    continue

                # Forward keyboard input to the container PTY.
                await asyncio.to_thread(
                    raw_socket.sendall,
                    message.encode("utf-8"),
                )

        async def receive_from_container():
            while True:
                output = await asyncio.to_thread(
                    raw_socket.recv, 4096
                )

                if not output:
                    break

                await websocket.send_text(
                    output.decode("utf-8", errors="replace")
                )

        input_task = asyncio.create_task(send_to_container())
        output_task = asyncio.create_task(receive_from_container())

        done, pending = await asyncio.wait(
            [input_task, output_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        # Surface an exception from the task that completed.
        for task in done:
            task.result()

    except WebSocketDisconnect:
        pass

    except Exception as error:
        print("TERMINAL WEBSOCKET ERROR:", repr(error))

        try:
            await websocket.close(code=1011)
        except Exception:
            pass

    finally:
        for task in (input_task, output_task):
            if task and not task.done():
                task.cancel()

        if input_task or output_task:
            await asyncio.gather(
                *(task for task in (input_task, output_task) if task),
                return_exceptions=True,
            )

        if docker_socket:
            try:
                docker_socket.close()
            except Exception:
                pass

        db.close()
