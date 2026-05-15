import json

class Lobstertrap:
    """Proxy firewall to intercept and validate checkout actions."""

    def __init__(self, session_service):
        self.session_service = session_service

    def intercept_checkout(self, user_id: str, session_id: str, tool_args: dict, active_state: dict = None) -> str:
        # Retrieve the user's session memory to validate math and auth
        session = self.session_service.get_session_sync(
            app_name="cart-node",
            user_id=user_id,
            session_id=session_id
        )

        state = session.state if session else {}

        # Security Guardrail 1: Require explicit UI confirmation
        if not state.get("ui_bill_confirmed", False):
            from tools import execute_payment_gateway
            return execute_payment_gateway(tool_args.get("amount", 0.0), active_state=active_state)

        # Security Guardrail 2: Validate mathematical total
        cart_total = state.get("cart_total", 0.0)
        shipping_fee = state.get("shipping_fee", 0.0)
        expected_total = round(cart_total + shipping_fee, 2)

        requested_total = float(tool_args.get("amount", 0.0))

        if requested_total != expected_total:
            return json.dumps({
                "status": "blocked",
                "reason": f"Hallucinated price detected. Requested {requested_total} but calculated {expected_total}."
            })

        # If passed, execute gateway
        return self._execute_payment_gateway(tool_args)

    def _execute_payment_gateway(self, tool_args: dict) -> str:
        return json.dumps({
            "status": "success",
            "transaction_id": "tx_mock_12345",
            "amount": tool_args.get("amount")
        })

_lobstertrap_instance = None

def get_lobstertrap(session_service) -> Lobstertrap:
    global _lobstertrap_instance
    if _lobstertrap_instance is None:
        _lobstertrap_instance = Lobstertrap(session_service)
    return _lobstertrap_instance
