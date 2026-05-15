from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from auth import create_token, verify_token
import os
import json
import asyncio
from google import genai
from google.genai import types
from google import adk
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue, LiveRequest
from google.adk.tools import FunctionTool
from tools import query_catalog, check_stock, reserve_item

app = FastAPI(title="Cart-Node Backend", description="Backend for Cart-Node e-commerce platform")

# Initialize ADK components
session_service = InMemorySessionService()
supervisor_agent = adk.Agent(
    name="supervisor",
    model="gemini-2.0-flash",
    instruction="You are the Supervisor Agent for Cart-Node, an e-commerce platform. You help the user find items, check stock, and reserve items for their order. Always use the provided tools to lookup exact prices and SKUs. Never estimate or hallucinate prices.",
    tools=[
        FunctionTool(func=query_catalog),
        FunctionTool(func=check_stock),
        FunctionTool(func=reserve_item)
    ]
)

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
        user_info = verify_ws_token(token)
        user_id = user_info.get("sub", "anonymous")
    except Exception as e:
        await websocket.close(code=1008, reason=f"Auth failed: {str(e)}")
        return

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        await websocket.send_text(json.dumps({"error": "Gemini API key not configured"}))
        await websocket.close(code=1011)
        return

    # Use the authenticated user's ID to maintain a consistent session
    # across multiple WebSocket connections
    session_id = f"session_for_{user_id}"

    runner = adk.Runner(
        app_name="cart-node",
        agent=supervisor_agent,
        session_service=session_service,
    )

    queue = LiveRequestQueue()

    try:
        # Task 1: Read from WebSocket (client audio & text) and send to Queue
        async def receive_from_client():
            try:
                while True:
                    message = await websocket.receive()
                    if "text" in message:
                        try:
                            data = json.loads(message["text"])
                            if data.get("type") == "end_of_turn":
                                # Send turn complete signal
                                queue.send(LiveRequest(content=types.LiveClientContent(turn_complete=True)))
                            elif data.get("type") == "close":
                                queue.close()
                                return
                        except Exception:
                            pass
                    elif "bytes" in message:
                        data = message["bytes"]
                        # Send PCM audio to Gemini
                        blob = types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                        queue.send_realtime(blob)
            except WebSocketDisconnect:
                print("Client disconnected")
                queue.close()
            except Exception as e:
                print(f"Error receiving from client: {e}")
                queue.close()

        # Task 2: Read from ADK runner and send to WebSocket
        async def receive_from_adk():
            try:
                async for event in runner.run_live(
                    user_id=user_id,
                    session_id=session_id,
                    live_request_queue=queue
                ):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                await websocket.send_text(json.dumps({"type": "text", "data": part.text}))
                            if part.inline_data:
                                await websocket.send_bytes(part.inline_data.data)
                                await websocket.send_text(json.dumps({"type": "audio_metadata", "mime_type": part.inline_data.mime_type}))

                    if event.turn_complete:
                        await websocket.send_text(json.dumps({"type": "turn_complete"}))

                    if event.error_message:
                        await websocket.send_text(json.dumps({"error": event.error_message}))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Error receiving from ADK: {e}")
                try:
                    await websocket.send_text(json.dumps({"error": str(e)}))
                except:
                    pass

        # Run both tasks concurrently
        t1 = asyncio.create_task(receive_from_client())
        t2 = asyncio.create_task(receive_from_adk())

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
            await runner.close()
            await websocket.close()
        except:
            pass


def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
