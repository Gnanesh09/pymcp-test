from typing import Any


def public_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": product["_id"],
        "name": product["name"],
        "brand": product["brand"],
        "category": product["category"],
        "price_paise": product["price_paise"],
        "price": round(product["price_paise"] / 100, 2),
        "mrp_paise": product["mrp_paise"],
        "rating": product["rating"],
        "stock": product["stock"],
        "unit": product["unit"],
        "description": product["description"],
        "image": product["image"],
    }


def public_agent(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": agent["_id"],
        "name": agent["name"],
        "description": agent.get("description"),
        "status": agent["status"],
        "balance_available_paise": agent.get("balance_available_paise", 0),
        "balance_reserved_paise": agent.get("balance_reserved_paise", 0),
        "balance_available": round(
            agent.get("balance_available_paise", 0) / 100, 2
        ),
        "policy": agent.get("policy", {}),
        "created_at": agent.get("created_at"),
        "updated_at": agent.get("updated_at"),
    }
