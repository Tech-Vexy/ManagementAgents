import base64
import json
import hmac
import hashlib
import time
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_dev_key")

def _base64url_encode(data: bytes) -> str:
    """Encodes bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _base64url_decode(b64_str: str) -> bytes:
    """Decodes base64url string with or without padding."""
    padding_len = (4 - len(b64_str) % 4) % 4
    padding = b'=' * padding_len
    return base64.urlsafe_b64decode(b64_str.encode('utf-8') + padding)

def create_token(payload: dict, expires_in_seconds: int = 3600) -> str:
    """Generates a custom JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}

    # Add expiration to payload
    payload_copy = payload.copy()
    payload_copy["exp"] = int(time.time()) + expires_in_seconds

    header_b64 = _base64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_b64 = _base64url_encode(json.dumps(payload_copy, separators=(',', ':')).encode('utf-8'))

    signature_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(SECRET_KEY.encode('utf-8'), signature_input, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"

def verify_token(token: str) -> dict:
    """Verifies a custom JWT token and returns the payload if valid."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signature_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_signature = hmac.new(SECRET_KEY.encode('utf-8'), signature_input, hashlib.sha256).digest()
        expected_signature_b64 = _base64url_encode(expected_signature)

        if not hmac.compare_digest(signature_b64, expected_signature_b64):
            raise ValueError("Invalid signature")

        # Decode and verify payload
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))

        # Check expiration
        if "exp" in payload:
            if payload["exp"] < int(time.time()):
                raise ValueError("Token has expired")

        return payload
    except Exception as e:
        raise ValueError(f"Token validation failed: {str(e)}")
