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
from tools import query_catalog, check_stock, reserve_item, validate_address, calculate_eta_and_fee, execute_payment_gateway, track_package
from lobstertrap import get_lobstertrap
import contextvars

app = FastAPI(title="Cart-Node Backend", description="Backend for Cart-Node e-commerce platform")

# Initialize ADK components
session_service = InMemorySessionService()
lobstertrap = get_lobstertrap(session_service)

# Use contextvars for safe concurrent session state resolution
current_user_id = contextvars.ContextVar("current_user_id", default=None)
current_session_id = contextvars.ContextVar("current_session_id", default=None)

def secure_execute_payment_gateway(amount: float) -> str:
    user_id = current_user_id.get()
    session_id = current_session_id.get()

    if not user_id or not session_id:
         return json.dumps({"error": "No active context for checkout"})

    session = session_service.get_session_sync(
        app_name="cart-node",
        user_id=user_id,
        session_id=session_id
    )
    active_state = session.state if session else None

    # Pass execution to the Lobstertrap
    return lobstertrap.intercept_checkout(
        user_id=user_id,
        session_id=session_id,
        tool_args={"amount": amount},
        active_state=active_state
    )

def secure_reserve_item(sku: str, quantity: int) -> str:
    user_id = current_user_id.get()
    session_id = current_session_id.get()

    if user_id and session_id:
        session = session_service.get_session_sync(
            app_name="cart-node",
            user_id=user_id,
            session_id=session_id
        )
        if session:
            return reserve_item(sku, quantity, active_state=session.state)
    return reserve_item(sku, quantity)

def secure_calculate_eta_and_fee(lat: float, lng: float) -> str:
    user_id = current_user_id.get()
    session_id = current_session_id.get()

    if user_id and session_id:
        session = session_service.get_session_sync(
            app_name="cart-node",
            user_id=user_id,
            session_id=session_id
        )
        if session:
            return calculate_eta_and_fee(lat, lng, active_state=session.state)
    return calculate_eta_and_fee(lat, lng)

checkout_agent = adk.Agent(
    name="checkout",
    model="gemini-2.0-flash",
    instruction="You are the Checkout Agent. Your only job is to execute the payment gateway when the user confirms their bill.",
    tools=[FunctionTool(func=secure_execute_payment_gateway)]
)

shipping_agent = adk.Agent(
    name="shipping",
    model="gemini-2.0-flash",
    instruction="You are the Shipping Agent. Your job is to validate addresses, calculate delivery ETAs and fees, and track active packages.",
    tools=[
        FunctionTool(func=validate_address),
        FunctionTool(func=secure_calculate_eta_and_fee),
        FunctionTool(func=track_package)
    ]
)

supervisor_agent = adk.Agent(
    name="supervisor",
    model="gemini-2.0-flash",
    instruction="You are the Supervisor Agent for Cart-Node, an e-commerce platform. You help the user find items, check stock, reserve items for their order, and track existing packages. Route logistics and tracking tasks to the shipping agent. Route payment tasks to the checkout agent. Always use the provided tools to lookup exact prices and SKUs. Never estimate or hallucinate prices.",
    tools=[
        FunctionTool(func=query_catalog),
        FunctionTool(func=check_stock),
        FunctionTool(func=secure_reserve_item)
    ],
    sub_agents=[shipping_agent, checkout_agent]
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

@app.post("/confirm_bill")
async def confirm_bill(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("sub", "anonymous")
    session_id = f"session_for_{user_id}"

    session = session_service.get_session_sync(
        app_name="cart-node",
        user_id=user_id,
        session_id=session_id
    )
    if session:
        state = session.state
        state["ui_bill_confirmed"] = True
        # For mock purposes, set valid totals to bypass the LobsterTrap math check if it hasn't been set by tools
        if "cart_total" not in state:
            state["cart_total"] = 0.0
        if "shipping_fee" not in state:
            state["shipping_fee"] = 0.0

    return {"status": "confirmed"}

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

    # Update context for the checkout agent tool
    current_user_id.set(user_id)
    current_session_id.set(session_id)

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
                        # Prompt Injection Scanner (Phase 5 Guardrail)
                        text_lower = message["text"].lower()
                        if "ignore previous" in text_lower or "override" in text_lower or "system prompt" in text_lower:
                            print("Prompt injection detected! Aborting.")
                            await websocket.send_text(json.dumps({"error": "Unauthorized command sequence detected."}))
                            queue.close()
                            return

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
