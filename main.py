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
# CONFIG
# ============================================================

APP_NAME = "QuickCart MCP"
APP_VERSION = "1.0.0"

# Your Render hostname.
RENDER_HOST = "pymcp-test.onrender.com"

# MCP endpoint exposed to ChatGPT:
# https://pymcp-test.onrender.com/mcp


# ============================================================
# PRODUCT DATABASE
# Replace this later with PostgreSQL / MongoDB / real APIs.
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
# IN-MEMORY STATE
# IMPORTANT:
# This is only for testing.
# Replace with a real DB before production.
# ============================================================

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
    return next(
        (product for product in PRODUCTS if product["id"] == product_id),
        None,
    )


def product_display(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": product["id"],
        "name": product["name"],
        "brand": product["brand"],
        "price": product["price"],
        "mrp": product["mrp"],
        "discount": product["discount"],
        "rating": product["rating"],
        "stock": product["stock"],
        "unit": product["unit"],
        "description": product["description"],
        "image": product["image"],
        "category": product["category"],
    }


def cart_summary(user_id: str) -> dict[str, Any]:
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

    delivery_fee = 0 if subtotal == 0 or subtotal >= 499 else 39
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


def catalogue_markdown(products: list[dict[str, Any]]) -> str:
    if not products:
        return "No products found."

    blocks: list[str] = []

    for product in products:
        discount_text = ""

        if product["discount"] > 0:
            discount_text = f" • {product['discount']}% OFF"

        blocks.append(
            f"### {product['name']}\n"
            f"**₹{product['price']}** "
            f"(MRP ₹{product['mrp']}){discount_text}\n\n"
            f"⭐ {product['rating']} • "
            f"{product['unit']} • "
            f"{product['stock']} in stock\n\n"
            f"{product['description']}\n\n"
            f"![{product['name']}]({product['image']})\n\n"
            f"Product ID: `{product['id']}`"
        )

    return "\n\n---\n\n".join(blocks)


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer(
    name=APP_NAME,
    instructions="""
You are the shopping agent for QuickCart.

You can search products, browse the catalogue, inspect products,
manage the user's cart, and place orders.

IMPORTANT WORKFLOW:

1. Search products when the user asks to find something.
2. Show relevant products and prices.
3. Ask/use additional searches when a request contains multiple
   product types.
4. Add requested products to the user's cart.
5. Show or inspect the cart before checkout.
6. Only execute checkout with confirm=true when the user explicitly
   wants to place/confirm/order the purchase.
7. Never invent stock, prices, product IDs, or order IDs.
8. After a successful checkout, return the order ID and total.

Examples:

"Find me chips"
-> search_products()

"Show me snacks"
-> get_catalogue(category="snacks")

"Add 2 Maggi"
-> search_products() if product ID is unknown
-> add_to_cart()

"Show my cart"
-> get_cart()

"Order everything"
-> get_cart()
-> checkout(confirm=true)
""",
    json_response=True,
    streamable_http_path="/mcp",
)


# ============================================================
# MCP READ TOOLS
# ============================================================

@mcp.tool()
def list_categories() -> dict[str, Any]:
    """List every product category available in QuickCart."""
    categories = sorted(
        {product["category"] for product in PRODUCTS}
    )

    return {
        "success": True,
        "count": len(categories),
        "categories": categories,
    }


@mcp.tool()
def search_products(
    query: str,
    category: str | None = None,
    max_price: int | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """
    Search the QuickCart product catalogue.

    Search matches product name, brand, category, description,
    and tags.
    """
    if not query.strip():
        return {
            "success": False,
            "error": "Search query cannot be empty.",
        }

    if limit < 1:
        limit = 1

    limit = min(limit, 50)

    normalized_query = normalize(query)
    terms = normalized_query.split()

    matches: list[tuple[int, dict[str, Any]]] = []

    for product in PRODUCTS:
        if category:
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

        score = 0

        for term in terms:
            if term in searchable:
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

    products = [
        product_display(product)
        for _, product in matches[:limit]
    ]

    raw_products = [
        product
        for _, product in matches[:limit]
    ]

    return {
        "success": True,
        "query": query,
        "count": len(products),
        "products": products,
        "catalogue_markdown": catalogue_markdown(raw_products),
    }


@mcp.tool()
def get_catalogue(
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Browse the QuickCart catalogue.

    Use this when the user wants to see products or browse
    a category.
    """
    limit = max(1, min(limit, 50))

    products = PRODUCTS

    if category:
        products = [
            product
            for product in products
            if normalize(product["category"]) == normalize(category)
        ]

    selected = products[:limit]

    return {
        "success": True,
        "category": category,
        "count": len(selected),
        "products": [
            product_display(product)
            for product in selected
        ],
        "catalogue_markdown": catalogue_markdown(selected),
    }


@mcp.tool()
def get_product_details(product_id: str) -> dict[str, Any]:
    """Get complete information for one product."""
    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
            "product_id": product_id,
        }

    return {
        "success": True,
        "product": product_display(product),
    }


# ============================================================
# MCP CART TOOLS
# ============================================================

@mcp.tool()
def add_to_cart(
    product_id: str,
    quantity: int = 1,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Add a product to the user's cart."""
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

    user_cart = CARTS.setdefault(user_id, {})

    existing_quantity = user_cart.get(product_id, 0)
    new_quantity = existing_quantity + quantity

    if new_quantity > product["stock"]:
        return {
            "success": False,
            "error": (
                f"Only {product['stock']} units of "
                f"{product['name']} are available."
            ),
        }

    user_cart[product_id] = new_quantity

    return {
        "success": True,
        "message": (
            f"Added {quantity} × {product['name']} "
            "to your cart."
        ),
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def update_cart_item(
    product_id: str,
    quantity: int,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Set the exact quantity for a cart item.

    Set quantity to 0 to remove it.
    """
    product = get_product(product_id)

    if product is None:
        return {
            "success": False,
            "error": "Product not found.",
        }

    if quantity < 0:
        return {
            "success": False,
            "error": "Quantity cannot be negative.",
        }

    user_cart = CARTS.setdefault(user_id, {})

    if quantity == 0:
        user_cart.pop(product_id, None)
    else:
        if quantity > product["stock"]:
            return {
                "success": False,
                "error": (
                    f"Only {product['stock']} units "
                    "are available."
                ),
            }

        user_cart[product_id] = quantity

    return {
        "success": True,
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def remove_from_cart(
    product_id: str,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Remove a product completely from the cart."""
    user_cart = CARTS.setdefault(user_id, {})
    removed = user_cart.pop(product_id, None)

    return {
        "success": True,
        "removed": removed is not None,
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def get_cart(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Show the current cart, subtotal, delivery fee and total."""
    return {
        "success": True,
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def clear_cart(
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Remove everything from the user's cart."""
    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Cart cleared.",
        "cart": cart_summary(user_id),
    }


# ============================================================
# MCP ORDER TOOLS
# ============================================================

@mcp.tool()
def checkout(
    confirm: bool,
    user_id: str = "demo-user",
    address: str = "Demo address, Bengaluru, Karnataka",
    payment_method: str = "cash_on_delivery",
) -> dict[str, Any]:
    """
    Place the user's cart as an order.

    confirm MUST be true only after the user explicitly requests
    checkout/order/purchase confirmation.

    This is a side-effecting action.
    """
    cart = cart_summary(user_id)

    if not cart["items"]:
        return {
            "success": False,
            "error": "Your cart is empty.",
        }

    if not confirm:
        return {
            "success": False,
            "requires_confirmation": True,
            "message": (
                "Checkout has NOT been executed. "
                "The user must explicitly confirm the purchase."
            ),
            "cart": cart,
        }

    # Final inventory validation.
    for item in cart["items"]:
        product = get_product(item["product_id"])

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
                    f"Not enough stock for "
                    f"{product['name']}."
                ),
            }

    order_id = f"QC-{uuid.uuid4().hex[:10].upper()}"

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "items": cart["items"],
        "subtotal": cart["subtotal"],
        "delivery_fee": cart["delivery_fee"],
        "total": cart["total"],
        "currency": cart["currency"],
        "status": "CONFIRMED",
        "payment_method": payment_method,
        "address": address,
    }

    ORDERS[order_id] = order

    # Update demo inventory.
    for item in cart["items"]:
        product = get_product(item["product_id"])

        if product is not None:
            product["stock"] -= item["quantity"]

    # Empty cart.
    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Order placed successfully.",
        "order": order,
    }


@mcp.tool()
def get_order(order_id: str) -> dict[str, Any]:
    """Get one order using its order ID."""
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
    """List all orders belonging to a user."""
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
async def lifespan(app: FastAPI):
    """
    Start the MCP Streamable HTTP session manager.

    This is required when the MCP app is mounted inside FastAPI.
    """
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Agentic commerce MCP server for ChatGPT.",
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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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
        "mcp_endpoint": f"https://{RENDER_HOST}/mcp",
        "tools": [
            "list_categories",
            "search_products",
            "get_catalogue",
            "get_product_details",
            "add_to_cart",
            "update_cart_item",
            "remove_from_cart",
            "get_cart",
            "clear_cart",
            "checkout",
            "get_order",
            "list_orders",
        ],
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

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        RENDER_HOST,
        f"{RENDER_HOST}:443",
    ],
    allowed_origins=[
        "https://chatgpt.com",
        "https://chat.openai.com",
    ],
)


# ============================================================
# MCP STREAMABLE HTTP APP
# ============================================================

# We mount this app at /mcp.
#
# By setting streamable_http_path="/", the final endpoint is:
#
# https://pymcp-test.onrender.com/mcp
#
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
        port=8000,
        reload=True,
    )