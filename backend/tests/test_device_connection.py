import asyncio

import pytest
from unittest.mock import AsyncMock
from app.services.device_connection import DeviceConnectionManager
@pytest.fixture
def anyio_backend():
    return "asyncio"



@pytest.mark.anyio
async def test_device_connection_and_session_registration():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    browser_socket = AsyncMock()

    await manager.connect(1, device_socket)
    assert await manager.is_connected(1)

    await manager.register_session(
        "session-1",
        1,
        browser_socket,
    )

    assert "session-1" in manager.device_sessions[1]


@pytest.mark.anyio
async def test_terminal_output_reaches_correct_browser():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    browser_socket = AsyncMock()

    await manager.connect(1, device_socket)
    await manager.register_session(
        "session-1",
        1,
        browser_socket,
    )

    message = {
        "type": "terminal.output",
        "session_id": "session-1",
        "data": "Hello from ADRI AI",
    }

    result = await manager.send_to_browser_for_device(
        1,
        "session-1",
        message,
    )

    assert result is True
    browser_socket.send_json.assert_awaited_once_with(message)


@pytest.mark.anyio
async def test_device_cannot_send_to_another_devices_session():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    browser_socket = AsyncMock()

    await manager.connect(1, device_socket)
    await manager.register_session(
        "session-1",
        1,
        browser_socket,
    )

    result = await manager.send_to_browser_for_device(
        2,
        "session-1",
        {"type": "terminal.output", "data": "unauthorized"},
    )

    assert result is False
    browser_socket.send_json.assert_not_awaited()


@pytest.mark.anyio
async def test_disconnected_device_cannot_receive_commands():
    manager = DeviceConnectionManager()

    with pytest.raises(RuntimeError, match="Device is disconnected"):
        await manager.send_to_device(
            1,
            {"type": "terminal.input", "data": "ls"},
        )


@pytest.mark.anyio
async def test_replacing_device_connection_cleans_old_sessions():
    manager = DeviceConnectionManager()
    old_device_socket = AsyncMock()
    new_device_socket = AsyncMock()
    browser_socket = AsyncMock()

    await manager.connect(1, old_device_socket)
    await manager.register_session(
        "old-session",
        1,
        browser_socket,
    )

    await manager.connect(1, new_device_socket)

    old_device_socket.close.assert_awaited_once()
    browser_socket.close.assert_awaited_once()
    assert await manager.get_connection(1) is new_device_socket
    assert "old-session" not in manager.sessions
    assert "old-session" not in manager.device_sessions.get(1, set())


@pytest.mark.anyio
async def test_device_disconnect_closes_browser_sessions():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    browser_socket = AsyncMock()

    await manager.connect(1, device_socket)
    await manager.register_session(
        "disconnect-session",
        1,
        browser_socket,
    )

    await manager.disconnect(1, device_socket)

    browser_socket.close.assert_awaited_once()
    assert not await manager.is_connected(1)
    assert "disconnect-session" not in manager.sessions


@pytest.mark.anyio
async def test_old_connection_disconnect_does_not_remove_new_connection():
    manager = DeviceConnectionManager()
    old_socket = AsyncMock()
    new_socket = AsyncMock()

    await manager.connect(1, old_socket)
    await manager.connect(1, new_socket)

    await manager.disconnect(1, old_socket)

    assert await manager.get_connection(1) is new_socket
    assert await manager.is_connected(1)


@pytest.mark.anyio
async def test_revoking_device_closes_agent_and_browser_sessions():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    browser_socket = AsyncMock()

    await manager.connect(1, device_socket)
    await manager.register_session(
        "revoked-session",
        1,
        browser_socket,
    )

    await manager.revoke(1)

    device_socket.close.assert_awaited_once_with(
        code=4403,
        reason="Device access revoked",
    )
    browser_socket.close.assert_awaited_once_with(
        code=4001,
        reason="Device access revoked",
    )

    assert not await manager.is_connected(1)
    assert "revoked-session" not in manager.sessions
    assert "revoked-session" not in manager.device_sessions.get(1, set())

    with pytest.raises(RuntimeError, match="Device is disconnected"):
        await manager.send_to_device(
            1,
            {"type": "terminal.input", "data": "ls"},
        )


@pytest.mark.anyio
async def test_failed_browser_send_removes_session_but_keeps_device_connected():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    browser_socket = AsyncMock()
    browser_socket.send_json.side_effect = RuntimeError("Browser disconnected")

    await manager.connect(1, device_socket)
    await manager.register_session(
        "failed-session",
        1,
        browser_socket,
    )

    result = await manager.send_to_browser_for_device(
        1,
        "failed-session",
        {"type": "terminal.output", "data": "test"},
    )

    assert result is False
    assert "failed-session" not in manager.sessions
    assert await manager.is_connected(1)
    browser_socket.close.assert_awaited_once()


@pytest.mark.anyio
async def test_workspace_request_receives_matching_response():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    await manager.connect(1, device_socket)

    task = asyncio.create_task(
        manager.request_workspace(
            1,
            {"type": "workspace.request", "request_id": "req-1"},
        )
    )
    await asyncio.sleep(0)

    resolved = await manager.resolve_workspace_response(
        1,
        {
            "request_id": "req-1",
            "success": True,
            "result": {"status": "running"},
        },
    )

    assert resolved is True
    assert await task == {"status": "running"}
    assert "req-1" not in manager.pending_requests


@pytest.mark.anyio
async def test_workspace_response_from_wrong_device_is_rejected():
    manager = DeviceConnectionManager()
    await manager.connect(1, AsyncMock())

    task = asyncio.create_task(
        manager.request_workspace(
            1,
            {"type": "workspace.request", "request_id": "req-2"},
        )
    )
    await asyncio.sleep(0)

    resolved = await manager.resolve_workspace_response(
        2,
        {"request_id": "req-2", "success": True, "result": "wrong"},
    )

    assert resolved is False

    resolved = await manager.resolve_workspace_response(
        1,
        {"request_id": "req-2", "success": True, "result": "correct"},
    )

    assert resolved is True
    assert await task == "correct"


@pytest.mark.anyio
async def test_device_disconnect_fails_pending_workspace_request():
    manager = DeviceConnectionManager()
    device_socket = AsyncMock()
    await manager.connect(1, device_socket)

    task = asyncio.create_task(
        manager.request_workspace(
            1,
            {"type": "workspace.request", "request_id": "req-3"},
        )
    )
    await asyncio.sleep(0)

    await manager.disconnect(1, device_socket)

    with pytest.raises(RuntimeError, match="Device disconnected"):
        await task

    assert "req-3" not in manager.pending_requests


@pytest.mark.anyio
async def test_workspace_request_timeout_cleans_pending_request():
    manager = DeviceConnectionManager()
    await manager.connect(1, AsyncMock())

    with pytest.raises(TimeoutError, match="timed out"):
        await manager.request_workspace(
            1,
            {"type": "workspace.request", "request_id": "req-4"},
            timeout=0.01,
        )

    assert "req-4" not in manager.pending_requests


@pytest.mark.anyio
async def test_agent_workspace_error_reaches_request_caller():
    manager = DeviceConnectionManager()
    await manager.connect(1, AsyncMock())

    task = asyncio.create_task(
        manager.request_workspace(
            1,
            {"type": "workspace.request", "request_id": "req-5"},
        )
    )
    await asyncio.sleep(0)

    resolved = await manager.resolve_workspace_response(
        1,
        {
            "request_id": "req-5",
            "success": False,
            "error": "Workspace container not found",
        },
    )

    assert resolved is True
    with pytest.raises(RuntimeError, match="Workspace container not found"):
        await task


@pytest.mark.anyio
async def test_raw_terminal_output_reaches_correct_browser():
    manager = DeviceConnectionManager()
    browser_socket = AsyncMock()

    await manager.connect(1, AsyncMock())
    await manager.register_session("raw-session", 1, browser_socket)

    result = await manager.send_text_to_browser_for_device(
        1,
        "raw-session",
        "Hello from Docker",
    )

    assert result is True
    browser_socket.send_text.assert_awaited_once_with("Hello from Docker")


@pytest.mark.anyio
async def test_raw_terminal_output_rejects_wrong_device():
    manager = DeviceConnectionManager()
    browser_socket = AsyncMock()

    await manager.connect(1, AsyncMock())
    await manager.register_session("raw-session", 1, browser_socket)

    result = await manager.send_text_to_browser_for_device(
        2,
        "raw-session",
        "unauthorized output",
    )

    assert result is False
    browser_socket.send_text.assert_not_awaited()
