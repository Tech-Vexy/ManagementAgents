import json
import os

CATALOG_FILE = os.path.join(os.path.dirname(__file__), "catalog.json")

def load_catalog() -> dict:
    try:
        with open(CATALOG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"items": []}

def query_catalog(query: str) -> str:
    """Queries the catalog for items matching a search query.

    Args:
        query: The search term to look for in the catalog.

    Returns:
        A JSON string containing the matching items with their exact SKUs and prices.
    """
    catalog = load_catalog()
    query_lower = query.lower()
    results = []

    for item in catalog.get("items", []):
        if query_lower in item.get("name", "").lower() or query_lower in item.get("description", "").lower():
            results.append({
                "sku": item["sku"],
                "name": item["name"],
                "price": item["price"]
            })

    return json.dumps({"results": results})

def check_stock(sku: str) -> str:
    """Checks the available stock for a specific item SKU.

    Args:
        sku: The exact SKU of the item.

    Returns:
        A JSON string indicating the stock level or an error if not found.
    """
    catalog = load_catalog()
    for item in catalog.get("items", []):
        if item.get("sku") == sku:
            return json.dumps({
                "sku": sku,
                "in_stock": item["stock"] > 0,
                "quantity": item["stock"]
            })

    return json.dumps({"error": f"SKU {sku} not found"})

def track_package(order_id: str) -> str:
    """Tracks the shipping status of an order.

    Args:
        order_id: The ID of the order to track.

    Returns:
        A JSON string containing the package status, coordinates, and emitting a UI signal.
    """
    # Mocking package tracking response
    return json.dumps({
        "order_id": order_id,
        "status": "Out for Delivery",
        "eta": "2:30 PM",
        "current_coordinates": {"lat": 40.7128, "lng": -74.0060},
        "signal": "track_package"
    })


def validate_address(address: str) -> str:
    """Validates the user's shipping address.

    Args:
        address: The shipping address provided by the user.

    Returns:
        A JSON string containing the validated address details and coordinates.
    """
    # Mocking Google Places API validation
    return json.dumps({
        "status": "valid",
        "formatted_address": f"{address} (Validated)",
        "coordinates": {"lat": 40.7128, "lng": -74.0060},
        "signal": "request_address" # Tells Android to optionally open Places Autocomplete
    })

def calculate_eta_and_fee(lat: float, lng: float, active_state: dict = None) -> str:
    """Calculates the estimated time of arrival and delivery fee based on coordinates.

    Args:
        lat: Latitude of the destination.
        lng: Longitude of the destination.

    Returns:
        A JSON string containing the dynamic delivery fee and ETA, emitting the UI signal.
    """
    # Mocking Google Maps SDK distance calculation
    distance_miles = 5.2
    fee = round(2.00 + (distance_miles * 0.50), 2)

    if active_state is not None:
        active_state["shipping_fee"] = fee

    return json.dumps({
        "distance_miles": distance_miles,
        "eta_minutes": 15,
        "delivery_fee": fee,
        "signal": "trigger_maps_ui" # Tells Android to expand MapView
    })

def execute_payment_gateway(amount: float, active_state: dict = None) -> str:
    """Executes the payment gateway transaction.

    Args:
        amount: The total float amount to be charged.

    Returns:
        A JSON string indicating the success of the transaction.
    """
    items = []
    shipping_fee = 0.0
    if active_state:
        items = active_state.get("items", [])
        shipping_fee = active_state.get("shipping_fee", 0.0)

    return json.dumps({
        "signal": "present_bill",
        "amount": amount,
        "items": items,
        "shipping_fee": shipping_fee
    })

def reserve_item(sku: str, quantity: int, active_state: dict = None) -> str:
    """Reserves a specific quantity of an item for checkout.

    Args:
        sku: The exact SKU of the item.
        quantity: The number of items to reserve.

    Returns:
        A JSON string confirming the reservation or indicating failure.
    """
    catalog = load_catalog()
    for item in catalog.get("items", []):
        if item.get("sku") == sku:
            if item["stock"] >= quantity:
                total_price = round(item["price"] * quantity, 2)
                if active_state is not None:
                    cart_total = active_state.get("cart_total", 0.0)
                    active_state["cart_total"] = cart_total + total_price
                    # Keep track of items for the receipt
                    items = active_state.get("items", [])
                    items.append({"name": item["name"], "price": total_price})
                    active_state["items"] = items

                return json.dumps({
                    "sku": sku,
                    "status": "reserved",
                    "quantity": quantity,
                    "price_per_unit": item["price"],
                    "total_price": total_price
                })
            else:
                return json.dumps({
                    "sku": sku,
                    "status": "failed",
                    "reason": "insufficient_stock",
                    "available": item["stock"]
                })

    return json.dumps({"error": f"SKU {sku} not found"})
