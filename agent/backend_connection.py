
from __future__ import annotations

import asyncio
import json
import logging

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from backend_terminal import BackendTerminalManager
from docker_workspace import DockerWorkspaceManager
from docker_terminal import DockerTerminalManager

logger = logging.getLogger("adri.backend_connection")


async def handle_workspace_request(
    message: dict,
    docker_manager: DockerWorkspaceManager,
    send_message,
):
    request_id = message.get("request_id")
    operation = message.get("operation")
    user_id = message.get("user_id")
    workspace_id = message.get("workspace_id")

    response = {
        "type": "workspace.response",
        "request_id": request_id,
        "success": False,
    }

    try:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
            raise ValueError("Invalid request ID")

        if type(user_id) is not int or user_id < 1:
            raise ValueError("Invalid user ID")

        if type(workspace_id) is not int or workspace_id < 1:
            raise ValueError("Invalid workspace ID")

        operations = {
            "start": docker_manager.start,
            "stop": docker_manager.stop,
            "status": docker_manager.status,
        }

        if operation in operations:
            result = await asyncio.to_thread(
                operations[operation],
                user_id,
                workspace_id,
            )

        elif operation == "execute":
            command = message.get("command")

            if not isinstance(command, str) or not 1 <= len(command) <= 1000:
                raise ValueError("Invalid command")

            result = await asyncio.to_thread(
                docker_manager.execute,
                user_id,
                workspace_id,
                command,
            )

        else:
            raise ValueError("Unsupported workspace operation")

        response["success"] = True
        response["result"] = result

    except Exception as exc:
        logger.warning(
            "Workspace request failed (operation=%s, request_id=%s): %s",
            operation,
            request_id,
            exc,
        )
        response["error"] = str(exc)[:500]

    await send_message(response)


async def run_backend_connection(
    backend_url: str,
    device_token: str,
    heartbeat_seconds: int = 25,
):
    if not backend_url or not device_token:
        logger.warning(
            "Backend connection not started: URL or device token is missing."
        )
        return

    heartbeat_seconds = max(5, heartbeat_seconds)

    while True:
        try:
            logger.info("Connecting to ADRI AI backend...")

            async with connect(
                backend_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            ) as websocket:

                await websocket.send(json.dumps({
                    "type": "authenticate",
                    "device_token": device_token,
                }))

                response = json.loads(
                    await asyncio.wait_for(websocket.recv(), timeout=10)
                )

                if (
                    not isinstance(response, dict)
                    or response.get("type") != "authenticated"
                ):
                    logger.error("Backend authentication was rejected.")
                    await websocket.close()
                    await asyncio.sleep(10)
                    continue

                logger.info(
                    "Agent authenticated. Device ID: %s",
                    response.get("device_id"),
                )

                send_lock = asyncio.Lock()

                async def send_message(message: dict):
                    async with send_lock:
                        await websocket.send(json.dumps(message))

                manager = BackendTerminalManager(send_message)
                docker_manager = DockerWorkspaceManager()
                docker_terminal_manager = DockerTerminalManager(
                    docker_manager,
                    send_message,
                )

                async def heartbeat():
                    while True:
                        await asyncio.sleep(heartbeat_seconds)
                        try:
                            await send_message({"type": "heartbeat"})
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception(
                                "Heartbeat failed; closing backend connection."
                            )
                            try:
                                await websocket.close()
                            except Exception:
                                pass
                            raise

                heartbeat_task = asyncio.create_task(heartbeat())

                try:
                    async for raw_message in websocket:
                        message = json.loads(raw_message)

                        if not isinstance(message, dict):
                            continue

                        message_type = message.get("type")
                        session_id = message.get("session_id")

                        if message_type == "heartbeat_ack":
                            continue

                        if message_type == "workspace.terminal.open":
                            try:
                                await docker_terminal_manager.open(
                                    session_id,
                                    message.get("user_id"),
                                    message.get("workspace_id"),
                                    message.get("rows", 30),
                                    message.get("cols", 100),
                                )
                                await send_message({
                                    "type": "workspace.terminal.ready",
                                    "session_id": session_id,
                                })
                            except Exception:
                                logger.exception(
                                    "Could not open Docker terminal session."
                                )
                                await send_message({
                                    "type": "workspace.terminal.closed",
                                    "session_id": session_id,
                                })

                        elif message_type == "workspace.terminal.input":
                            try:
                                await docker_terminal_manager.input(
                                    session_id,
                                    message.get("data"),
                                )
                            except Exception:
                                logger.exception(
                                    "Could not process Docker terminal input."
                                )
                                await docker_terminal_manager.close(session_id)
                                await send_message({
                                    "type": "workspace.terminal.closed",
                                    "session_id": session_id,
                                })

                        elif message_type == "workspace.terminal.resize":
                            try:
                                await docker_terminal_manager.resize(
                                    session_id,
                                    message.get("rows", 30),
                                    message.get("cols", 100),
                                )
                            except Exception:
                                logger.exception(
                                    "Could not resize Docker terminal session."
                                )
                                await docker_terminal_manager.close(session_id)
                                await send_message({
                                    "type": "workspace.terminal.closed",
                                    "session_id": session_id,
                                })

                        elif message_type == "workspace.terminal.close":
                            await docker_terminal_manager.close(session_id)

                            continue

                        if message_type == "workspace.request":
                            await handle_workspace_request(
                                message,
                                docker_manager,
                                send_message,
                            )

                        elif message_type == "terminal.open":
                            if isinstance(session_id, str):
                                try:
                                    await manager.open(session_id)
                                except Exception:
                                    logger.exception(
                                        "Could not open terminal session."
                                    )
                                    await send_message({
                                        "type": "terminal.closed",
                                        "session_id": session_id,
                                    })

                        elif message_type == "terminal.input":
                            if (
                                isinstance(session_id, str)
                                and isinstance(message.get("data"), str)
                            ):
                                try:
                                    await manager.input(
                                        session_id,
                                        message["data"],
                                    )
                                except Exception:
                                    logger.exception(
                                        "Could not process terminal input."
                                    )
                                    await manager.close(session_id)
                                    await send_message({
                                        "type": "terminal.closed",
                                        "session_id": session_id,
                                    })

                        elif message_type == "terminal.resize":
                            if isinstance(session_id, str):
                                try:
                                    await manager.resize(
                                        session_id,
                                        message.get("rows", 30),
                                        message.get("cols", 100),
                                    )
                                except Exception:
                                    logger.exception(
                                        "Could not resize terminal session."
                                    )
                                    await manager.close(session_id)
                                    await send_message({
                                        "type": "terminal.closed",
                                        "session_id": session_id,
                                    })

                        elif message_type == "terminal.close":
                            if isinstance(session_id, str):
                                await manager.close(session_id)

                finally:
                    heartbeat_task.cancel()
                    await asyncio.gather(
                        heartbeat_task,
                        return_exceptions=True,
                    )
                    await manager.close_all()
                    await docker_terminal_manager.close_all()
                    await asyncio.to_thread(docker_manager.close)

        except asyncio.CancelledError:
            raise

        except ConnectionClosed as exc:
            logger.warning(
                "Backend connection closed (code %s).",
                exc.code,
            )

        except Exception:
            logger.exception("Backend connection failed.")

        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)
