from fastapi.testclient import TestClient
from main import app

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
    # Check that it's a generic token validation failure since
    # invalid.token.string causes an incorrect padding / decode error or signature failure depending on the mock string
    assert "Token validation failed" in response.json()["detail"]
