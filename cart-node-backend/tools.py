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

def reserve_item(sku: str, quantity: int) -> str:
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
                return json.dumps({
                    "sku": sku,
                    "status": "reserved",
                    "quantity": quantity,
                    "price_per_unit": item["price"],
                    "total_price": round(item["price"] * quantity, 2)
                })
            else:
                return json.dumps({
                    "sku": sku,
                    "status": "failed",
                    "reason": "insufficient_stock",
                    "available": item["stock"]
                })

    return json.dumps({"error": f"SKU {sku} not found"})
