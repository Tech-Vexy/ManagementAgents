import pytest
import time
from auth import create_token, verify_token

def test_token_creation_and_verification():
    payload = {"sub": "testuser", "role": "admin"}
    token = create_token(payload)

    assert token is not None
    assert len(token.split(".")) == 3

    decoded = verify_token(token)
    assert decoded["sub"] == "testuser"
    assert decoded["role"] == "admin"
    assert "exp" in decoded

def test_token_expiration():
    payload = {"sub": "testuser"}
    # Create token that expires immediately
    token = create_token(payload, expires_in_seconds=-1)

    with pytest.raises(ValueError, match="Token has expired"):
        verify_token(token)

def test_invalid_signature():
    payload = {"sub": "testuser"}
    token = create_token(payload)

    # Tamper with the token
    parts = token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.invalid_signature"

    with pytest.raises(ValueError, match="Invalid signature"):
        verify_token(tampered_token)

def test_invalid_format():
    with pytest.raises(ValueError, match="Invalid token format"):
        verify_token("invalid.token")
