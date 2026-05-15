from lobstertrap import Lobstertrap
from google.adk.sessions import InMemorySessionService
import json

def test_lobstertrap_blocks_unauthorized():
    session_service = InMemorySessionService()
    session_service.create_session_sync(app_name="cart-node", user_id="user1", session_id="sess1", state={})

    trap = Lobstertrap(session_service)
    result_str = trap.intercept_checkout("user1", "sess1", {"amount": 50.0})
    result = json.loads(result_str)

    assert result["signal"] == "present_bill"
    assert result["amount"] == 50.0

def test_lobstertrap_blocks_bad_math():
    session_service = InMemorySessionService()
    session_service.create_session_sync(
        app_name="cart-node",
        user_id="user2",
        session_id="sess2",
        state={"ui_bill_confirmed": True, "cart_total": 45.0, "shipping_fee": 5.0}
    )

    trap = Lobstertrap(session_service)

    # Try to charge 100 instead of 50
    result_str = trap.intercept_checkout("user2", "sess2", {"amount": 100.0})
    result = json.loads(result_str)

    assert result["status"] == "blocked"
    assert "Hallucinated price detected" in result["reason"]

def test_lobstertrap_allows_valid():
    session_service = InMemorySessionService()
    session_service.create_session_sync(
        app_name="cart-node",
        user_id="user3",
        session_id="sess3",
        state={"ui_bill_confirmed": True, "cart_total": 45.0, "shipping_fee": 5.0}
    )

    trap = Lobstertrap(session_service)

    result_str = trap.intercept_checkout("user3", "sess3", {"amount": 50.0})
    result = json.loads(result_str)

    assert result["status"] == "success"
    assert "transaction_id" in result
