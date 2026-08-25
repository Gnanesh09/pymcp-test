from __future__ import annotations

import contextlib
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.transport_security import TransportSecuritySettings


# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "QuickCart MCP"
APP_VERSION = "2.0.0"

PUBLIC_HOST = "pymcp-test.onrender.com"

MCP_URL = f"https://{PUBLIC_HOST}/mcp"

# ChatGPT Apps UI resource
PRODUCT_UI_URI = "ui://quickcart/product-catalogue.html"

# product_catalogue.html must be beside main.py
PRODUCT_UI_FILE = (
    Path(__file__).resolve().parent / "product_catalogue.html"
)


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
        "image": "https://placehold.co/600x400/png?text=Aashirvaad+Atta",
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
        "image": "https://placehold.co/600x400/png?text=Tata+Salt",
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
        "image": "https://placehold.co/600x400/png?text=Amul+Milk",
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
        "image": "https://placehold.co/600x400/png?text=Amul+Butter",
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
        "image": "https://placehold.co/600x400/png?text=Maggi",
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
        "image": "https://placehold.co/600x400/png?text=Lays",
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
        "image": "https://placehold.co/600x400/png?text=Coca-Cola",
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
        "image": "https://placehold.co/600x400/png?text=Red+Bull",
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
        "image": "https://placehold.co/600x400/png?text=Surf+Excel",
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
        "image": "https://placehold.co/600x400/png?text=Colgate",
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


# ============================================================
# HELPERS
# ============================================================

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text)


def get_product(
    product_id: str,
) -> dict[str, Any] | None:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product

    return None


def public_product(
    product: dict[str, Any],
) -> dict[str, Any]:
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


def calculate_cart(
    user_id: str,
) -> dict[str, Any]:
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
        "item_count": sum(
            item["quantity"] for item in items
        ),
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


# ============================================================
# MCP APPS EXTENSION
#
# IMPORTANT:
# Apps/resource/tool registration happens BEFORE
# MCPServer(...) is created.
# ============================================================

apps = Apps()

apps.add_html_resource(
    PRODUCT_UI_URI,
    load_product_ui(),
    name="quickcart-product-catalogue",
    title="QuickCart Product Catalogue",
    description=(
        "QuickCart product catalogue with images, "
        "prices, ratings and Add buttons."
    ),
    prefers_border=True,
)


# ============================================================
# UI-BOUND PRODUCT TOOLS
#
# These MUST be registered BEFORE MCPServer(...)
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
    """
    Search products by name, brand, category,
    description or tags.
    """

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

    matches: list[
        tuple[int, dict[str, Any]]
    ] = []

    for product in PRODUCTS:

        if category is not None:
            if (
                normalize(product["category"])
                != normalize(category)
            ):
                continue

        if max_price is not None:
            if product["price"] > max_price:
                continue

        searchable_text = normalize(
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
            if term in searchable_text
        )

        if score > 0:
            matches.append(
                (score, product)
            )

    matches.sort(
        key=lambda item: (
            -item[0],
            -item[1]["rating"],
            item[1]["price"],
        )
    )

    selected_products = [
        product
        for _, product in matches[:limit]
    ]

    return {
        "success": True,
        "query": query,
        "count": len(selected_products),
        "products": [
            public_product(product)
            for product in selected_products
        ],
    }


@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Product Catalogue",
    description=(
        "Browse QuickCart products by category "
        "using the interactive product catalogue."
    ),
)
def get_catalogue(
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Browse all products or a specific category.
    """

    limit = max(1, min(limit, 50))

    products = PRODUCTS

    if category is not None:
        products = [
            product
            for product in products
            if (
                normalize(product["category"])
                == normalize(category)
            )
        ]

    selected_products = products[:limit]

    return {
        "success": True,
        "category": category,
        "count": len(selected_products),
        "products": [
            public_product(product)
            for product in selected_products
        ],
    }


@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Product Details",
    description=(
        "Show product information in the "
        "QuickCart product interface."
    ),
)
def get_product_details(
    product_id: str,
) -> dict[str, Any]:
    """
    Get detailed information about a product.
    """

    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
            "count": 0,
            "products": [],
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
#
# Apps must already contain resources/tools here.
# ============================================================

mcp = MCPServer(
    APP_NAME,
    instructions="""
You are QuickCart, an agentic shopping assistant.

AVAILABLE SHOPPING CAPABILITIES:

- list categories
- search products
- browse catalogue
- inspect product details
- add products to cart
- update cart quantities
- remove products
- view cart
- clear cart
- checkout
- view orders
- check order status

IMPORTANT SHOPPING BEHAVIOR:

1. When the user says "find", "search", "show me",
   "browse", or similar product requests, use
   search_products() or get_catalogue().

2. Product search/catalogue/product-detail tools have an
   interactive UI when the connected ChatGPT client supports MCP Apps.

3. Never invent products, prices, stock, ratings or IDs.

4. Use returned product IDs when adding items to the cart.

5. For multi-item requests, search each required product
   when necessary.

6. Before ordering, inspect the current cart.

7. checkout(confirm=False) must never create an order.

8. Only call checkout(confirm=True) when the user explicitly
   asks to buy, order, checkout, or confirm the purchase.

9. After a successful checkout, report the real order ID
   returned by checkout().
""",
    extensions=[apps],
)


# ============================================================
# NORMAL MCP TOOLS
#
# These are registered AFTER MCPServer exists.
# ============================================================

@mcp.tool()
def list_categories() -> dict[str, Any]:
    """
    List all available shopping categories.
    """

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
    """
    Add a product to the shopping cart.
    """

    if quantity <= 0:
        return {
            "success": False,
            "error": (
                "Quantity must be greater than zero."
            ),
        }

    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
        }

    cart = CARTS.setdefault(
        user_id,
        {},
    )

    current_quantity = cart.get(
        product_id,
        0,
    )

    new_quantity = (
        current_quantity + quantity
    )

    if new_quantity > product["stock"]:
        return {
            "success": False,
            "error": (
                f"Only {product['stock']} units "
                f"of {product['name']} are available."
            ),
        }

    cart[product_id] = new_quantity

    return {
        "success": True,
        "message": (
            f"Added {quantity} × "
            f"{product['name']} to your cart."
        ),
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def update_cart_item(
    product_id: str,
    quantity: int,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Set the exact quantity of a cart item.
    quantity=0 removes it.
    """

    if quantity < 0:
        return {
            "success": False,
            "error": (
                "Quantity cannot be negative."
            ),
        }

    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
        }

    cart = CARTS.setdefault(
        user_id,
        {},
    )

    if quantity == 0:
        cart.pop(
            product_id,
            None,
        )

    else:
        if quantity > product["stock"]:
            return {
                "success": False,
                "error": (
                    f"Only {product['stock']} units "
                    f"of {product['name']} are available."
                ),
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
    """
    Remove a product completely from the cart.
    """

    cart = CARTS.setdefault(
        user_id,
        {},
    )

    removed = cart.pop(
        product_id,
        None,
    )

    return {
        "success": True,
        "removed": removed is not None,
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def get_cart(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Show the current shopping cart.
    """

    return {
        "success": True,
        "cart": calculate_cart(user_id),
    }


@mcp.tool()
def clear_cart(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Remove all products from the cart.
    """

    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Cart cleared.",
        "cart": calculate_cart(user_id),
    }


# ============================================================
# ORDER TOOLS
# ============================================================

@mcp.tool()
def checkout(
    confirm: bool,
    user_id: str = "demo-user",
    address: str = (
        "Demo address, Bengaluru, Karnataka"
    ),
    payment_method: str = "cash_on_delivery",
) -> dict[str, Any]:
    """
    Place the cart as an order.

    confirm=False = preview only.
    confirm=True = actually create the order.
    """

    cart = calculate_cart(user_id)

    if not cart["items"]:
        return {
            "success": False,
            "error": "Cart is empty.",
        }

    if not confirm:
        return {
            "success": False,
            "requires_confirmation": True,
            "message": (
                "Checkout preview only. "
                "No order was created."
            ),
            "cart": cart,
        }

    # Final stock check
    for item in cart["items"]:

        product = get_product(
            item["product_id"]
        )

        if product is None:
            return {
                "success": False,
                "error": (
                    f"Product {item['product_id']} "
                    "is no longer available."
                ),
            }

        if (
            item["quantity"]
            > product["stock"]
        ):
            return {
                "success": False,
                "error": (
                    f"Insufficient stock for "
                    f"{product['name']}."
                ),
            }

    order_id = (
        f"QC-{uuid.uuid4().hex[:10].upper()}"
    )

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "status": "CONFIRMED",
        "items": cart["items"],
        "subtotal": cart["subtotal"],
        "delivery_fee": cart["delivery_fee"],
        "total": cart["total"],
        "currency": cart["currency"],
        "address": address,
        "payment_method": payment_method,
    }

    ORDERS[order_id] = order

    # Reduce demo inventory
    for item in cart["items"]:

        product = get_product(
            item["product_id"]
        )

        if product is not None:
            product["stock"] -= (
                item["quantity"]
            )

    # Clear cart
    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Order placed successfully.",
        "order": order,
    }


@mcp.tool()
def get_order(
    order_id: str,
) -> dict[str, Any]:
    """
    Get an order by order ID.
    """

    order = ORDERS.get(
        order_id
    )

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
    """
    List all orders for a user.
    """

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
# FASTAPI APPLICATION
# ============================================================

@contextlib.asynccontextmanager
async def lifespan(
    _app: FastAPI,
):
    """
    Start the MCP session manager when mounted
    inside FastAPI.
    """

    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Agentic commerce MCP server for ChatGPT."
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
# NORMAL FASTAPI ROUTES
# ============================================================

@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "mcp_endpoint": MCP_URL,
        "ui_resource": PRODUCT_UI_URI,
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "products": len(PRODUCTS),
        "orders": len(ORDERS),
        "ui": "enabled",
    }


@app.get("/catalogue")
async def catalogue() -> dict[str, Any]:
    return {
        "success": True,
        "count": len(PRODUCTS),
        "products": PRODUCTS,
    }


# ============================================================
# MCP TRANSPORT SECURITY
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


# ============================================================
# MCP STREAMABLE HTTP
# ============================================================

mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    transport_security=transport_security,
)


# ============================================================
# MOUNT MCP
# ============================================================

app.mount(
    "/mcp",
    mcp_http_app,
)


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )