from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from auth import create_token, verify_token
import os
import json
import asyncio
from google import genai
from google.genai import types

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

def verify_ws_token(token: str) -> dict:
    try:
        return verify_token(token)
    except Exception as e:
        raise ValueError(str(e))

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


@app.websocket("/live/audio")
async def live_audio_endpoint(websocket: WebSocket):
    await websocket.accept()

    # 1. Expect the first message to be the auth token
    try:
        auth_message = await websocket.receive_text()
        auth_data = json.loads(auth_message)
        token = auth_data.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing token")
            return
        verify_ws_token(token)
    except Exception as e:
        await websocket.close(code=1008, reason=f"Auth failed: {str(e)}")
        return

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        await websocket.send_text(json.dumps({"error": "Gemini API key not configured"}))
        await websocket.close(code=1011)
        return

    # 2. Connect to Gemini Live API
    try:
        client = genai.Client(api_key=gemini_api_key)

        # Configure Gemini
        config = types.LiveConnectConfig(
            system_instruction=types.Content(parts=[types.Part.from_text(text="You are the Supervisor Agent for Cart-Node, an e-commerce platform. You help the user place orders. Please be brief and helpful.")]),
        )

        # We use a context manager for the Live API
        async with client.aio.live.connect(model="gemini-2.0-flash", config=config) as session:

            # Task 1: Read from WebSocket (client audio & text) and send to Gemini
            async def receive_from_client():
                try:
                    while True:
                        message = await websocket.receive()
                        if "text" in message:
                            try:
                                data = json.loads(message["text"])
                                if data.get("type") == "end_of_turn":
                                    await session.send(end_of_turn=True)
                                elif data.get("type") == "close":
                                    # Client specifically requests closure
                                    return
                            except Exception:
                                pass
                        elif "bytes" in message:
                            data = message["bytes"]
                            # Send PCM audio to Gemini WITHOUT end_of_turn=True
                            await session.send(input={"data": data, "mime_type": "audio/pcm;rate=16000"}, end_of_turn=False)
                except WebSocketDisconnect:
                    print("Client disconnected")
                except Exception as e:
                    print(f"Error receiving from client: {e}")

            # Task 2: Read from Gemini and send to WebSocket (text/audio back to client)
            async def receive_from_gemini():
                try:
                    async for response in session.receive():
                        server_content = response.server_content
                        if server_content is not None:
                            model_turn = server_content.model_turn
                            if model_turn is not None:
                                for part in model_turn.parts:
                                    if part.text:
                                        # Stream text back to the client
                                        await websocket.send_text(json.dumps({"type": "text", "data": part.text}))
                                    if part.inline_data:
                                        # Stream audio bytes back to the client if the model returns audio
                                        await websocket.send_bytes(part.inline_data.data)
                                        # Also send a signal that audio chunk arrived
                                        await websocket.send_text(json.dumps({"type": "audio_metadata", "mime_type": part.inline_data.mime_type}))

                            if server_content.turn_complete:
                                await websocket.send_text(json.dumps({"type": "turn_complete"}))
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Error receiving from Gemini: {e}")
                    try:
                        await websocket.send_text(json.dumps({"error": str(e)}))
                    except:
                        pass

            # Run both tasks concurrently
            t1 = asyncio.create_task(receive_from_client())
            t2 = asyncio.create_task(receive_from_gemini())

            # Wait for either the client to close (or error), or gemini stream to error
            done, pending = await asyncio.wait(
                [t1, t2],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

    except Exception as e:
        print(f"WebSocket session error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass


def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
