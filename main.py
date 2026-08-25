from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import uuid
from html import escape
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.transport_security import TransportSecuritySettings


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "QuickCart MCP"
APP_VERSION = "3.0.0"

PUBLIC_HOST = "pymcp-test.onrender.com"
PUBLIC_BASE_URL = f"https://{PUBLIC_HOST}"
MCP_URL = f"{PUBLIC_BASE_URL}/mcp"

PRODUCT_UI_URI = "ui://quickcart/product-catalogue.html"

BASE_DIR = Path(__file__).resolve().parent
PRODUCT_UI_FILE = BASE_DIR / "product_catalogue.html"

# Razorpay
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
# RAZORPAY_KEY_ID = "rzp_test_SIjuTFfoEyDAWa"
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
# RAZORPAY_KEY_SECRET = "iOSIi09qMHX2pp7rqTkhMHPL"
RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


# ============================================================
# DEMO PRODUCT DATABASE
# ============================================================

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": "p001",
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
        "tags": ["atta", "flour", "wheat", "grocery"],
    },
    {
        "id": "p002",
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
        "tags": ["salt", "grocery"],
    },
    {
        "id": "p003",
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
        "tags": ["milk", "dairy", "breakfast"],
    },
    {
        "id": "p004",
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
        "tags": ["butter", "dairy"],
    },
    {
        "id": "p005",
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
        "tags": ["maggi", "noodles", "instant", "snacks"],
    },
    {
        "id": "p006",
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
        "tags": ["chips", "snacks"],
    },
    {
        "id": "p007",
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
        "tags": ["coke", "drink", "beverage", "soft drink"],
    },
    {
        "id": "p008",
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
        "tags": ["energy", "drink", "beverage"],
    },
    {
        "id": "p009",
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
        "tags": ["detergent", "washing", "household"],
    },
    {
        "id": "p010",
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
        "tags": ["toothpaste", "personal care"],
    },
]


# ============================================================
# DEMO STATE
# ============================================================

# Demo only.
# Replace with PostgreSQL/MongoDB for production.
CARTS: dict[str, dict[str, int]] = {}
ORDERS: dict[str, dict[str, Any]] = {}

# Razorpay payment attempts.
PAYMENTS: dict[str, dict[str, Any]] = {}


# ============================================================
# HELPERS
# ============================================================

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text)


def get_product(product_id: str) -> dict[str, Any] | None:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product

    return None


def public_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": product["id"],
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


def calculate_cart(user_id: str) -> dict[str, Any]:
    user_cart = CARTS.get(user_id, {})

    items: list[dict[str, Any]] = []
    subtotal = 0

    for product_id, quantity in user_cart.items():
        product = get_product(product_id)

        if product is None:
            continue

        line_total = product["price"] * quantity
        subtotal += line_total

        items.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "quantity": quantity,
                "unit_price": product["price"],
                "line_total": line_total,
                "image": product["image"],
            }
        )

    delivery_fee = 39 if 0 < subtotal < 499 else 0
    total = subtotal + delivery_fee

    return {
        "user_id": user_id,
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total,
        "currency": "INR",
    }


def load_product_ui() -> str:
    if not PRODUCT_UI_FILE.exists():
        raise FileNotFoundError(
            f"Missing UI file: {PRODUCT_UI_FILE}"
        )

    return PRODUCT_UI_FILE.read_text(
        encoding="utf-8"
    )


def verify_razorpay_signature(
    order_id: str,
    payment_id: str,
    received_signature: str,
) -> bool:
    if not RAZORPAY_KEY_SECRET:
        return False

    message = f"{order_id}|{payment_id}"

    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected_signature,
        received_signature,
    )


# ============================================================
# APPS SDK
# ============================================================

apps = Apps()

apps.add_html_resource(
    PRODUCT_UI_URI,
    load_product_ui(),
    name="quickcart-product-catalogue",
    title="QuickCart Product Catalogue",
    description=(
        "QuickCart product catalogue with images, "
        "prices, ratings, cart and payment actions."
    ),
    prefers_border=True,
)


# ============================================================
# UI PRODUCT TOOLS
# ============================================================

@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Search Products",
    description=(
        "Search QuickCart products and show them "
        "in the interactive product catalogue."
    ),
)
def search_products(
    query: str,
    category: str | None = None,
    max_price: int | None = None,
    limit: int = 8,
) -> dict[str, Any]:

    if not query.strip():
        return {
            "success": False,
            "message": "Search query cannot be empty.",
            "query": query,
            "count": 0,
            "products": [],
        }

    limit = max(1, min(limit, 50))
    terms = normalize(query).split()

    matches: list[tuple[int, dict[str, Any]]] = []

    for product in PRODUCTS:

        if category is not None:
            if normalize(product["category"]) != normalize(category):
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
            matches.append((score, product))

    matches.sort(
        key=lambda item: (
            -item[0],
            -item[1]["rating"],
            item[1]["price"],
        )
    )

    selected = [
        product
        for _, product in matches[:limit]
    ]

    return {
        "success": True,
        "query": query,
        "count": len(selected),
        "products": [
            public_product(product)
            for product in selected
        ],
    }


@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Product Catalogue",
    description="Browse QuickCart products.",
)
def get_catalogue(
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:

    limit = max(1, min(limit, 50))

    products = PRODUCTS

    if category:
        products = [
            product
            for product in products
            if normalize(product["category"])
            == normalize(category)
        ]

    selected = products[:limit]

    return {
        "success": True,
        "category": category,
        "count": len(selected),
        "products": [
            public_product(product)
            for product in selected
        ],
    }


@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Product Details",
    description="Show details for a product.",
)
def get_product_details(
    product_id: str,
) -> dict[str, Any]:

    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
            "products": [],
            "count": 0,
        }

    return {
        "success": True,
        "count": 1,
        "products": [
            public_product(product)
        ],
    }


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer(
    APP_NAME,
    instructions="""
You are QuickCart, an agentic commerce assistant.

Use the shopping tools to search, browse, manage the cart,
create payments, and check orders.

IMPORTANT:
- Search products when the user asks what is available.
- Use the interactive product UI whenever available.
- Never invent products, prices, stock or order IDs.
- Inspect the cart before payment.
- create_payment_order only creates a Razorpay payment attempt.
- Do not claim payment succeeded until the server confirms it.
- Only complete the purchase after genuine payment verification.
- Do not expose the Razorpay secret.
""",
    extensions=[apps],
)


# ============================================================
# NORMAL MCP TOOLS
# ============================================================

@mcp.tool()
def list_categories() -> dict[str, Any]:
    """List all shopping categories."""

    categories = sorted(
        {
            product["category"]
            for product in PRODUCTS
        }
    )

    return {
        "success": True,
        "categories": categories,
        "count": len(categories),
    }


@mcp.tool()
def add_to_cart(
    product_id: str,
    quantity: int = 1,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Add a product to the cart."""

    if quantity <= 0:
        return {
            "success": False,
            "error": "Quantity must be greater than zero.",
        }

    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
        }

    cart = CARTS.setdefault(user_id, {})

    current = cart.get(product_id, 0)
    new_quantity = current + quantity

    if new_quantity > product["stock"]:
        return {
            "success": False,
            "error": (
                f"Only {product['stock']} units "
                f"are available."
            ),
        }

    cart[product_id] = new_quantity

    return {
        "success": True,
        "message": (
            f"Added {quantity} × "
            f"{product['name']}."
        ),
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def update_cart_item(
    product_id: str,
    quantity: int,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Set the exact cart quantity."""

    if quantity < 0:
        return {
            "success": False,
            "error": "Quantity cannot be negative.",
        }

    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
        }

    cart = CARTS.setdefault(user_id, {})

    if quantity == 0:
        cart.pop(product_id, None)
    else:
        if quantity > product["stock"]:
            return {
                "success": False,
                "error": "Not enough stock.",
            }

        cart[product_id] = quantity

    return {
        "success": True,
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def remove_from_cart(
    product_id: str,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Remove one item from the cart."""

    cart = CARTS.setdefault(user_id, {})

    removed = cart.pop(product_id, None)

    return {
        "success": True,
        "removed": removed is not None,
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def get_cart(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Return the current cart."""

    return {
        "success": True,
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def clear_cart(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Clear the cart."""

    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Cart cleared.",
        "cart": calculate_cart(user_id),
    }


# ============================================================
# RAZORPAY: CREATE PAYMENT ORDER
# ============================================================

@mcp.tool()
def create_payment_order(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Create a Razorpay Test Mode Order for the current cart.

    This DOES NOT mark the QuickCart order as paid.
    """

    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return {
            "success": False,
            "error": (
                "Razorpay credentials are not configured "
                "on the server."
            ),
        }

    cart = calculate_cart(user_id)

    if not cart["items"]:
        return {
            "success": False,
            "error": "Your cart is empty.",
        }

    amount_paise = int(
        round(cart["total"] * 100)
    )

    receipt = (
        f"qc_{uuid.uuid4().hex[:16]}"
    )

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": {
            "user_id": user_id,
            "source": "quickcart_chatgpt",
        },
    }

    try:
        response = httpx.post(
            f"{RAZORPAY_API_BASE}/orders",
            json=payload,
            auth=(
                RAZORPAY_KEY_ID,
                RAZORPAY_KEY_SECRET,
            ),
            timeout=20,
        )

        if response.status_code >= 400:
            return {
                "success": False,
                "error": (
                    "Razorpay rejected the order."
                ),
                "razorpay_response": response.text,
            }

        razorpay_order = response.json()

    except httpx.RequestError as exc:
        return {
            "success": False,
            "error": (
                f"Could not reach Razorpay: {exc}"
            ),
        }

    razorpay_order_id = razorpay_order["id"]

    # Save immutable payment snapshot.
    PAYMENTS[razorpay_order_id] = {
        "razorpay_order_id": razorpay_order_id,
        "user_id": user_id,
        "cart": cart,
        "status": "CREATED",
        "amount_paise": amount_paise,
    }

    payment_url = (
        f"{PUBLIC_BASE_URL}/payment/"
        f"{razorpay_order_id}"
    )

    return {
        "success": True,
        "test_mode": True,
        "razorpay_order_id": razorpay_order_id,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "amount": cart["total"],
        "amount_paise": amount_paise,
        "currency": "INR",
        "payment_url": payment_url,
        "message": (
            "Razorpay Test Mode payment order "
            "created. Open payment_url to continue."
        ),
        "cart": cart,
    }


# ============================================================
# PAYMENT STATUS
# ============================================================

@mcp.tool()
def get_payment_status(
    razorpay_order_id: str,
) -> dict[str, Any]:
    """Check the server-side payment attempt status."""

    payment = PAYMENTS.get(
        razorpay_order_id
    )

    if payment is None:
        return {
            "success": False,
            "error": "Payment attempt not found.",
        }

    return {
        "success": True,
        "payment": {
            "razorpay_order_id": payment[
                "razorpay_order_id"
            ],
            "status": payment["status"],
            "amount_paise": payment[
                "amount_paise"
            ],
            "user_id": payment["user_id"],
            "payment_id": payment.get(
                "payment_id"
            ),
        },
    }


# ============================================================
# CHECKOUT / QUICKCART ORDER
# ============================================================

@mcp.tool()
def checkout(
    confirm: bool,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Finalize a QuickCart order only after payment.

    confirm=True alone is NOT enough.
    The matching Razorpay payment must have been
    successfully verified first.
    """

    if not confirm:
        return {
            "success": False,
            "requires_confirmation": True,
            "message": (
                "Checkout was not executed."
            ),
        }

    payment_attempts = [
        payment
        for payment in PAYMENTS.values()
        if (
            payment["user_id"] == user_id
            and payment["status"] == "PAID"
        )
    ]

    if not payment_attempts:
        return {
            "success": False,
            "error": (
                "No verified Razorpay payment "
                "was found for this user."
            ),
        }

    payment = payment_attempts[-1]
    cart = payment["cart"]

    if not cart["items"]:
        return {
            "success": False,
            "error": "Paid cart is empty.",
        }

    order_id = (
        f"QC-{uuid.uuid4().hex[:10].upper()}"
    )

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "status": "CONFIRMED",
        "payment_status": "PAID",
        "razorpay_order_id": (
            payment["razorpay_order_id"]
        ),
        "razorpay_payment_id": payment.get(
            "payment_id"
        ),
        "items": cart["items"],
        "subtotal": cart["subtotal"],
        "delivery_fee": cart["delivery_fee"],
        "total": cart["total"],
        "currency": cart["currency"],
        "payment_method": "razorpay_test",
    }

    ORDERS[order_id] = order

    # Reduce inventory.
    for item in cart["items"]:
        product = get_product(
            item["product_id"]
        )

        if product is not None:
            product["stock"] = max(
                0,
                product["stock"] - item["quantity"],
            )

    CARTS[user_id] = {}

    payment["status"] = "ORDER_CREATED"
    payment["quickcart_order_id"] = order_id

    return {
        "success": True,
        "message": "Paid order created.",
        "order": order,
    }


@mcp.tool()
def get_order(
    order_id: str,
) -> dict[str, Any]:
    """Get an existing QuickCart order."""

    order = ORDERS.get(order_id)

    if order is None:
        return {
            "success": False,
            "error": "Order not found.",
        }

    return {
        "success": True,
        "order": order,
    }


@mcp.tool()
def list_orders(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """List orders for a user."""

    orders = [
        order
        for order in ORDERS.values()
        if order["user_id"] == user_id
    ]

    return {
        "success": True,
        "count": len(orders),
        "orders": orders,
    }


# ============================================================
# FASTAPI APP
# ============================================================

@contextlib.asynccontextmanager
async def lifespan(
    _app: FastAPI,
):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Agentic commerce MCP server.",
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
        PUBLIC_BASE_URL,
    ],
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "Last-Event-ID",
        "Mcp-Method",
        "Mcp-Name",
        "Mcp-Protocol-Version",
        "Mcp-Session-Id",
    ],
    expose_headers=[
        "Mcp-Session-Id",
    ],
)


# ============================================================
# NORMAL ROUTES
# ============================================================

@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "mcp_endpoint": MCP_URL,
        "razorpay": (
            "configured"
            if RAZORPAY_KEY_ID
            else "not configured"
        ),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "products": len(PRODUCTS),
        "orders": len(ORDERS),
        "payment_attempts": len(PAYMENTS),
        "razorpay_test_mode": bool(
            RAZORPAY_KEY_ID
        ),
    }


@app.get("/catalogue")
async def catalogue():
    return {
        "success": True,
        "count": len(PRODUCTS),
        "products": PRODUCTS,
    }


# ============================================================
# RAZORPAY PAYMENT PAGE
#
# IMPORTANT:
# This page is hosted by YOUR FastAPI server.
# The Razorpay secret is never sent here.
# ============================================================

@app.get(
    "/payment/{razorpay_order_id}",
    response_class=HTMLResponse,
)
async def payment_page(
    razorpay_order_id: str,
):
    payment = PAYMENTS.get(
        razorpay_order_id
    )

    if payment is None:
        return HTMLResponse(
            content="""
            <h2>Payment session not found.</h2>
            <p>Please create a new payment attempt.</p>
            """,
            status_code=404,
        )

    if not RAZORPAY_KEY_ID:
        return HTMLResponse(
            content="""
            <h2>Razorpay is not configured.</h2>
            """,
            status_code=500,
        )

    amount = payment["amount_paise"]
    user_id = payment["user_id"]

    checkout_html = f"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta
        name="viewport"
        content="width=device-width,initial-scale=1"
    >
    <title>QuickCart Payment</title>

    <style>
        body {{
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            background: #f5f5f5;
            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Inter",
                sans-serif;
        }}

        .card {{
            width: min(420px, calc(100% - 32px));
            background: white;
            padding: 28px;
            border-radius: 20px;
            box-shadow:
                0 10px 40px
                rgba(0,0,0,.08);
        }}

        h1 {{
            margin: 0 0 8px;
            font-size: 24px;
        }}

        .subtitle {{
            color: #666;
            font-size: 14px;
            margin-bottom: 24px;
        }}

        .amount {{
            font-size: 32px;
            font-weight: 800;
            margin: 18px 0 24px;
        }}

        button {{
            width: 100%;
            border: none;
            border-radius: 12px;
            padding: 14px;
            background: #111;
            color: white;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
        }}

        button:disabled {{
            opacity: .6;
        }}

        .status {{
            margin-top: 16px;
            font-size: 14px;
            color: #555;
            line-height: 1.5;
        }}

        .success {{
            color: #087443;
        }}

        .error {{
            color: #b42318;
        }}
    </style>

    <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
</head>

<body>

<div class="card">

    <h1>QuickCart Payment</h1>

    <div class="subtitle">
        Razorpay Test Mode
    </div>

    <div class="amount">
        ₹{payment["amount_paise"] / 100:.2f}
    </div>

    <button
        id="payButton"
        onclick="startPayment()"
    >
        Pay Now
    </button>

    <div
        id="status"
        class="status"
    >
        Test payment only. No real money will be charged.
    </div>

</div>

<script>

const razorpayKey = {RAZORPAY_KEY_ID!r};
const razorpayOrderId = {razorpay_order_id!r};
const userId = {user_id!r};
const amountPaise = {amount};

function setStatus(
    message,
    className = ""
) {{
    const element =
        document.getElementById("status");

    element.className =
        "status " + className;

    element.textContent =
        message;
}}


async function startPayment() {{

    const button =
        document.getElementById(
            "payButton"
        );

    button.disabled = true;

    try {{

        setStatus(
            "Opening Razorpay Checkout..."
        );

        const options = {{

            key: razorpayKey,

            amount: amountPaise,

            currency: "INR",

            name: "QuickCart",

            description:
                "QuickCart Test Payment",

            order_id:
                razorpayOrderId,

            theme: {{
                color: "#111111"
            }},

            handler:
                async function(response) {{

                    setStatus(
                        "Verifying payment..."
                    );

                    try {{

                        const verifyResponse =
                            await fetch(
                                "/payment/verify",
                                {{
                                    method: "POST",
                                    headers: {{
                                        "Content-Type":
                                            "application/json"
                                    }},
                                    body:
                                        JSON.stringify({{
                                            user_id:
                                                userId,

                                            razorpay_order_id:
                                                response.razorpay_order_id,

                                            razorpay_payment_id:
                                                response.razorpay_payment_id,

                                            razorpay_signature:
                                                response.razorpay_signature
                                        }})
                                }}
                            );

                        const result =
                            await verifyResponse.json();

                        if (
                            !verifyResponse.ok ||
                            !result.success
                        ) {{
                            throw new Error(
                                result.error ||
                                "Payment verification failed"
                            );
                        }}

                        setStatus(
                            "Payment verified successfully. "
                            + "You can return to ChatGPT.",
                            "success"
                        );

                        button.textContent =
                            "Payment Successful";

                    }} catch (error) {{

                        setStatus(
                            error.message ||
                            "Payment verification failed.",
                            "error"
                        );

                        button.disabled =
                            false;
                    }}
                }},

            modal: {{
                ondismiss:
                    function() {{
                        setStatus(
                            "Payment window closed."
                        );

                        button.disabled =
                            false;
                    }}
            }}

        }};

        const razorpay =
            new Razorpay(options);

        razorpay.on(
            "payment.failed",
            function(response) {{
                setStatus(
                    "Payment failed: "
                    + (
                        response.error?.description
                        || "Unknown error"
                    ),
                    "error"
                );

                button.disabled =
                    false;
            }}
        );

        razorpay.open();

    }} catch (error) {{

        console.error(error);

        setStatus(
            "Unable to start payment.",
            "error"
        );

        button.disabled =
            false;
    }}
}}

</script>

</body>
</html>
"""

    return HTMLResponse(
        checkout_html
    )


# ============================================================
# RAZORPAY VERIFY ENDPOINT
# ============================================================

@app.post("/payment/verify")
async def verify_payment(
    request: Request,
):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "success": False,
                "error": "Invalid JSON.",
            },
            status_code=400,
        )

    user_id = payload.get(
        "user_id",
        "demo-user",
    )

    razorpay_order_id = payload.get(
        "razorpay_order_id"
    )

    razorpay_payment_id = payload.get(
        "razorpay_payment_id"
    )

    razorpay_signature = payload.get(
        "razorpay_signature"
    )

    if not all(
        [
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
        ]
    ):
        return JSONResponse(
            {
                "success": False,
                "error": (
                    "Missing Razorpay payment fields."
                ),
            },
            status_code=400,
        )

    payment = PAYMENTS.get(
        razorpay_order_id
    )

    if payment is None:
        return JSONResponse(
            {
                "success": False,
                "error": (
                    "Payment attempt not found."
                ),
            },
            status_code=404,
        )

    if payment["user_id"] != user_id:
        return JSONResponse(
            {
                "success": False,
                "error": "User mismatch.",
            },
            status_code=403,
        )

    if payment["status"] in {
        "PAID",
        "ORDER_CREATED",
    }:
        return {
            "success": True,
            "status": payment["status"],
            "message": "Payment already verified.",
        }

    valid = verify_razorpay_signature(
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature,
    )

    if not valid:
        payment["status"] = "VERIFICATION_FAILED"

        return JSONResponse(
            {
                "success": False,
                "error": (
                    "Razorpay signature verification failed."
                ),
            },
            status_code=400,
        )

    payment["status"] = "PAID"
    payment["payment_id"] = razorpay_payment_id
    payment["signature"] = razorpay_signature

    return {
        "success": True,
        "status": "PAID",
        "message": (
            "Payment verified successfully."
        ),
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
    }


# ============================================================
# MCP STREAMABLE HTTP
# ============================================================

transport_security = TransportSecuritySettings(
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
# LOCAL START
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )