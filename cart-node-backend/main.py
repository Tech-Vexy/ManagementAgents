from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional
from auth import create_token, verify_token

app = FastAPI(title="Cart-Node Backend", description="Backend for Cart-Node e-commerce platform")

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str

class UserInfo(BaseModel):
    username: str

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    token = authorization.split(" ")[1]

    try:
        payload = verify_token(token)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    # In a real app, verify against DB
    if request.username == "testuser" and request.password == "password":
        token = create_token({"sub": request.username, "role": "user"})
        return LoginResponse(token=token)
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/verify")
async def verify(current_user: dict = Depends(get_current_user)):
    return {"message": "Token is valid", "user": current_user}

def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
