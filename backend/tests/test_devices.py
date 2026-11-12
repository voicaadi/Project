
from app.api.device_routes import PairingClaim


def test_pairing_code_requires_32_characters():
    valid = PairingClaim(
        code="A" * 32,
        device_name="Test PC",
        operating_system="Windows 11",
    )

    assert len(valid.code) == 32


def test_pairing_code_rejects_short_code():
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        PairingClaim(
            code="ABC123",
            device_name="Test PC",
            operating_system="Windows 11",
        )
