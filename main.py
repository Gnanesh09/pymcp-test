from __future__ import annotations

import contextlib
import re
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "QuickCart MCP"
APP_VERSION = "1.0.0"

# Render hostname
PUBLIC_HOST = "pymcp-test.onrender.com"

# The MCP URL will be:
# https://pymcp-test.onrender.com/mcp


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
# For testing only.
# Replace with PostgreSQL/MongoDB in production.

CARTS: dict[str, dict[str, int]] = {}
ORDERS: dict[str, dict[str, Any]] = {}


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


def build_catalogue_text(
    products: list[dict[str, Any]],
) -> str:
    if not products:
        return "No matching products found."

    blocks: list[str] = []

    for product in products:
        discount = ""

        if product["discount"] > 0:
            discount = f" | {product['discount']}% OFF"

        blocks.append(
            f"### {product['name']}\n"
            f"Brand: {product['brand']}\n"
            f"Price: ₹{product['price']}\n"
            f"MRP: ₹{product['mrp']}\n"
            f"Rating: ⭐ {product['rating']}\n"
            f"Unit: {product['unit']}\n"
            f"Stock: {product['stock']}\n"
            f"{discount}\n"
            f"Product ID: {product['id']}\n"
            f"Image: {product['image']}"
        )

    return "\n\n--------------------\n\n".join(blocks)


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

    delivery_fee = 0

    if subtotal > 0 and subtotal < 499:
        delivery_fee = 39

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


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer(
    APP_NAME,
    instructions="""
You are QuickCart, an agentic shopping assistant.

You have tools for:
- browsing products
- searching products
- getting product details
- managing a shopping cart
- creating orders
- checking order status

Rules:

1. When the user asks to find something, search first.
2. Never invent product information.
3. Use product IDs returned by search/catalogue tools.
4. For multi-product requests, search for each required product
   when necessary.
5. Before ordering, inspect the current cart.
6. Never call checkout with confirm=true unless the user has
   explicitly requested the purchase/order/checkout.
7. After an order succeeds, return the order ID and total.
""",
)


# ============================================================
# PRODUCT TOOLS
# ============================================================

@mcp.tool()
def list_categories() -> dict[str, Any]:
    """
    List all available shopping categories.
    """
    categories = sorted(
        {product["category"] for product in PRODUCTS}
    )

    return {
        "success": True,
        "categories": categories,
        "count": len(categories),
    }


@mcp.tool()
def search_products(
    query: str,
    category: str | None = None,
    max_price: int | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """
    Search the product catalogue by name, brand, category,
    description, or tags.
    """
    if not query.strip():
        return {
            "success": False,
            "error": "Search query cannot be empty.",
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

        score = 0

        for term in terms:
            if term in searchable_text:
                score += 1

        if score > 0:
            matches.append((score, product))

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
        "catalogue": build_catalogue_text(
            selected_products
        ),
    }


@mcp.tool()
def get_catalogue(
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Browse the product catalogue.
    """
    limit = max(1, min(limit, 50))

    products = PRODUCTS

    if category is not None:
        products = [
            product
            for product in products
            if normalize(product["category"])
            == normalize(category)
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
        "catalogue": build_catalogue_text(
            selected_products
        ),
    }


@mcp.tool()
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
            "product_id": product_id,
        }

    return {
        "success": True,
        "product": public_product(product),
    }


# ============================================================
# CART TOOLS
# ============================================================

@mcp.tool()
def add_to_cart(
    product_id: str,
    quantity: int = 1,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Add a product to the user's cart.
    """
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

    current_quantity = cart.get(
        product_id,
        0,
    )

    new_quantity = current_quantity + quantity

    if new_quantity > product["stock"]:
        return {
            "success": False,
            "error": (
                f"Only {product['stock']} units of "
                f"{product['name']} are available."
            ),
        }

    cart[product_id] = new_quantity

    return {
        "success": True,
        "message": (
            f"Added {quantity} × "
            f"{product['name']} to cart."
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
    Set the exact quantity for a cart item.
    Use quantity=0 to remove the item.
    """
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
                "error": (
                    f"Only {product['stock']} units "
                    "are available."
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
    cart = CARTS.setdefault(user_id, {})

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
    Get the user's current cart.
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
    Remove every item from the cart.
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
    address: str = "Demo address, Bengaluru, Karnataka",
    payment_method: str = "cash_on_delivery",
) -> dict[str, Any]:
    """
    Place the cart as an order.

    confirm=true is required to actually create the order.
    Only use it after the user explicitly asks to order,
    checkout, buy, or confirm the purchase.
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
                "Checkout was not executed. "
                "Explicit purchase confirmation is required."
            ),
            "cart": cart,
        }

    # Verify stock one final time.
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

        if item["quantity"] > product["stock"]:
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

    # Reduce demo stock.
    for item in cart["items"]:
        product = get_product(
            item["product_id"]
        )

        if product is not None:
            product["stock"] -= item["quantity"]

    # Clear cart.
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
# FASTAPI APP
# ============================================================

@contextlib.asynccontextmanager
async def lifespan(
    _app: FastAPI,
):
    """
    Start the MCP session manager when MCP is mounted
    inside the FastAPI application.
    """
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
        "mcp_endpoint": (
            f"https://{PUBLIC_HOST}/mcp"
        ),
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "products": len(PRODUCTS),
        "orders": len(ORDERS),
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
#
# This creates an ASGI app containing:
#
# /mcp
#
# We mount it directly below.
#
# json_response=True is a transport option,
# NOT an MCPServer constructor option.
# ============================================================

mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    transport_security=transport_security,
)


# ============================================================
# MOUNT MCP UNDER /mcp
# ============================================================

app.mount(
    "/mcp",
    mcp_http_app,
)


# ============================================================
# LOCAL EXECUTION
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )