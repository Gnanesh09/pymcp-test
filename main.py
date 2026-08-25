from __future__ import annotations

import contextlib
import re
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


# ============================================================
# SHOPPING DATA
# Replace this later with PostgreSQL/MongoDB/your real APIs.
# ============================================================

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": "p001",
        "name": "Aashirvaad Atta 5kg",
        "category": "grocery",
        "price": 289,
        "mrp": 320,
        "discount": 10,
        "rating": 4.5,
        "stock": 50,
        "brand": "Aashirvaad",
        "unit": "5 kg",
        "description": "Premium whole wheat flour.",
        "image": "https://placehold.co/600x400/png?text=Aashirvaad+Atta",
        "tags": ["atta", "flour", "wheat", "grocery"],
    },
    {
        "id": "p002",
        "name": "Tata Salt 1kg",
        "category": "grocery",
        "price": 28,
        "mrp": 30,
        "discount": 7,
        "rating": 4.7,
        "stock": 100,
        "brand": "Tata",
        "unit": "1 kg",
        "description": "Iodised vacuum evaporated salt.",
        "image": "https://placehold.co/600x400/png?text=Tata+Salt",
        "tags": ["salt", "grocery"],
    },
    {
        "id": "p003",
        "name": "Amul Taaza Milk 1L",
        "category": "dairy",
        "price": 62,
        "mrp": 66,
        "discount": 6,
        "rating": 4.8,
        "stock": 40,
        "brand": "Amul",
        "unit": "1 litre",
        "description": "Fresh toned milk.",
        "image": "https://placehold.co/600x400/png?text=Amul+Milk",
        "tags": ["milk", "dairy", "breakfast"],
    },
    {
        "id": "p004",
        "name": "Amul Butter 500g",
        "category": "dairy",
        "price": 285,
        "mrp": 310,
        "discount": 8,
        "rating": 4.8,
        "stock": 25,
        "brand": "Amul",
        "unit": "500 g",
        "description": "Pasteurised table butter.",
        "image": "https://placehold.co/600x400/png?text=Amul+Butter",
        "tags": ["butter", "dairy"],
    },
    {
        "id": "p005",
        "name": "Maggi 2-Minute Noodles",
        "category": "snacks",
        "price": 14,
        "mrp": 15,
        "discount": 7,
        "rating": 4.6,
        "stock": 200,
        "brand": "Nestle",
        "unit": "70 g",
        "description": "Instant noodles.",
        "image": "https://placehold.co/600x400/png?text=Maggi",
        "tags": ["maggi", "noodles", "instant", "snacks"],
    },
    {
        "id": "p006",
        "name": "Lay's Magic Masala",
        "category": "snacks",
        "price": 20,
        "mrp": 20,
        "discount": 0,
        "rating": 4.4,
        "stock": 120,
        "brand": "Lay's",
        "unit": "50 g",
        "description": "Spicy potato chips.",
        "image": "https://placehold.co/600x400/png?text=Lays",
        "tags": ["chips", "snacks"],
    },
    {
        "id": "p007",
        "name": "Coca-Cola 750ml",
        "category": "beverages",
        "price": 40,
        "mrp": 45,
        "discount": 11,
        "rating": 4.3,
        "stock": 80,
        "brand": "Coca-Cola",
        "unit": "750 ml",
        "description": "Carbonated soft drink.",
        "image": "https://placehold.co/600x400/png?text=Coca-Cola",
        "tags": ["coke", "drink", "beverage", "soft drink"],
    },
    {
        "id": "p008",
        "name": "Red Bull Energy Drink",
        "category": "beverages",
        "price": 125,
        "mrp": 135,
        "discount": 7,
        "rating": 4.5,
        "stock": 35,
        "brand": "Red Bull",
        "unit": "250 ml",
        "description": "Energy drink.",
        "image": "https://placehold.co/600x400/png?text=Red+Bull",
        "tags": ["energy", "drink", "beverage"],
    },
    {
        "id": "p009",
        "name": "Surf Excel Matic 2kg",
        "category": "household",
        "price": 365,
        "mrp": 420,
        "discount": 13,
        "rating": 4.6,
        "stock": 20,
        "brand": "Surf Excel",
        "unit": "2 kg",
        "description": "Detergent powder for washing machines.",
        "image": "https://placehold.co/600x400/png?text=Surf+Excel",
        "tags": ["detergent", "washing", "household"],
    },
    {
        "id": "p010",
        "name": "Colgate MaxFresh",
        "category": "personal-care",
        "price": 99,
        "mrp": 115,
        "discount": 14,
        "rating": 4.5,
        "stock": 60,
        "brand": "Colgate",
        "unit": "150 g",
        "description": "Fresh breath toothpaste.",
        "image": "https://placehold.co/600x400/png?text=Colgate",
        "tags": ["toothpaste", "personal care"],
    },
]


# ============================================================
# DEMO STATE
# ============================================================

CARTS: dict[str, dict[str, int]] = {}
ORDERS: dict[str, dict[str, Any]] = {}


def get_product(product_id: str) -> dict[str, Any] | None:
    return next(
        (p for p in PRODUCTS if p["id"] == product_id),
        None,
    )


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text)


def product_card(product: dict[str, Any]) -> str:
    discount = (
        f" 🔥 {product['discount']}% OFF"
        if product["discount"] > 0
        else ""
    )

    return (
        f"### {product['name']}\n"
        f"**₹{product['price']}**  ~~₹{product['mrp']}~~{discount}\n\n"
        f"⭐ {product['rating']} · {product['unit']} · "
        f"{product['stock']} in stock\n\n"
        f"{product['description']}\n\n"
        f"![{product['name']}]({product['image']})\n\n"
        f"`{product['id']}`"
    )


def cart_summary(user_id: str) -> dict[str, Any]:
    items = CARTS.get(user_id, {})

    result = []
    subtotal = 0

    for product_id, quantity in items.items():
        product = get_product(product_id)

        if not product:
            continue

        line_total = product["price"] * quantity
        subtotal += line_total

        result.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "quantity": quantity,
                "unit_price": product["price"],
                "line_total": line_total,
                "image": product["image"],
            }
        )

    delivery_fee = 0 if subtotal >= 499 or subtotal == 0 else 39
    total = subtotal + delivery_fee

    return {
        "user_id": user_id,
        "items": result,
        "item_count": sum(item["quantity"] for item in result),
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total,
        "currency": "INR",
    }


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer(
    "QuickCart",
    title="QuickCart",
    description=(
        "Agentic grocery shopping MCP server. "
        "Search products, inspect catalogues, manage carts "
        "and place orders."
    ),
    version="1.0.0",
    instructions="""
You are connected to QuickCart.

Shopping workflow:
1. Search before buying when the user asks for a product.
2. Show useful product options using search_products or catalogue.
3. Inspect exact product details when needed.
4. Add requested products to the cart.
5. Re-check the cart before ordering.
6. Only call checkout with confirm=true when the user explicitly
   asks to place/confirm/order the purchase.
7. After checkout, report the order id and total.

For requests such as:
"find milk"
"find chips and coke"
"buy 2 Maggi and 1 milk"
"add everything"
"order my cart"

use the tools to perform the workflow rather than pretending
the action happened.
""",
)


# ============================================================
# READ TOOLS
# ============================================================

@mcp.tool()
def list_categories() -> dict[str, Any]:
    """List all shopping categories available in the store."""
    categories = sorted({p["category"] for p in PRODUCTS})

    return {
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
    Search products by name, brand, category, tags or description.

    Use this for natural-language shopping requests such as
    "chips", "milk", "things for breakfast", "cheap drinks", etc.
    """
    query_norm = normalize(query)
    terms = query_norm.split()

    matches = []

    for product in PRODUCTS:
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

        if category and normalize(product["category"]) != normalize(category):
            continue

        if max_price is not None and product["price"] > max_price:
            continue

        if score > 0:
            matches.append((score, product))

    matches.sort(
        key=lambda item: (
            -item[0],
            -item[1]["rating"],
            item[1]["price"],
        )
    )

    products = [product for _, product in matches[:limit]]

    catalogue_markdown = (
        "\n\n---\n\n".join(product_card(p) for p in products)
        if products
        else "No matching products found."
    )

    return {
        "query": query,
        "count": len(products),
        "products": products,
        "catalogue_markdown": catalogue_markdown,
    }


@mcp.tool()
def get_product_details(product_id: str) -> dict[str, Any]:
    """Get complete details for one product by product ID."""
    product = get_product(product_id)

    if not product:
        return {
            "success": False,
            "error": "Product not found",
            "product_id": product_id,
        }

    return {
        "success": True,
        "product": product,
        "display": product_card(product),
    }


@mcp.tool()
def get_catalogue(
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return the store catalogue.

    Use this when the user asks to browse products,
    see products, show the catalogue, or shop a category.
    """
    products = PRODUCTS

    if category:
        products = [
            p
            for p in products
            if normalize(p["category"]) == normalize(category)
        ]

    products = products[:limit]

    return {
        "count": len(products),
        "category": category,
        "products": products,
        "catalogue_markdown": (
            "\n\n---\n\n".join(product_card(p) for p in products)
            if products
            else "No products found."
        ),
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
    Add one product to the shopping cart.

    This is a write action.
    """
    if quantity <= 0:
        return {
            "success": False,
            "error": "Quantity must be greater than zero.",
        }

    product = get_product(product_id)

    if not product:
        return {
            "success": False,
            "error": "Product not found.",
        }

    current = CARTS.setdefault(user_id, {}).get(product_id, 0)

    if current + quantity > product["stock"]:
        return {
            "success": False,
            "error": f"Only {product['stock']} units are available.",
        }

    CARTS[user_id][product_id] = current + quantity

    return {
        "success": True,
        "message": f"Added {quantity} × {product['name']}.",
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def update_cart_item(
    product_id: str,
    quantity: int,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """
    Set the exact quantity of a cart item.

    quantity=0 removes the item.
    """
    product = get_product(product_id)

    if not product:
        return {
            "success": False,
            "error": "Product not found.",
        }

    if quantity < 0:
        return {
            "success": False,
            "error": "Quantity cannot be negative.",
        }

    if quantity == 0:
        CARTS.setdefault(user_id, {}).pop(product_id, None)
    else:
        if quantity > product["stock"]:
            return {
                "success": False,
                "error": f"Only {product['stock']} units are available.",
            }

        CARTS.setdefault(user_id, {})[product_id] = quantity

    return {
        "success": True,
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def remove_from_cart(
    product_id: str,
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Remove one product completely from the cart."""
    CARTS.setdefault(user_id, {}).pop(product_id, None)

    return {
        "success": True,
        "cart": cart_summary(user_id),
    }


@mcp.tool()
def get_cart(user_id: str = "demo-user") -> dict[str, Any]:
    """View the current shopping cart and calculated total."""
    return cart_summary(user_id)


@mcp.tool()
def clear_cart(user_id: str = "demo-user") -> dict[str, Any]:
    """Remove all items from the shopping cart."""
    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Cart cleared.",
        "cart": cart_summary(user_id),
    }


# ============================================================
# CHECKOUT / ORDER TOOLS
# ============================================================

@mcp.tool()
def checkout(
    confirm: bool,
    user_id: str = "demo-user",
    address: str = "Demo address, Bengaluru, Karnataka",
    payment_method: str = "cash_on_delivery",
) -> dict[str, Any]:
    """
    Place the current cart as an order.

    IMPORTANT:
    Only use confirm=true when the user explicitly requested
    the order/purchase to be placed.

    This is the final side-effecting shopping action.
    """
    if not confirm:
        return {
            "success": False,
            "requires_confirmation": True,
            "message": (
                "Checkout was not executed. "
                "Ask the user to explicitly confirm the order."
            ),
            "cart": cart_summary(user_id),
        }

    cart = cart_summary(user_id)

    if not cart["items"]:
        return {
            "success": False,
            "error": "Cart is empty.",
        }

    order_id = f"QC-{uuid.uuid4().hex[:10].upper()}"

    order = {
        "order_id": order_id,
        "user_id": user_id,
        "items": cart["items"],
        "subtotal": cart["subtotal"],
        "delivery_fee": cart["delivery_fee"],
        "total": cart["total"],
        "currency": "INR",
        "status": "CONFIRMED",
        "payment_method": payment_method,
        "address": address,
    }

    ORDERS[order_id] = order

    # Empty cart after successful checkout.
    CARTS[user_id] = {}

    return {
        "success": True,
        "message": "Order placed successfully.",
        "order": order,
    }


@mcp.tool()
def get_order(order_id: str) -> dict[str, Any]:
    """Get the status and details of an order."""
    order = ORDERS.get(order_id)

    if not order:
        return {
            "success": False,
            "error": "Order not found.",
        }

    return {
        "success": True,
        "order": order,
    }


@mcp.tool()
def list_orders(user_id: str = "demo-user") -> dict[str, Any]:
    """List all orders belonging to a user."""
    orders = [
        order
        for order in ORDERS.values()
        if order["user_id"] == user_id
    ]

    return {
        "count": len(orders),
        "orders": orders,
    }


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="QuickCart Agentic Commerce API",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "QuickCart",
        "status": "online",
        "mcp_endpoint": "/mcp",
        "message": "Agentic shopping MCP server",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "products": len(PRODUCTS),
        "orders": len(ORDERS),
    }


@app.get("/catalogue")
async def catalogue_http():
    return {
        "count": len(PRODUCTS),
        "products": PRODUCTS,
    }


# ============================================================
# MOUNT MCP INTO FASTAPI
# ============================================================

# The MCP SDK v2 uses streamable HTTP for remote MCP connections.
# For local development, localhost/127.0.0.1 are automatically
# protected by the SDK's DNS-rebinding safeguards.
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app.router.lifespan_context = lifespan

# Mount the MCP ASGI application under /mcp.
app.mount("/", mcp_app)


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