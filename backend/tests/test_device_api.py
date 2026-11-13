
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL

from app.main import app
from app.database.connection import (
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_HOST,
    POSTGRES_PORT,
    get_db,
)


@pytest.fixture
def test_client():
    test_url = URL.create(
        "postgresql+psycopg2",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=int(POSTGRES_PORT),
        database="devops_ai_test",
    )

    test_engine = create_engine(test_url)
    connection = test_engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        transaction.rollback()
        connection.close()
        test_engine.dispose()


def test_device_pairing_and_revocation(test_client, monkeypatch):
    unique_id = uuid.uuid4().hex
    email = f"{unique_id}@example.com"
    username = f"user_{unique_id[:12]}"
    password = "TestPassword123!"

    # Mock Resend and capture the verification code.
    verification = {}

    monkeypatch.setattr(
        "app.api.auth_routes.send_verification_email",
        lambda email, code: verification.update(code=code),
)

    # Register a test user.
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": email,
            "username": username,
            "password": password,
        },
    )
    assert response.status_code == 201
    assert "code" in verification

    # Verify the email.
    response = test_client.post(
        "/api/auth/verify-email",
        json={"email": email, "code": verification["code"]},
    )
    assert response.status_code == 200
    assert response.json()["verified"] is True

    # Log in.
    response = test_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200

    access_token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Create a pairing code.
    response = test_client.post(
        "/api/devices/pairing",
        headers=headers,
    )
    assert response.status_code == 200
    pairing_code = response.json()["code"]
    assert len(pairing_code) == 32

    # Claim the pairing code.
    response = test_client.post(
        "/api/devices/claim",
        json={
            "code": pairing_code,
            "device_name": "Integration Test PC",
            "operating_system": "Windows 11",
        },
    )
    assert response.status_code == 200
    result = response.json()
    device_id = result["device_id"]
    assert result["device_token"]

    # Check that the pairing code cannot be reused.
    response = test_client.post(
        "/api/devices/claim",
        json={
            "code": pairing_code,
            "device_name": "Another PC",
            "operating_system": "Linux",
        },
    )
    assert response.status_code == 400

    # List devices.
    response = test_client.get("/api/devices/", headers=headers)
    assert response.status_code == 200
    assert any(device["id"] == device_id for device in response.json())

    # Revoke the device.
    response = test_client.delete(
        f"/api/devices/{device_id}",
        headers=headers,
    )
    assert response.status_code == 204

    # Confirm it is inactive.
    response = test_client.get("/api/devices/", headers=headers)
    assert response.status_code == 200

    device = next(
        device for device in response.json()
        if device["id"] == device_id
    )
    assert device["is_active"] is False
def test_unverified_user_cannot_login(test_client, monkeypatch):
    unique_id = uuid.uuid4().hex

    monkeypatch.setattr(
        "app.api.auth_routes.send_verification_email",
        lambda email, token: None,
    )

    # Register an account without verifying its email.
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": f"{unique_id}@example.com",
            "username": f"user_{unique_id[:12]}",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 201

    # Attempt login without email verification.
    response = test_client.post(
        "/api/auth/login",
        json={
            "email": f"{unique_id}@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 403
    assert "verify your email" in response.json()["detail"].lower()