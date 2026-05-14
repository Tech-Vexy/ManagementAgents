from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from main import app
import json
import pytest

client = TestClient(app)

def test_login_success():
    response = client.post("/login", json={"username": "testuser", "password": "password"})
    assert response.status_code == 200
    assert "token" in response.json()

def test_login_failure():
    response = client.post("/login", json={"username": "wronguser", "password": "password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_verify_success():
    # Login first to get token
    login_response = client.post("/login", json={"username": "testuser", "password": "password"})
    token = login_response.json()["token"]

    # Verify token
    response = client.get("/verify", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["sub"] == "testuser"

def test_verify_missing_token():
    response = client.get("/verify")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header missing"

def test_verify_invalid_token():
    response = client.get("/verify", headers={"Authorization": "Bearer invalid.token.string"})
    assert response.status_code == 401
    assert "Token validation failed" in response.json()["detail"]

def test_websocket_missing_auth():
    # The websocket expects the first text frame to be JSON containing the token
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/live/audio") as websocket:
            websocket.send_text(json.dumps({}))
            # Should disconnect with 1008
            websocket.receive_text()

    assert e.value.code == 1008

def test_websocket_invalid_auth():
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/live/audio") as websocket:
            websocket.send_text(json.dumps({"token": "bad.token.data"}))
            websocket.receive_text()

    assert e.value.code == 1008

def test_websocket_auth_success_no_api_key():
    login_response = client.post("/login", json={"username": "testuser", "password": "password"})
    token = login_response.json()["token"]

    # Since GEMINI_API_KEY is not set in our test environment, it should auth successfully
    # but then close the connection with a 1011 after sending an error message.
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/live/audio") as websocket:
            websocket.send_text(json.dumps({"token": token}))
            msg = websocket.receive_text()
            assert "Gemini API key not configured" in msg
            websocket.receive_text() # Trigger the actual close

    assert e.value.code == 1011
