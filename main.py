from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pymongo import AsyncMongoClient, ReturnDocument

from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.transport_security import TransportSecuritySettings


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "QuickCart Agentic Commerce"
APP_VERSION = "4.0.0"

PUBLIC_HOST = os.getenv(
    "PUBLIC_HOST",
    "pymcp-test.onrender.com",
).strip()

PUBLIC_BASE_URL = (
    f"https://{PUBLIC_HOST}"
)

MCP_URL = (
    f"{PUBLIC_BASE_URL}/mcp"
)

TIMEZONE = ZoneInfo("Asia/Kolkata")

# MongoDB
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "",
).strip()

MONGODB_DB = os.getenv(
    "MONGODB_DB",
    "quickcart",
).strip()

# Razorpay standard Test Mode
RAZORPAY_KEY_ID = os.getenv(
    "RAZORPAY_KEY_ID",
    "",
).strip()

RAZORPAY_KEY_SECRET = os.getenv(
    "RAZORPAY_KEY_SECRET",
    "",
).strip()

RAZORPAY_API_BASE = (
    "https://api.razorpay.com/v1"
)

# IMPORTANT:
#
# SIMULATED:
#     Fully autonomous demo rail.
#     No human interaction.
#
# RAZORPAY_CHECKOUT:
#     Normal Razorpay Checkout.
#     Requires a human.
#
# RAZORPAY_RESERVE_PAY:
#     Intended production autonomous rail,
#     but must only be enabled after Razorpay
#     activates Reserve Pay for your account.
#
AUTONOMOUS_PAYMENT_MODE = os.getenv(
    "AUTONOMOUS_PAYMENT_MODE",
    "SIMULATED",
).strip().upper()

DEFAULT_AGENT_ID = (
    "agent_demo_grocery"
)

DEFAULT_USER_ID = (
    "demo-user"
)

DEFAULT_MERCHANT_ID = (
    "quickcart"
)

PRODUCT_UI_URI = (
    "ui://quickcart/product-catalogue.html"
)

BASE_DIR = Path(__file__).resolve().parent

PRODUCT_UI_FILE = (
    BASE_DIR / "product_catalogue.html"
)


# ============================================================
# MONGODB
# ============================================================

mongo_client: AsyncMongoClient | None = None
db = None

agents_collection = None
policies_collection = None
products_collection = None
carts_collection = None
orders_collection = None
payments_collection = None
spend_collection = None
runs_collection = None
audit_collection = None


# ============================================================
# DEFAULT PRODUCTS
#
# Seeded into MongoDB once.
# ============================================================

DEFAULT_PRODUCTS: list[dict[str, Any]] = [
    {
        "_id": "p001",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Aashirvaad Atta 5kg",
        "brand": "Aashirvaad",
        "category": "grocery",
        "price": 289,
        "mrp": 320,
        "discount": 10,
        "rating": 4.5,
        "stock": 50,
        "unit": "5 kg",
        "description": "Premium whole wheat flour.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQi8qXYSl439pmbK5h5T8GcGYJtQtRkxrnKDYbCRYy7aQ&s=10",
        "tags": [
            "atta",
            "flour",
            "wheat",
            "grocery",
        ],
        "active": True,
    },
    {
        "_id": "p002",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Tata Salt 1kg",
        "brand": "Tata",
        "category": "grocery",
        "price": 28,
        "mrp": 30,
        "discount": 7,
        "rating": 4.7,
        "stock": 100,
        "unit": "1 kg",
        "description": "Iodised vacuum evaporated salt.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRa7lkQncRgI3d52YGb2MGmsofKoauTJoLvrJaBUWppVg&s=10",
        "tags": [
            "salt",
            "grocery",
        ],
        "active": True,
    },
    {
        "_id": "p003",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Amul Taaza Milk 1L",
        "brand": "Amul",
        "category": "dairy",
        "price": 62,
        "mrp": 66,
        "discount": 6,
        "rating": 4.8,
        "stock": 40,
        "unit": "1 litre",
        "description": "Fresh toned milk.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSGaiqZ-X_6OZLVY0cbRoHSLv-u_YsbqtBAm_C6RggvLA&s=10",
        "tags": [
            "milk",
            "dairy",
            "breakfast",
        ],
        "active": True,
    },
    {
        "_id": "p004",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Amul Butter 500g",
        "brand": "Amul",
        "category": "dairy",
        "price": 285,
        "mrp": 310,
        "discount": 8,
        "rating": 4.8,
        "stock": 25,
        "unit": "500 g",
        "description": "Pasteurised table butter.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTtZt3ju1kB5B4tsHu3KrQ-PRVe5xcSBXBf9NZbEPlF_A&s",
        "tags": [
            "butter",
            "dairy",
        ],
        "active": True,
    },
    {
        "_id": "p005",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Maggi 2-Minute Noodles",
        "brand": "Nestle",
        "category": "snacks",
        "price": 14,
        "mrp": 15,
        "discount": 7,
        "rating": 4.6,
        "stock": 200,
        "unit": "70 g",
        "description": "Instant noodles.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT1YIdP9S9iKozp1c7D3XMZjK4riYeeLQD1kac9QMpV5Q&s=10",
        "tags": [
            "maggi",
            "noodles",
            "instant",
            "snacks",
        ],
        "active": True,
    },
    {
        "_id": "p006",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Lay's Magic Masala",
        "brand": "Lay's",
        "category": "snacks",
        "price": 20,
        "mrp": 20,
        "discount": 0,
        "rating": 4.4,
        "stock": 120,
        "unit": "50 g",
        "description": "Spicy potato chips.",
        "image": "https://banerjeesupermarket.com/wp-content/uploads/2026/04/81rQQr3BvWL._SL1500_-600x723.jpg",
        "tags": [
            "chips",
            "snacks",
        ],
        "active": True,
    },
    {
        "_id": "p007",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Coca-Cola 750ml",
        "brand": "Coca-Cola",
        "category": "beverages",
        "price": 40,
        "mrp": 45,
        "discount": 11,
        "rating": 4.3,
        "stock": 80,
        "unit": "750 ml",
        "description": "Carbonated soft drink.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTmgriAj9WTl8bqGCJRG7uQd5F19pEuYH4mn_1ryHIYKg&s=10",
        "tags": [
            "coke",
            "drink",
            "beverage",
            "soft drink",
        ],
        "active": True,
    },
    {
        "_id": "p008",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Red Bull Energy Drink",
        "brand": "Red Bull",
        "category": "beverages",
        "price": 125,
        "mrp": 135,
        "discount": 7,
        "rating": 4.5,
        "stock": 35,
        "unit": "250 ml",
        "description": "Energy drink.",
        "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTEHbTunV3BTGk2CFf6WaoWWYYPa1QyQQz8tSYKrmlXCA&s=10",
        "tags": [
            "energy",
            "drink",
            "beverage",
        ],
        "active": True,
    },
    {
        "_id": "p009",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Surf Excel Matic 2kg",
        "brand": "Surf Excel",
        "category": "household",
        "price": 365,
        "mrp": 420,
        "discount": 13,
        "rating": 4.6,
        "stock": 20,
        "unit": "2 kg",
        "description": "Detergent powder for washing machines.",
        "image": "https://encrypted-tbn1.gstatic.com/shopping?q=tbn:ANd9GcS1xQGzDp2BZq8vjTvS7Wrp3vrWNSOUbNsEozv_8vS3ZqSv9XnD40lVVttATUuNMGT1SCy6FeRGQLPdvOtO5qs9dCyieobHF60qcedA9hNwG-7xpf2gvD0Wqz4567YIsm7wq2xlP8o&usqp=CAc",
        "tags": [
            "detergent",
            "washing",
            "household",
        ],
        "active": True,
    },
    {
        "_id": "p010",
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Colgate MaxFresh",
        "brand": "Colgate",
        "category": "personal-care",
        "price": 99,
        "mrp": 115,
        "discount": 14,
        "rating": 4.5,
        "stock": 60,
        "unit": "150 g",
        "description": "Fresh breath toothpaste.",
        "image": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:ANd9GcQcGOP1-iLFVa741jL0HGPQJ0gsGmOsrFrXmiEAL4dQ97K04aljr25r9RvaSFCgk76RD7ep9UwAxO3nZdpA2Ny1c6u_p2igD8Yf7oDjyr59NbmfcYcyJKrSpQ",
        "tags": [
            "toothpaste",
            "personal care",
        ],
        "active": True,
    },
]


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_key() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(
        r"[^a-z0-9\s-]",
        " ",
        text,
    )
    return re.sub(
        r"\s+",
        " ",
        text,
    )


def json_safe(document: Any) -> Any:
    if isinstance(document, dict):
        return {
            str(k): json_safe(v)
            for k, v in document.items()
            if k != "_id"
        }

    if isinstance(document, list):
        return [
            json_safe(item)
            for item in document
        ]

    if isinstance(document, datetime):
        return document.isoformat()

    return document


def product_public(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": product["_id"],
        "name": product["name"],
        "brand": product["brand"],
        "category": product["category"],
        "price": product["price"],
        "mrp": product["mrp"],
        "discount": product["discount"],
        "rating": product["rating"],
        "stock": product["stock"],
        "unit": product["unit"],
        "description": product["description"],
        "image": product["image"],
    }


def build_cart(
    items: list[dict[str, Any]],
) -> dict[str, Any]:

    subtotal = sum(
        item["unit_price"] * item["quantity"]
        for item in items
    )

    delivery_fee = (
        39
        if 0 < subtotal < 499
        else 0
    )

    return {
        "items": items,
        "item_count": sum(
            item["quantity"]
            for item in items
        ),
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": subtotal + delivery_fee,
        "currency": "INR",
    }


def payment_mode_description() -> str:
    if AUTONOMOUS_PAYMENT_MODE == "SIMULATED":
        return (
            "Autonomous test rail. "
            "No real money moves."
        )

    if AUTONOMOUS_PAYMENT_MODE == "RAZORPAY_RESERVE_PAY":
        return (
            "Razorpay UPI Reserve Pay adapter. "
            "Requires account activation."
        )

    return (
        "Standard Razorpay Checkout. "
        "Human interaction required."
    )


# ============================================================
# AUDIT
# ============================================================

async def audit(
    event: str,
    *,
    agent_id: str | None = None,
    user_id: str | None = None,
    amount: int | None = None,
    status: str | None = None,
    reason: Any = None,
    data: dict[str, Any] | None = None,
) -> str:

    event_id = (
        f"evt_{uuid.uuid4().hex[:16]}"
    )

    await audit_collection.insert_one(
        {
            "_id": event_id,
            "event": event,
            "agent_id": agent_id,
            "user_id": user_id,
            "amount": amount,
            "status": status,
            "reason": reason,
            "data": data or {},
            "timestamp": now_utc(),
            "date": today_key(),
        }
    )

    return event_id


# ============================================================
# AGENT POLICY
# ============================================================

async def ensure_demo_agent() -> None:

    existing = await agents_collection.find_one(
        {
            "_id": DEFAULT_AGENT_ID,
        }
    )

    if existing:
        return

    agent = {
        "_id": DEFAULT_AGENT_ID,
        "user_id": DEFAULT_USER_ID,
        "merchant_id": DEFAULT_MERCHANT_ID,
        "name": "Grocery Autopilot",
        "status": "active",
        "created_at": now_utc(),
    }

    policy = {
        "_id": DEFAULT_AGENT_ID,
        "agent_id": DEFAULT_AGENT_ID,

        # THE USER'S REQUESTED DAILY LIMIT
        "daily_limit": 50000,

        # Harder per-transaction boundary.
        "per_transaction_limit": 10000,

        "allowed_categories": [
            "grocery",
            "snacks",
            "beverages",
            "dairy",
        ],

        "allowed_merchants": [
            DEFAULT_MERCHANT_ID,
        ],

        "auto_purchase": True,

        # Test rail.
        "payment_mode": (
            AUTONOMOUS_PAYMENT_MODE
        ),

        "created_at": now_utc(),
        "updated_at": now_utc(),
    }

    await agents_collection.insert_one(
        agent
    )

    await policies_collection.insert_one(
        policy
    )

    await audit(
        "AGENT_CREATED",
        agent_id=DEFAULT_AGENT_ID,
        user_id=DEFAULT_USER_ID,
        status="SUCCESS",
        reason="Initial autonomous grocery agent.",
        data={
            "daily_limit": 50000,
            "per_transaction_limit": 10000,
        },
    )


async def get_agent(
    agent_id: str,
) -> dict[str, Any] | None:

    return await agents_collection.find_one(
        {"_id": agent_id}
    )


async def get_policy(
    agent_id: str,
) -> dict[str, Any] | None:

    return await policies_collection.find_one(
        {"_id": agent_id}
    )


# ============================================================
# DAILY SPEND
# ============================================================

async def get_daily_spend(
    agent_id: str,
) -> int:

    document = (
        await spend_collection.find_one(
            {
                "_id": (
                    f"{agent_id}:{today_key()}"
                )
            }
        )
    )

    if not document:
        return 0

    return int(
        document.get("amount", 0)
    )


async def reserve_daily_spend(
    *,
    agent_id: str,
    amount: int,
    daily_limit: int,
) -> dict[str, Any] | None:

    spend_id = (
        f"{agent_id}:{today_key()}"
    )

    # Make sure today's record exists.
    await spend_collection.update_one(
        {"_id": spend_id},
        {
            "$setOnInsert": {
                "agent_id": agent_id,
                "date": today_key(),
                "amount": 0,
                "transaction_count": 0,
                "created_at": now_utc(),
            }
        },
        upsert=True,
    )

    # Atomic guard against concurrent overspending.
    result = await spend_collection.find_one_and_update(
        {
            "_id": spend_id,
            "amount": {
                "$lte": daily_limit - amount
            },
        },
        {
            "$inc": {
                "amount": amount,
                "transaction_count": 1,
            },
            "$set": {
                "updated_at": now_utc(),
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if result is None:
        return None

    return result


async def release_daily_spend(
    *,
    agent_id: str,
    amount: int,
) -> None:

    spend_id = (
        f"{agent_id}:{today_key()}"
    )

    await spend_collection.update_one(
        {"_id": spend_id},
        {
            "$inc": {
                "amount": -amount,
                "transaction_count": -1,
            }
        },
    )


# ============================================================
# POLICY ENGINE
# ============================================================

async def evaluate_purchase(
    *,
    agent_id: str,
    user_id: str,
    merchant_id: str,
    amount: int,
    categories: list[str],
) -> dict[str, Any]:

    policy = await get_policy(
        agent_id
    )

    if not policy:
        return {
            "decision": "BLOCK",
            "reason": "Agent policy not found.",
        }

    if not policy.get(
        "auto_purchase",
        False,
    ):
        return {
            "decision": "BLOCK",
            "reason": (
                "Autonomous purchasing is disabled."
            ),
        }

    if merchant_id not in policy.get(
        "allowed_merchants",
        [],
    ):
        return {
            "decision": "BLOCK",
            "reason": (
                "Merchant is not allowed by agent policy."
            ),
        }

    allowed_categories = set(
        policy.get(
            "allowed_categories",
            [],
        )
    )

    disallowed = [
        category
        for category in categories
        if category not in allowed_categories
    ]

    if disallowed:
        return {
            "decision": "BLOCK",
            "reason": (
                "One or more categories are blocked.",
            ),
            "disallowed_categories": disallowed,
        }

    per_transaction_limit = int(
        policy["per_transaction_limit"]
    )

    daily_limit = int(
        policy["daily_limit"]
    )

    if amount <= 0:
        return {
            "decision": "BLOCK",
            "reason": "Purchase amount must be positive.",
        }

    if amount > per_transaction_limit:
        return {
            "decision": "BLOCK",
            "reason": (
                f"₹{amount} exceeds the "
                f"₹{per_transaction_limit} "
                "per-transaction limit."
            ),
            "limits": {
                "transaction": per_transaction_limit,
                "daily": daily_limit,
            },
        }

    daily_spend = await get_daily_spend(
        agent_id
    )

    remaining = max(
        0,
        daily_limit - daily_spend,
    )

    if amount > remaining:
        return {
            "decision": "BLOCK",
            "reason": (
                f"Daily limit exceeded. "
                f"Remaining today: ₹{remaining}."
            ),
            "limits": {
                "daily": daily_limit,
                "spent_today": daily_spend,
                "remaining": remaining,
            },
        }

    return {
        "decision": "ALLOW",
        "reason": [
            "Autonomous purchase is enabled.",
            "Merchant is allowed.",
            "All categories are allowed.",
            (
                "Transaction is below "
                "per-transaction limit."
            ),
            (
                "Transaction is within "
                "today's remaining budget."
            ),
        ],
        "limits": {
            "daily": daily_limit,
            "spent_today": daily_spend,
            "remaining_before": remaining,
            "remaining_after": (
                remaining - amount
            ),
            "per_transaction": (
                per_transaction_limit
            ),
        },
    }


# ============================================================
# PRODUCT / BASKET
# ============================================================

async def load_products(
    product_ids: list[str],
) -> list[dict[str, Any]]:

    documents = await products_collection.find(
        {
            "_id": {
                "$in": product_ids
            },
            "active": True,
        }
    ).to_list(length=None)

    by_id = {
        product["_id"]: product
        for product in documents
    }

    return [
        by_id[product_id]
        for product_id in product_ids
        if product_id in by_id
    ]


async def build_basket(
    items: list[dict[str, Any]],
) -> dict[str, Any]:

    normalized_items = []

    for item in items:

        product_id = str(
            item["product_id"]
        )

        quantity = int(
            item.get("quantity", 1)
        )

        if quantity <= 0:
            raise ValueError(
                "Quantity must be greater than zero."
            )

        product = await products_collection.find_one(
            {
                "_id": product_id,
                "active": True,
            }
        )

        if not product:
            raise ValueError(
                f"Product {product_id} not found."
            )

        if product["stock"] < quantity:
            raise ValueError(
                f"Only {product['stock']} units "
                f"of {product['name']} are available."
            )

        normalized_items.append(
            {
                "product_id": product["_id"],
                "name": product["name"],
                "category": product["category"],
                "quantity": quantity,
                "unit_price": int(
                    product["price"]
                ),
                "line_total": (
                    int(product["price"])
                    * quantity
                ),
                "image": product["image"],
            }
        )

    categories = sorted(
        {
            item["category"]
            for item in normalized_items
        }
    )

    cart = build_cart(
        normalized_items
    )

    return {
        **cart,
        "categories": categories,
    }


# ============================================================
# AUTONOMOUS PAYMENT ADAPTER
# ============================================================

async def autonomous_payment(
    *,
    agent_id: str,
    user_id: str,
    amount: int,
    basket: dict[str, Any],
) -> dict[str, Any]:

    mode = (
        await get_policy(agent_id)
    ).get(
        "payment_mode",
        AUTONOMOUS_PAYMENT_MODE,
    )

    # --------------------------------------------------------
    # SIMULATED AUTONOMOUS RAIL
    # --------------------------------------------------------

    if mode == "SIMULATED":

        payment_id = (
            f"sim_pay_{uuid.uuid4().hex[:16]}"
        )

        order_payment = {
            "_id": payment_id,
            "provider": "SIMULATED_AUTONOMOUS_RAIL",
            "agent_id": agent_id,
            "user_id": user_id,
            "amount": amount,
            "currency": "INR",
            "status": "CAPTURED",
            "test": True,
            "created_at": now_utc(),
            "basket": basket,
        }

        await payments_collection.insert_one(
            order_payment
        )

        await audit(
            "AUTONOMOUS_PAYMENT_CAPTURED",
            agent_id=agent_id,
            user_id=user_id,
            amount=amount,
            status="SUCCESS",
            reason=(
                "Autonomous test rail captured "
                "the bounded purchase."
            ),
            data={
                "payment_id": payment_id,
                "provider": (
                    "SIMULATED_AUTONOMOUS_RAIL"
                ),
            },
        )

        return {
            "success": True,
            "provider": (
                "SIMULATED_AUTONOMOUS_RAIL"
            ),
            "payment_id": payment_id,
            "status": "CAPTURED",
            "amount": amount,
        }

    # --------------------------------------------------------
    # STANDARD RAZORPAY CHECKOUT
    #
    # NOT autonomous.
    # Included only as fallback/compatibility.
    # --------------------------------------------------------

    if mode == "RAZORPAY_CHECKOUT":

        if not (
            RAZORPAY_KEY_ID
            and RAZORPAY_KEY_SECRET
        ):
            return {
                "success": False,
                "error": (
                    "Razorpay credentials are not configured."
                ),
            }

        amount_paise = (
            amount * 100
        )

        receipt = (
            f"qc_{uuid.uuid4().hex[:16]}"
        )

        try:
            response = await httpx.AsyncClient().post(
                f"{RAZORPAY_API_BASE}/orders",
                auth=(
                    RAZORPAY_KEY_ID,
                    RAZORPAY_KEY_SECRET,
                ),
                json={
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt,
                    "notes": {
                        "agent_id": agent_id,
                        "user_id": user_id,
                    },
                },
                timeout=20,
            )

        except httpx.RequestError as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if response.status_code >= 400:
            return {
                "success": False,
                "error": response.text,
            }

        razorpay_order = response.json()

        payment_id = razorpay_order[
            "id"
        ]

        await payments_collection.insert_one(
            {
                "_id": payment_id,
                "provider": "razorpay",
                "type": "checkout",
                "agent_id": agent_id,
                "user_id": user_id,
                "razorpay_order_id": payment_id,
                "amount": amount,
                "currency": "INR",
                "status": "CREATED",
                "created_at": now_utc(),
            }
        )

        return {
            "success": True,
            "provider": "razorpay",
            "status": "CREATED",
            "razorpay_order_id": payment_id,
            "requires_human_payment": True,
            "message": (
                "Standard Razorpay Checkout "
                "requires human payment."
            ),
        }

    # --------------------------------------------------------
    # RESERVE PAY
    # --------------------------------------------------------

    if mode == "RAZORPAY_RESERVE_PAY":

        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "error": (
                "Razorpay UPI Reserve Pay is not "
                "configured for this environment. "
                "Request Reserve Pay activation and "
                "wire the account-specific Reserve Pay "
                "API contract here."
            ),
        }

    return {
        "success": False,
        "error": (
            f"Unknown autonomous payment mode: {mode}"
        ),
    }


# ============================================================
# CREATE AUTONOMOUS ORDER
# ============================================================

async def execute_autonomous_purchase(
    *,
    agent_id: str,
    user_id: str,
    items: list[dict[str, Any]],
    intent: str,
) -> dict[str, Any]:

    run_id = (
        f"run_{uuid.uuid4().hex[:16]}"
    )

    await runs_collection.insert_one(
        {
            "_id": run_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "intent": intent,
            "status": "STARTED",
            "started_at": now_utc(),
        }
    )

    try:

        basket = await build_basket(
            items
        )

    except ValueError as exc:

        await runs_collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "FAILED",
                    "error": str(exc),
                    "finished_at": now_utc(),
                }
            },
        )

        await audit(
            "AUTONOMOUS_PURCHASE_FAILED",
            agent_id=agent_id,
            user_id=user_id,
            status="FAILED",
            reason=str(exc),
            data={"run_id": run_id},
        )

        return {
            "success": False,
            "status": "FAILED",
            "reason": str(exc),
        }

    amount = int(
        basket["total"]
    )

    categories = basket[
        "categories"
    ]

    await audit(
        "AGENT_BASKET_BUILT",
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        status="READY",
        reason=intent,
        data={
            "run_id": run_id,
            "items": basket["items"],
            "categories": categories,
        },
    )

    policy_result = await evaluate_purchase(
        agent_id=agent_id,
        user_id=user_id,
        merchant_id=DEFAULT_MERCHANT_ID,
        amount=amount,
        categories=categories,
    )

    await audit(
        "AGENT_POLICY_EVALUATED",
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        status=policy_result[
            "decision"
        ],
        reason=policy_result.get(
            "reason"
        ),
        data={
            "run_id": run_id,
            "policy": policy_result,
        },
    )

    if policy_result[
        "decision"
    ] != "ALLOW":

        await runs_collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "BLOCKED",
                    "policy_result": (
                        policy_result
                    ),
                    "finished_at": now_utc(),
                }
            },
        )

        return {
            "success": False,
            "status": "BLOCKED",
            "run_id": run_id,
            "policy": policy_result,
            "basket": basket,
        }

    # --------------------------------------------------------
    # Reserve daily budget atomically.
    # --------------------------------------------------------

    policy = await get_policy(
        agent_id
    )

    reservation = (
        await reserve_daily_spend(
            agent_id=agent_id,
            amount=amount,
            daily_limit=int(
                policy["daily_limit"]
            ),
        )
    )

    if reservation is None:

        await audit(
            "AUTONOMOUS_PURCHASE_BLOCKED",
            agent_id=agent_id,
            user_id=user_id,
            amount=amount,
            status="BLOCKED",
            reason=(
                "Daily limit became unavailable "
                "during atomic reservation."
            ),
            data={
                "run_id": run_id,
            },
        )

        await runs_collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "BLOCKED",
                    "finished_at": now_utc(),
                }
            },
        )

        return {
            "success": False,
            "status": "BLOCKED",
            "run_id": run_id,
            "reason": (
                "Daily limit became unavailable."
            ),
        }

    await audit(
        "AGENT_SPEND_RESERVED",
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        status="RESERVED",
        data={
            "run_id": run_id,
            "spent_today": reservation[
                "amount"
            ],
            "daily_limit": policy[
                "daily_limit"
            ],
        },
    )

    # --------------------------------------------------------
    # Payment
    # --------------------------------------------------------

    payment = await autonomous_payment(
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        basket=basket,
    )

    if not payment["success"]:

        # Release budget because payment did not happen.
        await release_daily_spend(
            agent_id=agent_id,
            amount=amount,
        )

        await audit(
            "AUTONOMOUS_PAYMENT_FAILED",
            agent_id=agent_id,
            user_id=user_id,
            amount=amount,
            status="FAILED",
            reason=payment.get(
                "error"
            ),
            data={
                "run_id": run_id,
                "payment": payment,
            },
        )

        await runs_collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "PAYMENT_FAILED",
                    "finished_at": now_utc(),
                }
            },
        )

        return {
            "success": False,
            "status": "PAYMENT_FAILED",
            "run_id": run_id,
            "payment": payment,
            "message": (
                "No order was created and the "
                "reserved daily budget was released."
            ),
        }

    # --------------------------------------------------------
    # Inventory reservation
    # --------------------------------------------------------

    inventory_changes = []

    for item in basket["items"]:

        result = (
            await products_collection.find_one_and_update(
                {
                    "_id": item["product_id"],
                    "stock": {
                        "$gte": item["quantity"]
                    },
                },
                {
                    "$inc": {
                        "stock": -item["quantity"]
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        )

        if result is None:

            # Roll back previous stock changes.
            for changed in inventory_changes:
                await products_collection.update_one(
                    {
                        "_id": changed[
                            "product_id"
                        ]
                    },
                    {
                        "$inc": {
                            "stock": changed[
                                "quantity"
                            ]
                        }
                    },
                )

            # This is a test payment adapter.
            # Release spend because fulfilment failed.
            await release_daily_spend(
                agent_id=agent_id,
                amount=amount,
            )

            await audit(
                "ORDER_FAILED",
                agent_id=agent_id,
                user_id=user_id,
                amount=amount,
                status="FAILED",
                reason=(
                    "Inventory changed before fulfilment."
                ),
                data={
                    "run_id": run_id,
                    "product_id": item[
                        "product_id"
                    ],
                },
            )

            return {
                "success": False,
                "status": "ORDER_FAILED",
                "reason": (
                    "Inventory changed before "
                    "the order could be fulfilled."
                ),
                "payment": payment,
            }

        inventory_changes.append(
            {
                "product_id": item["product_id"],
                "quantity": item["quantity"],
            }
        )

    # --------------------------------------------------------
    # Order
    # --------------------------------------------------------

    order_id = (
        f"QC-{uuid.uuid4().hex[:10].upper()}"
    )

    order = {
        "_id": order_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "merchant_id": DEFAULT_MERCHANT_ID,
        "status": "CONFIRMED",
        "payment_status": "PAID",
        "payment_id": payment.get(
            "payment_id"
        ) or payment.get(
            "razorpay_order_id"
        ),
        "payment_provider": payment[
            "provider"
        ],
        "items": basket["items"],
        "subtotal": basket["subtotal"],
        "delivery_fee": basket[
            "delivery_fee"
        ],
        "total": basket["total"],
        "currency": "INR",
        "intent": intent,
        "created_at": now_utc(),
    }

    await orders_collection.insert_one(
        order
    )

    await audit(
        "ORDER_CREATED",
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        status="SUCCESS",
        reason=(
            "Purchase completed inside "
            "agent guardrails."
        ),
        data={
            "run_id": run_id,
            "order_id": order_id,
            "payment": payment,
        },
    )

    await runs_collection.update_one(
        {"_id": run_id},
        {
            "$set": {
                "status": "COMPLETED",
                "order_id": order_id,
                "payment_id": payment.get(
                    "payment_id"
                ),
                "finished_at": now_utc(),
            }
        },
    )

    return {
        "success": True,
        "status": "COMPLETED",
        "run_id": run_id,
        "order": json_safe(order),
        "policy": policy_result,
        "payment": payment,
    }


# ============================================================
# APPS UI
# ============================================================

apps = Apps()


def load_product_ui() -> str:
    if not PRODUCT_UI_FILE.exists():
        raise FileNotFoundError(
            f"Missing {PRODUCT_UI_FILE}"
        )

    return PRODUCT_UI_FILE.read_text(
        encoding="utf-8"
    )


apps.add_html_resource(
    PRODUCT_UI_URI,
    load_product_ui(),
    name="quickcart-product-catalogue",
    title="QuickCart Product Catalogue",
    description=(
        "Interactive product catalogue and "
        "autonomous shopping agent."
    ),
    prefers_border=True,
)


# ============================================================
# UI TOOLS
# ============================================================

@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Search Products",
    description=(
        "Search the merchant catalogue and "
        "display product cards."
    ),
)
async def search_products(
    query: str,
    category: str | None = None,
    max_price: int | None = None,
    limit: int = 8,
) -> dict[str, Any]:

    limit = max(
        1,
        min(limit, 50),
    )

    terms = normalize(
        query
    ).split()

    documents = await products_collection.find(
        {
            "active": True,
        }
    ).to_list(length=None)

    matches = []

    for product in documents:

        if category is not None:
            if normalize(
                product["category"]
            ) != normalize(category):
                continue

        if max_price is not None:
            if product["price"] > max_price:
                continue

        searchable = normalize(
            " ".join(
                [
                    product["name"],
                    product["brand"],
                    product["category"],
                    product["description"],
                    " ".join(product["tags"]),
                ]
            )
        )

        score = sum(
            1
            for term in terms
            if term in searchable
        )

        if score > 0:
            matches.append(
                (score, product)
            )

    matches.sort(
        key=lambda entry: (
            -entry[0],
            -entry[1]["rating"],
            entry[1]["price"],
        )
    )

    selected = [
        entry[1]
        for entry in matches[:limit]
    ]

    return {
        "success": True,
        "query": query,
        "count": len(selected),
        "products": [
            product_public(product)
            for product in selected
        ],
    }


@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Product Catalogue",
    description="Browse the merchant catalogue.",
)
async def get_catalogue(
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:

    query: dict[str, Any] = {
        "active": True,
    }

    if category:
        query["category"] = normalize(
            category
        )

    documents = await products_collection.find(
        query
    ).sort(
        [
            ("rating", -1),
            ("price", 1),
        ]
    ).limit(
        max(1, min(limit, 50))
    ).to_list(
        length=None
    )

    return {
        "success": True,
        "category": category,
        "count": len(documents),
        "products": [
            product_public(product)
            for product in documents
        ],
    }


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer(
    APP_NAME,
    instructions="""
You are QuickCart's autonomous commerce agent.

You can:
- search a real merchant catalogue
- inspect an agent's financial policy
- evaluate purchases against hard guardrails
- autonomously purchase products within the mandate
- show spending and audit history
- check orders

AUTONOMOUS PURCHASE RULES:

1. Never invent products, prices, inventory or spending limits.
2. For normal shopping requests, search the catalogue.
3. For autonomous-agent requests, use the agent policy.
4. The backend policy engine is authoritative.
5. Never override a BLOCK decision.
6. Never claim that a payment happened unless the backend
   returned success.
7. In SIMULATED autonomous mode, purchases are explicitly
   marked as simulated test payments.
8. Standard Razorpay Checkout requires human interaction.
9. Do not describe standard Checkout as autonomous payment.
10. Only a Razorpay Reserve Pay integration activated for the
    merchant can provide the real "authorize once, debit later"
    autonomous payment rail.
""",
    extensions=[apps],
)


# ============================================================
# AGENT TOOLS
# ============================================================

@mcp.tool()
async def get_agent_policy(
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Return the agent's autonomous spending mandate."""

    agent = await get_agent(
        agent_id
    )

    policy = await get_policy(
        agent_id
    )

    if not agent or not policy:
        return {
            "success": False,
            "error": "Agent not found.",
        }

    return {
        "success": True,
        "agent": json_safe(agent),
        "policy": json_safe(policy),
        "spend_today": await get_daily_spend(
            agent_id
        ),
        "payment_mode": payment_mode_description(),
    }


@mcp.tool()
async def evaluate_agent_purchase_tool(
    agent_id: str,
    amount: int,
    category: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """
    Deterministically evaluate whether an autonomous
    purchase is inside the agent's mandate.
    """

    result = await evaluate_purchase(
        agent_id=agent_id,
        user_id=user_id,
        merchant_id=DEFAULT_MERCHANT_ID,
        amount=amount,
        categories=[normalize(category)],
    )

    await audit(
        "POLICY_CHECK",
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        status=result["decision"],
        reason=result.get("reason"),
        data={
            "category": category,
        },
    )

    return {
        "success": True,
        "agent_id": agent_id,
        "amount": amount,
        **result,
    }


@mcp.tool()
async def autonomous_purchase(
    items: list[dict[str, Any]],
    intent: str,
    agent_id: str = DEFAULT_AGENT_ID,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """
    Execute an autonomous purchase.

    No human payment action is requested in SIMULATED mode.
    The backend first checks the agent's hard financial
    guardrails, then executes the configured payment rail.
    """

    return await execute_autonomous_purchase(
        agent_id=agent_id,
        user_id=user_id,
        items=items,
        intent=intent,
    )


@mcp.tool()
async def get_agent_spending(
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Show today's autonomous spending and remaining budget."""

    policy = await get_policy(
        agent_id
    )

    if not policy:
        return {
            "success": False,
            "error": "Agent policy not found.",
        }

    spent = await get_daily_spend(
        agent_id
    )

    daily_limit = int(
        policy["daily_limit"]
    )

    return {
        "success": True,
        "agent_id": agent_id,
        "date": today_key(),
        "daily_limit": daily_limit,
        "spent_today": spent,
        "remaining_today": max(
            0,
            daily_limit - spent,
        ),
        "per_transaction_limit": int(
            policy["per_transaction_limit"]
        ),
    }


@mcp.tool()
async def get_agent_activity(
    agent_id: str = DEFAULT_AGENT_ID,
    limit: int = 20,
) -> dict[str, Any]:
    """Return the latest audit events for an agent."""

    events = await audit_collection.find(
        {
            "agent_id": agent_id,
        }
    ).sort(
        "timestamp",
        -1,
    ).limit(
        max(1, min(limit, 100))
    ).to_list(
        length=None
    )

    return {
        "success": True,
        "count": len(events),
        "events": [
            json_safe(event)
            for event in events
        ],
    }


@mcp.tool()
async def explain_agent_purchase(
    run_id: str,
) -> dict[str, Any]:
    """
    Explain why an autonomous purchase was allowed,
    blocked or failed.
    """

    run = await runs_collection.find_one(
        {
            "_id": run_id,
        }
    )

    if not run:
        return {
            "success": False,
            "error": "Agent run not found.",
        }

    events = await audit_collection.find(
        {
            "data.run_id": run_id,
        }
    ).sort(
        "timestamp",
        1,
    ).to_list(
        length=None
    )

    return {
        "success": True,
        "run": json_safe(run),
        "audit": [
            json_safe(event)
            for event in events
        ],
    }


# ============================================================
# SHOPPING TOOLS
# ============================================================

@mcp.tool()
async def list_categories() -> dict[str, Any]:
    """List all catalogue categories."""

    categories = await products_collection.distinct(
        "category",
        {
            "active": True,
        },
    )

    return {
        "success": True,
        "categories": sorted(
            categories
        ),
        "count": len(categories),
    }


@mcp.tool()
async def get_cart(
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Get the persistent cart from MongoDB."""

    cart = await carts_collection.find_one(
        {
            "_id": f"cart:{user_id}",
        }
    )

    if not cart:
        return {
            "success": True,
            "cart": build_cart([]),
        }

    return {
        "success": True,
        "cart": json_safe(
            cart
        ),
    }


@mcp.tool()
async def add_to_cart(
    product_id: str,
    quantity: int = 1,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Add an item to the persistent MongoDB cart."""

    if quantity <= 0:
        return {
            "success": False,
            "error": "Quantity must be greater than zero.",
        }

    product = await products_collection.find_one(
        {
            "_id": product_id,
            "active": True,
        }
    )

    if not product:
        return {
            "success": False,
            "error": "Product not found.",
        }

    existing = await carts_collection.find_one(
        {
            "_id": f"cart:{user_id}",
        }
    )

    current_quantity = 0

    if existing:
        for item in existing.get(
            "items",
            [],
        ):
            if item["product_id"] == product_id:
                current_quantity = item[
                    "quantity"
                ]

    new_quantity = (
        current_quantity + quantity
    )

    if new_quantity > product["stock"]:
        return {
            "success": False,
            "error": (
                f"Only {product['stock']} "
                f"units are available."
            ),
        }

    cart_id = f"cart:{user_id}"

    if current_quantity > 0:

        await carts_collection.update_one(
            {
                "_id": cart_id,
                "items.product_id": product_id,
            },
            {
                "$set": {
                    "items.$.quantity": new_quantity,
                    "updated_at": now_utc(),
                }
            },
        )

    else:

        await carts_collection.update_one(
            {
                "_id": cart_id,
            },
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "created_at": now_utc(),
                },
                "$push": {
                    "items": {
                        "product_id": product_id,
                        "name": product["name"],
                        "category": product["category"],
                        "quantity": quantity,
                        "unit_price": product["price"],
                        "line_total": (
                            product["price"]
                            * quantity
                        ),
                        "image": product["image"],
                    }
                },
                "$set": {
                    "updated_at": now_utc(),
                },
            },
            upsert=True,
        )

    # Recalculate line totals.
    cart = await carts_collection.find_one(
        {"_id": cart_id}
    )

    updated_items = []

    for item in cart.get(
        "items",
        [],
    ):

        product_now = await products_collection.find_one(
            {"_id": item["product_id"]}
        )

        if product_now:
            item["unit_price"] = product_now[
                "price"
            ]
            item["line_total"] = (
                product_now["price"]
                * item["quantity"]
            )
            updated_items.append(item)

    cart_summary = build_cart(
        updated_items
    )

    await carts_collection.update_one(
        {"_id": cart_id},
        {
            "$set": {
                "items": updated_items,
                "subtotal": cart_summary[
                    "subtotal"
                ],
                "delivery_fee": cart_summary[
                    "delivery_fee"
                ],
                "total": cart_summary[
                    "total"
                ],
                "updated_at": now_utc(),
            }
        },
    )

    return {
        "success": True,
        "message": (
            f"Added {quantity} × "
            f"{product['name']}."
        ),
        "cart": cart_summary,
    }


# ============================================================
# ORDER HISTORY
# ============================================================

@mcp.tool()
async def get_order(
    order_id: str,
) -> dict[str, Any]:
    """Get a persistent MongoDB order."""

    order = await orders_collection.find_one(
        {
            "_id": order_id,
        }
    )

    if not order:
        return {
            "success": False,
            "error": "Order not found.",
        }

    return {
        "success": True,
        "order": json_safe(order),
    }


@mcp.tool()
async def list_orders(
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """List a user's orders."""

    orders = await orders_collection.find(
        {
            "user_id": user_id,
        }
    ).sort(
        "created_at",
        -1,
    ).limit(
        100
    ).to_list(
        length=None
    )

    return {
        "success": True,
        "count": len(orders),
        "orders": [
            json_safe(order)
            for order in orders
        ],
    }


# ============================================================
# FASTAPI LIFESPAN
# ============================================================

@contextlib.asynccontextmanager
async def lifespan(
    app: FastAPI,
):

    global mongo_client
    global db

    global agents_collection
    global policies_collection
    global products_collection
    global carts_collection
    global orders_collection
    global payments_collection
    global spend_collection
    global runs_collection
    global audit_collection

    if not MONGODB_URI:
        raise RuntimeError(
            "MONGODB_URI is not configured."
        )

    mongo_client = AsyncMongoClient(
        MONGODB_URI
    )

    db = mongo_client[
        MONGODB_DB
    ]

    # Verify database connectivity.
    ping = await db.command(
        "ping"
    )

    if int(ping["ok"]) != 1:
        raise RuntimeError(
            "MongoDB ping failed."
        )

    agents_collection = db[
        "agents"
    ]

    policies_collection = db[
        "agent_policies"
    ]

    products_collection = db[
        "products"
    ]

    carts_collection = db[
        "carts"
    ]

    orders_collection = db[
        "orders"
    ]

    payments_collection = db[
        "payments"
    ]

    spend_collection = db[
        "agent_spend"
    ]

    runs_collection = db[
        "agent_runs"
    ]

    audit_collection = db[
        "audit_events"
    ]

    # Indexes.
    await products_collection.create_index(
        [
            ("merchant_id", 1),
            ("category", 1),
        ]
    )

    await products_collection.create_index(
        [
            ("name", "text"),
            ("brand", "text"),
            ("description", "text"),
        ]
    )

    await orders_collection.create_index(
        [
            ("user_id", 1),
            ("created_at", -1),
        ]
    )

    await audit_collection.create_index(
        [
            ("agent_id", 1),
            ("timestamp", -1),
        ]
    )

    await spend_collection.create_index(
        [
            ("agent_id", 1),
            ("date", 1),
        ],
        unique=True,
    )

    # Seed products safely.
    for product in DEFAULT_PRODUCTS:
        await products_collection.update_one(
            {
                "_id": product["_id"],
            },
            {
                "$setOnInsert": product,
            },
            upsert=True,
        )

    await ensure_demo_agent()

    app.state.mongo_client = mongo_client
    app.state.db = db

    print(
        "MongoDB connected:",
        MONGODB_DB,
    )

    print(
        "Agent:",
        DEFAULT_AGENT_ID,
    )

    print(
        "Daily limit: ₹50,000"
    )

    print(
        "Autonomous payment mode:",
        AUTONOMOUS_PAYMENT_MODE,
    )

    yield

    if mongo_client:
        await mongo_client.close()


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "MongoDB-backed autonomous commerce "
        "agent with bounded spending."
    ),
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chatgpt.com",
        "https://chat.openai.com",
    ],
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "OPTIONS",
    ],
    allow_headers=[
        "*",
    ],
    expose_headers=[
        "Mcp-Session-Id",
    ],
)


# ============================================================
# NORMAL HTTP ROUTES
# ============================================================

@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "mcp": MCP_URL,
        "agent": DEFAULT_AGENT_ID,
        "autonomous_payment_mode": (
            AUTONOMOUS_PAYMENT_MODE
        ),
    }


@app.get("/health")
async def health():

    mongo_ok = False

    if db is not None:
        try:
            result = await db.command(
                "ping"
            )
            mongo_ok = (
                int(result["ok"]) == 1
            )
        except Exception:
            mongo_ok = False

    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "mongodb": mongo_ok,
        "razorpay_test_keys": (
            RAZORPAY_KEY_ID.startswith(
                "rzp_test_"
            )
            and bool(
                RAZORPAY_KEY_SECRET
            )
        ),
        "autonomous_payment_mode": (
            AUTONOMOUS_PAYMENT_MODE
        ),
        "agent": DEFAULT_AGENT_ID,
        "daily_limit": 50000,
    }


@app.get("/agent")
async def agent_http():
    agent = await get_agent(
        DEFAULT_AGENT_ID
    )

    policy = await get_policy(
        DEFAULT_AGENT_ID
    )

    return {
        "agent": json_safe(agent),
        "policy": json_safe(policy),
        "spending": {
            "today": await get_daily_spend(
                DEFAULT_AGENT_ID
            ),
        },
    }


@app.get("/agent/audit")
async def audit_http(
    limit: int = 50,
):

    events = await audit_collection.find(
        {
            "agent_id": DEFAULT_AGENT_ID,
        }
    ).sort(
        "timestamp",
        -1,
    ).limit(
        max(1, min(limit, 100))
    ).to_list(
        length=None
    )

    return {
        "count": len(events),
        "events": [
            json_safe(event)
            for event in events
        ],
    }


# ============================================================
# AUTONOMOUS TEST ENDPOINT
#
# This lets you test the exact agent workflow from a browser
# before asking ChatGPT to call it.
# ============================================================

@app.post("/test/autonomous-purchase")
async def test_autonomous_purchase(
    payload: dict[str, Any],
):

    items = payload.get(
        "items",
        [
            {
                "product_id": "p005",
                "quantity": 20,
            }
        ],
    )

    intent = payload.get(
        "intent",
        "Test autonomous grocery purchase",
    )

    return await execute_autonomous_purchase(
        agent_id=DEFAULT_AGENT_ID,
        user_id=DEFAULT_USER_ID,
        items=items,
        intent=intent,
    )


# ============================================================
# MCP TRANSPORT SECURITY
# ============================================================

transport_security = (
    TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            PUBLIC_HOST,
            f"{PUBLIC_HOST}:443",
        ],
        allowed_origins=[
            "https://chatgpt.com",
            "https://chat.openai.com",
        ],
    )
)


# ============================================================
# MCP STREAMABLE HTTP
# ============================================================

mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    transport_security=transport_security,
)


app.mount(
    "/mcp",
    mcp_http_app,
)


# ============================================================
# LOCAL ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )