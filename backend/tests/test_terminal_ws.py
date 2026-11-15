import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database.connection import (
    Base,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_HOST,
    POSTGRES_PORT,
    get_db,
)
from app.database.models import User, UserDevice, Workspace
from app.security.auth import create_access_token
from app.api import terminal_ws
from app.services.device_connection import device_connections


@pytest.fixture
def terminal_environment(monkeypatch):
    test_url = URL.create(
        "postgresql+psycopg2",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=int(POSTGRES_PORT),
        database="devops_ai_test",
    )

    engine = create_engine(test_url)
    Base.metadata.create_all(bind=engine)

    connection = engine.connect()
    transaction = connection.begin()

    TestSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(terminal_ws, "SessionLocal", TestSession)

    sent_messages = []
    registered_sessions = []
    removed_sessions = []

    async def connected(device_id):
        return True

    async def register(session_id, device_id, browser_socket):
        registered_sessions.append((session_id, device_id))

    async def send(device_id, message):
        sent_messages.append((device_id, message))

    async def remove(session_id):
        removed_sessions.append(session_id)

    monkeypatch.setattr(device_connections, "is_connected", connected)
    monkeypatch.setattr(device_connections, "register_session", register)
    monkeypatch.setattr(device_connections, "send_to_device", send)
    monkeypatch.setattr(device_connections, "remove_session", remove)

    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield {
                "client": client,
                "session_factory": TestSession,
                "sent_messages": sent_messages,
                "registered_sessions": registered_sessions,
                "removed_sessions": removed_sessions,
            }
    finally:
        app.dependency_overrides.clear()
        transaction.rollback()
        connection.close()
        engine.dispose()


def create_test_workspace(session_factory):
    db = session_factory()
    unique_id = uuid.uuid4().hex

    try:
        user = User(
            email=f"{unique_id}@example.com",
            username=f"user_{unique_id[:12]}",
            hashed_password="test-hash",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.flush()

        device = UserDevice(
            user_id=user.id,
            device_name="Test PC",
            operating_system="Linux",
            device_token_hash=uuid.uuid4().hex,
            is_active=True,
        )
        db.add(device)
        db.flush()

        workspace = Workspace(
            name="Terminal Test",
            user_id=user.id,
            device_id=device.id,
            status="running",
        )
        db.add(workspace)
        db.commit()

        return (
            user.id,
            device.id,
            workspace.id,
            create_access_token(user.id),
        )
    finally:
        db.close()


def test_browser_terminal_forwards_input_resize_and_close(
    terminal_environment,
):
    env = terminal_environment
    user_id, device_id, workspace_id, token = create_test_workspace(
        env["session_factory"]
    )

    with env["client"].websocket_connect(
        f"/api/workspaces/{workspace_id}/terminal/ws"
    ) as websocket:
        websocket.send_json({"token": token})
        websocket.send_text("whoami\n")
        websocket.send_text("\x00RESIZE:120:40")

    messages = [message for _, message in env["sent_messages"]]

    assert len(messages) == 4

    open_message, input_message, resize_message, close_message = messages

    assert open_message["type"] == "workspace.terminal.open"
    assert open_message["user_id"] == user_id
    assert open_message["workspace_id"] == workspace_id
    assert open_message["rows"] == 30
    assert open_message["cols"] == 100

    assert input_message["type"] == "workspace.terminal.input"
    assert input_message["data"] == "whoami\n"

    assert resize_message["type"] == "workspace.terminal.resize"
    assert resize_message["rows"] == 40
    assert resize_message["cols"] == 120

    assert close_message["type"] == "workspace.terminal.close"

    assert all(
        sent_device_id == device_id
        for sent_device_id, _ in env["sent_messages"]
    )

    assert len(env["registered_sessions"]) == 1
    assert len(env["removed_sessions"]) == 1
    assert (
        env["registered_sessions"][0][0]
        == env["removed_sessions"][0]
    )


def test_browser_terminal_rejects_workspace_without_device(
    terminal_environment,
):
    env = terminal_environment
    user_id, _, workspace_id, token = create_test_workspace(
        env["session_factory"]
    )

    db = env["session_factory"]()
    try:
        workspace = db.query(Workspace).filter(
            Workspace.id == workspace_id
        ).one()
        workspace.device_id = None
        db.commit()
    finally:
        db.close()

    with env["client"].websocket_connect(
        f"/api/workspaces/{workspace_id}/terminal/ws"
    ) as websocket:
        websocket.send_json({"token": token})

        with pytest.raises(WebSocketDisconnect) as error:
            websocket.receive_text()

    assert error.value.code == 4409
    assert env["sent_messages"] == []
    assert env["registered_sessions"] == []
