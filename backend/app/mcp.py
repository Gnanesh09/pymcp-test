
from __future__ import annotations

"""
Umon Mart — Remote MCP / ChatGPT integration.

This module is deliberately a thin protocol adapter over the existing Umon
commerce services. It does not create a second cart, wallet, policy engine,
or payment system.

Flow:
    ChatGPT / MCP client
        -> OAuth 2.1
        -> /mcp (Streamable HTTP)
        -> authenticated Clerk user
        -> existing Umon services
        -> catalog / cart / policy / checkout / orders / audit

Money boundary:
    The model never supplies the final charge amount. Umon recomputes the
    current cart and the existing checkout service performs the authoritative
    policy, balance, inventory, order, ledger and audit operations.

Run as a dedicated MCP process during development:
    python -m app.mcp

Your normal Umon API can continue to run on port 8001.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
import secrets
from typing import Any, AsyncGenerator

import httpx
from urllib.parse import urlencode, urlparse

import jwt
from pydantic import BaseModel, Field
from fastmcp import Context, FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.server.dependencies import get_http_headers
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jwt import PyJWKClient

from .config import settings
from .db import lifespan as db_lifespan
from .db import get_db, utc_now
from .models import public_agent, public_product
from .policies import evaluate_purchase
from .security import get_current_claims
from .services import (
    add_to_cart as service_add_to_cart,
    agent_stats,
    audit,
    checkout_with_agent_balance,
    clear_cart as service_clear_cart,
    get_cart as service_get_cart,
    get_owned_agent,
    get_recommendations as service_get_recommendations,
    remove_cart_item as service_remove_cart_item,
    search_products as service_search_products,
    update_cart_item as service_update_cart_item,
)
from .langgraph_agent import graph_description, run_shopping_assistant


# ============================================================
# CONFIG
# ============================================================

MCP_APP_NAME = "Umon Mart"
MCP_APP_VERSION = "1.0.0"
MCP_SCOPE = "umon"

FRONTEND_URL = os.getenv(
    "UMON_FRONTEND_URL",
    "http://localhost:3000",
).strip().rstrip("/")

MCP_PUBLIC_URL = os.getenv(
    "MCP_PUBLIC_URL",
    "http://localhost:8002",
).strip().rstrip("/")

MCP_ENDPOINT = f"{MCP_PUBLIC_URL}/mcp"

UMON_WIDGET_DOMAIN = os.getenv(
    "UMON_WIDGET_DOMAIN",
    MCP_PUBLIC_URL,
).strip().rstrip("/")

# Image hosts currently used by seeded Umon products. The browser widget uses
# the proxy below so third-party image CSP/redirect/CORS behavior does not
# determine whether a product image renders.
UI_IMAGE_HOSTS = {
    "encrypted-tbn0.gstatic.com",
    "encrypted-tbn1.gstatic.com",
    "banerjeesupermarket.com",
}

OAUTH_CODE_TTL_SECONDS = 120
OAUTH_ACCESS_TTL_SECONDS = 3600
OAUTH_REFRESH_TTL_SECONDS = 60 * 60 * 24 * 30

PRODUCT_UI_URI = "ui://umon/product-catalogue.html"


# ============================================================
# MONGO OAUTH STATE
# ============================================================


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc_datetime(value: Any) -> datetime | None:
    """
    Normalize Mongo/PyMongo datetime values to timezone-aware UTC.
    """
    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _token_datetime_is_valid(
    expires_at: Any,
) -> bool:
    normalized = _as_utc_datetime(
        expires_at
    )

    if normalized is None:
        return False

    return normalized > utc_now()

async def _cleanup_oauth() -> None:
    db = get_db()
    now = utc_now()

    await db.mcp_oauth_codes.delete_many(
        {"expires_at": {"$lte": now}}
    )

    await db.mcp_oauth_tokens.delete_many(
        {"expires_at": {"$lte": now}}
    )

    await db.mcp_oauth_refresh_tokens.delete_many(
        {"expires_at": {"$lte": now}}
    )


# ============================================================
# CLERK AUTH FOR OAUTH CONSENT / MCP FALLBACK
# ============================================================

_jwks_client = PyJWKClient(settings.clerk_jwks_url)


async def _verify_clerk_token(token: str) -> dict[str, Any]:
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Clerk session token is required.",
        )

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)

        decode_options: dict[str, Any] = {
            "algorithms": ["RS256"],
            "issuer": settings.clerk_issuer,
            "leeway": 10,
            "options": {"verify_aud": False},
        }

        claims = jwt.decode(
            token,
            signing_key.key,
            **decode_options,
        )

        if settings.clerk_authorized_party:
            azp = claims.get("azp")
            if azp and azp != settings.clerk_authorized_party:
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized session issuer.",
                )

        if not claims.get("sub"):
            raise HTTPException(
                status_code=401,
                detail="Clerk token missing subject.",
            )

        return claims

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Clerk session token: {exc}",
        ) from exc


async def _ensure_active_user(
    clerk_user_id: str,
    claims: dict[str, Any] | None = None,
) -> None:
    db = get_db()

    now = utc_now()
    user = await db.users.find_one_and_update(
        {"clerk_user_id": clerk_user_id},
        {
            "$set": {
                "email": claims.get("email") if claims else None,
                "updated_at": now,
            },
            "$setOnInsert": {
                "clerk_user_id": clerk_user_id,
                "status": "ACTIVE",
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
    )

    if not user or user.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="Umon user account is not active.",
        )


# ============================================================
# MCP AUTHORIZATION
# ============================================================

async def _resolve_mcp_user(ctx: Context | None = None) -> str:
    """
    Resolve the authenticated Umon user from the FastMCP HTTP bearer token.

    FastMCP does not expose HTTP headers as ``ctx.headers``. The supported
    HTTP helper is ``get_http_headers()``.
    """
    headers = get_http_headers(include_all=True) or {}

    authorization = (
        headers.get("authorization")
        or headers.get("Authorization")
        or ""
    ).strip()

    if not authorization.lower().startswith("bearer "):
        raise PermissionError("Umon authentication is required.")

    bearer = authorization[7:].strip()

    if not bearer:
        raise PermissionError("Empty bearer token.")

    await _cleanup_oauth()
    db = get_db()

    oauth_token = await db.mcp_oauth_tokens.find_one(
        {
            "token_hash": _hash(bearer),
            "resource": MCP_ENDPOINT,
        }
    )

    if oauth_token:
        if not _token_datetime_is_valid(
            oauth_token.get("expires_at")
        ):
            raise PermissionError(
                "Umon MCP access token expired."
            )

        user_id = str(
            oauth_token["clerk_user_id"]
        )

        await _ensure_active_user(user_id)

        return user_id

    # Local MCP Inspector convenience:
    # allow a valid Clerk JWT directly.
    try:
        claims = await _verify_clerk_token(bearer)
        user_id = str(claims["sub"])

        await _ensure_active_user(
            user_id,
            claims,
        )

        return user_id
    except HTTPException as exc:
        raise PermissionError(
            str(exc.detail)
        ) from exc


async def _user(ctx: Context) -> str:
    try:
        return await _resolve_mcp_user(ctx)
    except PermissionError as exc:
        raise RuntimeError(str(exc)) from exc


# ============================================================
# SAFE PUBLIC REPRESENTATIONS
# ============================================================


def _money(paise: int) -> float:
    return round(int(paise) / 100, 2)


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_json(item)
            for key, item in value.items()
            if key != "_id"
        }
    if isinstance(value, list):
        return [_safe_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

def _safe_product(product: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize either:
      1. a raw Mongo product containing `_id`, or
      2. an already-public product containing `id`.

    services.search_products() already returns public_product(...)
    objects, so calling public_product() a second time causes:
        KeyError: '_id'
    """

    if "_id" in product:
        result = dict(
            public_product(product)
        )
    else:
        # Already in public form.
        result = dict(product)

    # Make the tool response easy for an LLM to consume.
    if "price_paise" in result:
        result["price"] = _money(
            int(result["price_paise"])
        )

    if "mrp_paise" in result:
        result["mrp"] = _money(
            int(result["mrp_paise"])
        )

    image = result.get("image")
    if isinstance(image, str) and image.startswith(("http://", "https://")):
        try:
            host = urlparse(image).hostname or ""
            host = host.lower().rstrip(".")
            if host in UI_IMAGE_HOSTS:
                result["image"] = (
                    f"{MCP_PUBLIC_URL}/assets/image-proxy?"
                    f"{urlencode({'url': image})}"
                )
        except Exception:
            result["image"] = None

    return _safe_json(result)


def _safe_agent(agent: dict[str, Any]) -> dict[str, Any]:
    return _safe_json(public_agent(agent))


def _error(
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            **extra,
        },
    }


# ============================================================
# MCP SERVER
# ============================================================

# ============================================================
# FASTMCP APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
    """
    Reuse Umon's existing MongoDB startup/shutdown lifecycle.
    FastMCP owns the HTTP transport lifecycle.
    """
    async with db_lifespan(server):
        yield


mcp = FastMCP(
    name=MCP_APP_NAME,
    instructions=(
        "Umon Mart makes this merchant sellable to AI buyers. "
        "For user-facing product discovery, recommendations, basket building, or shopping, prefer the single composite shopping_assist tool. "
        "Do not call search_offers, get_recommendations, or get_cart_recommendations as separate user-facing steps when shopping_assist can satisfy the request; those tools are supporting lookups and do not render an app. "
        "Only make another catalogue lookup when the first result genuinely lacks required live evidence or the user explicitly asks for a different lookup. "
        "Use live catalog data before making product claims. "
        "The shared cart belongs to the user, not an agent. "
        "At checkout, use the user's selected purchasing agent. "
        "The backend is authoritative for price, stock, merchant settings, "
        "agent policy, balance, payment, order and audit state. "
        "Never override BLOCK or CONFIRM decisions. "
        "Never invent payment success. "
        "Only call checkout after clear user authorization. "
        "When a shopping request can benefit from a visual catalogue/cart/checkout result, use the corresponding MCP App tool so the user can see verified Umon data. "
    ),
    lifespan=app_lifespan,
)


# ============================================================
# ACCOUNT / AGENT TOOLS
# ============================================================

@mcp.tool()
async def list_my_agents(ctx: Context) -> dict[str, Any]:
    """List the authenticated Umon user's purchasing agents."""
    user_id = await _user(ctx)
    db = get_db()

    agents = await (
        db.agents.find({"owner_clerk_user_id": user_id})
        .sort("created_at", -1)
        .limit(50)
        .to_list(length=50)
    )

    return {
        "success": True,
        "agents": [_safe_agent(agent) for agent in agents],
    }


@mcp.tool()
async def get_my_agent(
    agent_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Get one purchasing agent owned by the authenticated user."""
    user_id = await _user(ctx)

    agent = await get_owned_agent(
        user_id,
        agent_id,
    )

    if not agent:
        return _error(
            "AGENT_NOT_FOUND",
            "Agent not found or not owned by this user.",
        )

    return {
        "success": True,
        "agent": _safe_agent(agent),
    }


@mcp.tool()
async def get_agent_policy(
    agent_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Return the exact current purchasing policy for an owned agent."""
    user_id = await _user(ctx)

    agent = await get_owned_agent(
        user_id,
        agent_id,
    )

    if not agent:
        return _error(
            "AGENT_NOT_FOUND",
            "Agent not found or not owned by this user.",
        )

    return {
        "success": True,
        "agent_id": agent_id,
        "policy": _safe_json(agent.get("policy", {})),
    }


@mcp.tool()
async def get_agent_spending(
    agent_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Return balance, daily/monthly spend and purchasing limits."""
    user_id = await _user(ctx)

    try:
        stats = await agent_stats(
            user_id,
            agent_id,
        )
    except ValueError as exc:
        return _error(
            "AGENT_NOT_FOUND",
            str(exc),
        )

    return {
        "success": True,
        "agent": stats.get("agent"),
        "balance": stats.get("balance"),
        "spending": stats.get("spending"),
        "funding": stats.get("funding"),
        "limits": stats.get("limits"),
    }


# ============================================================
# CATALOG
# ============================================================

@mcp.tool()
async def search_offers(
    query: str = "",
    category: str | None = None,
    max_price: float | None = None,
    limit: int = 8,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Internal catalog lookup. Use shopping_assist for user-facing shopping/browsing so only one Store UI is rendered per turn."""
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    await _user(ctx)

    if max_price is not None and max_price < 0:
        return _error(
            "INVALID_MAX_PRICE",
            "Maximum price cannot be negative.",
        )

    products = await service_search_products(
        query=query,
        category=category,
        max_price_paise=(
            round(max_price * 100)
            if max_price is not None
            else None
        ),
        limit=max(1, min(int(limit), 20)),
    )

    return {
        "success": True,
        "query": query,
        "category": category,
        "count": len(products),
        "products": [
            _safe_product(product)
            for product in products
        ],
    }


@mcp.tool()
async def get_offer(
    product_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Internal lookup for one live active offer. Do not use this to create a separate user-facing catalogue surface."""
    await _user(ctx)
    db = get_db()

    product = await db.products.find_one(
        {
            "_id": product_id,
            "merchant_id": settings.merchant_id,
            "active": True,
        }
    )

    if not product:
        return _error(
            "OFFER_NOT_FOUND",
            "This offer is unavailable.",
        )

    return {
        "success": True,
        "offer": _safe_product(product),
    }


@mcp.tool()
async def list_categories(ctx: Context) -> dict[str, Any]:
    """List active product categories currently available in Umon Mart."""
    await _user(ctx)
    db = get_db()

    categories = await db.products.distinct(
        "category",
        {
            "merchant_id": settings.merchant_id,
            "active": True,
        },
    )

    return {
        "success": True,
        "categories": sorted(
            str(category)
            for category in categories
        ),
    }


# ============================================================
# CROSS-SELL / UPSELL
# ============================================================

@mcp.tool()
async def get_recommendations(
    product_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """
    Internal recommendation lookup. Prefer shopping_assist for user-facing
    recommendations so the Store UI is rendered once with a coherent set.

    Recommendations are advisory: this tool never adds items to the cart
    and never spends money.
    """
    await _user(ctx)

    products = await service_get_recommendations(
        product_id
    )

    return {
        "success": True,
        "product_id": product_id,
        "recommendations": [
            _safe_json(product)
            for product in products
        ],
    }


@mcp.tool()
async def get_cart_recommendations(
    ctx: Context,
    limit: int = 6,
) -> dict[str, Any]:
    """Internal cart cross-sell lookup. Prefer shopping_assist for user-facing recommendations."""
    user_id = await _user(ctx)
    cart = await service_get_cart(user_id)

    existing_ids = {
        str(item.get("product_id"))
        for item in cart.get("items", [])
    }

    recommendations: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in cart.get("items", []):
        product_id = str(item.get("product_id"))
        for recommendation in await service_get_recommendations(product_id):
            rec_id = str(recommendation.get("id"))
            if rec_id in existing_ids or rec_id in seen:
                continue

            recommendations.append(
                _safe_json(recommendation)
            )
            seen.add(rec_id)

            if len(recommendations) >= max(1, min(limit, 12)):
                break

        if len(recommendations) >= max(1, min(limit, 12)):
            break

    return {
        "success": True,
        "cart": cart,
        "recommendations": recommendations,
    }


# ============================================================
# SHARED CART
# ============================================================

@mcp.tool()
async def create_cart(ctx: Context) -> dict[str, Any]:
    """Get the user's ONE shared Umon Mart cart, creating it if necessary."""
    user_id = await _user(ctx)
    return {
        "success": True,
        "cart": await service_get_cart(user_id),
    }


@mcp.tool()
async def get_cart(ctx: Context) -> dict[str, Any]:
    """Return the authenticated user's current shared cart."""
    user_id = await _user(ctx)
    return {
        "success": True,
        "cart": await service_get_cart(user_id),
    }


@mcp.tool(app=AppConfig(visibility=["model", "app"]))
async def add_to_cart(
    product_id: str,
    quantity: int = Field(
        default=1,
        ge=1,
        le=50,
    ),
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Add an offer to the shared user cart; no agent is selected here."""
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    user_id = await _user(ctx)

    try:
        cart = await service_add_to_cart(
            user_id,
            product_id,
            int(quantity),
        )
    except ValueError as exc:
        await audit(
            owner_clerk_user_id=user_id,
            action="MCP_CART_ITEM_ADDED",
            result="FAILED",
            metadata={
                "product_id": product_id,
                "quantity": int(quantity),
            },
            reason=str(exc),
        )
        return _error(
            "CART_UPDATE_FAILED",
            str(exc),
        )

    await audit(
        owner_clerk_user_id=user_id,
        action="MCP_CART_ITEM_ADDED",
        result="SUCCESS",
        metadata={
            "product_id": product_id,
            "quantity": int(quantity),
        },
    )

    return {
        "success": True,
        "cart": cart,
    }


@mcp.tool()
async def update_cart_item(
    product_id: str,
    quantity: int = Field(
        ge=1,
        le=50,
    ),
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Set a shared-cart item's quantity."""
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    user_id = await _user(ctx)

    try:
        cart = await service_update_cart_item(
            user_id,
            product_id,
            int(quantity),
        )
    except ValueError as exc:
        return _error(
            "CART_UPDATE_FAILED",
            str(exc),
        )

    return {
        "success": True,
        "cart": cart,
    }


@mcp.tool()
async def remove_from_cart(
    product_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Remove an item from the user's shared cart."""
    user_id = await _user(ctx)

    try:
        cart = await service_remove_cart_item(
            user_id,
            product_id,
        )
    except ValueError as exc:
        return _error(
            "CART_UPDATE_FAILED",
            str(exc),
        )

    return {
        "success": True,
        "cart": cart,
    }


@mcp.tool()
async def clear_cart(
    ctx: Context,
) -> dict[str, Any]:
    """Clear the user's entire shared cart."""
    user_id = await _user(ctx)

    return {
        "success": True,
        "cart": await service_clear_cart(
            user_id
        ),
    }


# ============================================================
# CHECKOUT PREFLIGHT
# ============================================================

async def _fresh_checkout_snapshot(
    user_id: str,
) -> dict[str, Any]:
    """Re-read all current product prices/stock and recompute the checkout total."""
    db = get_db()

    cart = await service_get_cart(user_id)

    if not cart.get("items"):
        return _error(
            "CART_EMPTY",
            "The shared cart is empty.",
        )

    fresh_items: list[dict[str, Any]] = []
    categories: list[str] = []
    subtotal_paise = 0

    for item in cart.get("items", []):
        product_id = str(item.get("product_id"))
        quantity = int(item.get("quantity", 0))

        if quantity < 1:
            return _error(
                "INVALID_QUANTITY",
                "Cart contains an invalid quantity.",
            )

        product = await db.products.find_one(
            {
                "_id": product_id,
                "merchant_id": settings.merchant_id,
                "active": True,
            }
        )

        if not product:
            return _error(
                "OFFER_UNAVAILABLE",
                f"{product_id} is no longer available.",
            )

        stock = int(product.get("stock", 0))
        if stock < quantity:
            return _error(
                "INSUFFICIENT_STOCK",
                f"Only {stock} units of {product['name']} are available.",
                product_id=product_id,
            )

        unit_price_paise = int(
            product.get("price_paise", 0)
        )
        line_total_paise = unit_price_paise * quantity
        subtotal_paise += line_total_paise

        category = str(
            product.get("category", "")
        ).strip().lower()
        categories.append(category)

        fresh_items.append(
            {
                "product_id": product_id,
                "name": product.get("name"),
                "brand": product.get("brand"),
                "category": category,
                "quantity": quantity,
                "unit_price_paise": unit_price_paise,
                "unit_price": _money(unit_price_paise),
                "line_total_paise": line_total_paise,
                "line_total": _money(line_total_paise),
                "stock_available": stock,
                "image": product.get("image"),
            }
        )

    delivery_fee_paise = (
        3900
        if 0 < subtotal_paise < 49900
        else 0
    )

    total_paise = (
        subtotal_paise + delivery_fee_paise
    )

    merchant = await db.merchants.find_one(
        {"_id": settings.merchant_id}
    )

    if not merchant:
        return _error(
            "MERCHANT_UNAVAILABLE",
            "Umon Mart is currently unavailable.",
        )

    return {
        "success": True,
        "cart": {
            "items": fresh_items,
            "item_count": sum(
                int(item["quantity"])
                for item in fresh_items
            ),
            "subtotal_paise": subtotal_paise,
            "subtotal": _money(subtotal_paise),
            "delivery_fee_paise": delivery_fee_paise,
            "delivery_fee": _money(delivery_fee_paise),
            "total_paise": total_paise,
            "total": _money(total_paise),
            "currency": "INR",
        },
        "categories": sorted(set(categories)),
        "merchant": _safe_json(merchant),
    }


@mcp.tool()
async def get_checkout_options(
    ctx: Context,
) -> dict[str, Any]:
    """Show the user's current cart, available agents and supported checkout methods."""
    user_id = await _user(ctx)

    snapshot = await _fresh_checkout_snapshot(
        user_id
    )
    if not snapshot.get("success"):
        return snapshot

    db = get_db()
    agents = await (
        db.agents.find(
            {
                "owner_clerk_user_id": user_id,
                "status": {
                    "$in": [
                        "ACTIVE",
                        "DISABLED",
                    ]
                },
            }
        )
        .sort("created_at", -1)
        .limit(50)
        .to_list(length=50)
    )

    return {
        "success": True,
        "cart": snapshot["cart"],
        "payment_methods": [
            {
                "id": "AGENT_BALANCE",
                "label": "Umon purchasing agent balance",
                "description": (
                    "Use an already-funded Umon agent within its configured guardrails."
                ),
                "mcp_supported": True,
            },
            {
                "id": "RAZORPAY",
                "label": "Direct Razorpay",
                "description": (
                    "Normal Razorpay checkout is available through the Umon store UI."
                ),
                "mcp_supported": False,
            },
        ],
        "agents": [
            _safe_agent(agent)
            for agent in agents
        ],
    }


@mcp.tool()
async def validate_checkout(
    agent_id: str,
    confirmed: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Read-only purchase preflight.

    This never reserves balance, changes stock or creates an order.
    """
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    user_id = await _user(ctx)

    agent = await get_owned_agent(
        user_id,
        agent_id,
    )

    if not agent:
        return _error(
            "AGENT_NOT_FOUND",
            "Agent not found or not owned by this user.",
        )

    snapshot = await _fresh_checkout_snapshot(
        user_id
    )

    if not snapshot.get("success"):
        return snapshot

    policy = await evaluate_purchase(
        agent=agent,
        amount_paise=int(
            snapshot["cart"]["total_paise"]
        ),
        categories=snapshot["categories"],
        merchant=snapshot["merchant"],
        confirmed=confirmed,
    )

    await audit(
        owner_clerk_user_id=user_id,
        action="MCP_CHECKOUT_VALIDATED",
        result=str(policy.get("decision", "BLOCK")),
        agent_id=agent_id,
        amount_paise=int(
            snapshot["cart"]["total_paise"]
        ),
        reason=policy.get("reason"),
        metadata={
            "confirmed": bool(confirmed),
            "read_only": True,
        },
    )

    return {
        "success": True,
        "decision": policy.get("decision", "BLOCK"),
        "agent": _safe_agent(agent),
        "cart": snapshot["cart"],
        "merchant": {
            "id": settings.merchant_id,
            "name": settings.merchant_name,
        },
        "policy": _safe_json(policy),
        "money_movement": False,
        "next_step": (
            "Call checkout only after clear user authorization."
            if policy.get("decision") == "ALLOW"
            else "Do not call checkout unless a new preflight returns ALLOW."
        ),
    }


# ============================================================
# MONEY ACTION
# ============================================================

@mcp.tool()
async def checkout(
    agent_id: str,
    confirmed: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Execute the current shared cart using the selected agent balance.

    The tool intentionally accepts no amount. Umon calculates the final total
    from the authoritative current catalog, then the existing checkout service
    performs the real authorization and money/ledger/order workflow.
    """
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    user_id = await _user(ctx)

    try:
        result = await checkout_with_agent_balance(
            user_id,
            agent_id,
            bool(confirmed),
        )
    except Exception as exc:
        await audit(
            owner_clerk_user_id=user_id,
            action="MCP_CHECKOUT_FAILED",
            result="FAILED",
            agent_id=agent_id,
            reason=str(exc),
            metadata={
                "confirmed": bool(confirmed),
            },
        )
        return {
            "success": False,
            "status": "FAILED",
            "agent_id": agent_id,
            "error": {
                "code": "CHECKOUT_FAILED",
                "message": str(exc),
            },
            "money_movement": False,
            "recovery": (
                "No successful checkout result was returned. "
                "Do not claim that the order was paid. "
                "The user can inspect the audit trail or retry after resolving the failure."
            ),
        }

    safe = _safe_json(result)

    return {
        "success": bool(result.get("success", False)),
        **safe,
        "agent_id": agent_id,
        "money_movement": bool(result.get("success", False)),
    }


# ============================================================
# ORDERS + AUDIT
# ============================================================

@mcp.tool()
async def get_order_status(
    order_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Return the current payment and order state for an owned order."""
    user_id = await _user(ctx)
    db = get_db()

    order = await db.orders.find_one(
        {
            "_id": order_id,
            "owner_clerk_user_id": user_id,
        }
    )

    if not order:
        return _error(
            "ORDER_NOT_FOUND",
            "Order not found.",
        )

    return {
        "success": True,
        "order": _safe_json(order),
    }


@mcp.tool()
async def get_order(
    order_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Get an authenticated user's order."""
    return await get_order_status(
        order_id,
        ctx,
    )


@mcp.tool()
async def list_my_orders(
    ctx: Context,
    limit: int = 20,
) -> dict[str, Any]:
    """List the authenticated user's recent orders."""
    user_id = await _user(ctx)
    db = get_db()

    docs = await (
        db.orders.find(
            {
                "owner_clerk_user_id": user_id,
            }
        )
        .sort("created_at", -1)
        .limit(max(1, min(int(limit), 50)))
        .to_list(length=50)
    )

    return {
        "success": True,
        "count": len(docs),
        "orders": [
            _safe_json(order)
            for order in docs
        ],
    }


@mcp.tool()
async def get_my_activity(
    ctx: Context,
    agent_id: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Show the authenticated user's recent audit trail."""
    user_id = await _user(ctx)
    db = get_db()

    query: dict[str, Any] = {
        "owner_clerk_user_id": user_id,
    }

    if agent_id:
        agent = await get_owned_agent(
            user_id,
            agent_id,
        )
        if not agent:
            return _error(
                "AGENT_NOT_FOUND",
                "Agent not found or not owned by this user.",
            )
        query["agent_id"] = agent_id

    events = await (
        db.audit_events.find(query)
        .sort("created_at", -1)
        .limit(max(1, min(int(limit), 100)))
        .to_list(length=100)
    )

    return {
        "success": True,
        "count": len(events),
        "events": [
            _safe_json(event)
            for event in events
        ],
    }




# ============================================================
# LANGGRAPH + CHATGPT APP UI
# ============================================================

from pathlib import Path

STORE_UI_URI = "ui://umon/store.html"
CART_UI_URI = "ui://umon/cart.html"
CHECKOUT_UI_URI = "ui://umon/checkout.html"
ORDER_UI_URI = "ui://umon/order.html"
UI_DIR = Path(__file__).resolve().parent / "ui"

# Known domains used by the current seeded catalogue plus Google Fonts.
# Keep this allowlist small. New merchant image hosts should be added here
# deliberately when their URLs are introduced into catalogue data.
UI_RESOURCE_DOMAINS = [
    "https://unpkg.com",
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
    "https://encrypted-tbn0.gstatic.com",
    "https://encrypted-tbn1.gstatic.com",
    "https://banerjeesupermarket.com",
    "https://www.bbassets.com",
]


def _load_ui(name: str) -> str:
    path = UI_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Umon UI resource is missing: {path.name}") from exc


def _ui_resource_app() -> AppConfig:
    # On a resource, resource_uri/visibility are not used. FastMCP uses the
    # resource itself as the UI and only needs its CSP/domain here.
    return AppConfig(
        domain=UMON_WIDGET_DOMAIN,
        csp=ResourceCSP(
            resource_domains=UI_RESOURCE_DOMAINS,
        ),
    )


def _ui_tool_app(resource_uri: str) -> AppConfig:
    # model + app visibility ensures the host can render the app while the
    # same tool remains callable by the model.
    return AppConfig(
        resource_uri=resource_uri,
        visibility=["model", "app"],
        domain=UMON_WIDGET_DOMAIN,
        prefers_border=True,
    )


@mcp.resource(STORE_UI_URI, app=_ui_resource_app())
def store_ui() -> str:
    """Interactive Umon product recommendation UI."""
    return _load_ui("store.html")


@mcp.resource(CART_UI_URI, app=_ui_resource_app())
def cart_ui() -> str:
    """Interactive Umon shared-cart UI."""
    return _load_ui("cart.html")


@mcp.resource(CHECKOUT_UI_URI, app=_ui_resource_app())
def checkout_ui() -> str:
    """Read-only Umon checkout review UI."""
    return _load_ui("checkout.html")


@mcp.resource(ORDER_UI_URI, app=_ui_resource_app())
def order_ui() -> str:
    """Umon order/payment state UI."""
    return _load_ui("order.html")


@mcp.tool(app=_ui_tool_app(STORE_UI_URI))
async def shopping_assist(
    intent: str,
    budget: float | None = None,
    category: str | None = None,
    selected_agent_id: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Use Umon's shopping graph to understand a goal, inspect the shared cart,
    discover live products, surface merchant-defined cross-sells and return a
    small verified recommendation set. Never changes the cart or moves money.
    """
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    user_id = await _user(ctx)

    if budget is not None and budget < 0:
        return _error("INVALID_BUDGET", "Budget cannot be negative.")

    result = await run_shopping_assistant(
        user_id=user_id,
        intent=intent,
        budget_paise=round(budget * 100) if budget is not None else None,
        category=category,
        selected_agent_id=selected_agent_id,
    )

    await audit(
        owner_clerk_user_id=user_id,
        action="MCP_SHOPPING_ASSISTED",
        result="SUCCESS",
        agent_id=selected_agent_id,
        metadata={
            "intent": intent,
            "budget_paise": round(budget * 100) if budget is not None else None,
            "category": category,
            "suggestion_total_paise": result.get("suggestion_total_paise", 0),
            "graph": graph_description(),
        },
    )

    return {
        "success": True,
        "mode": "RECOMMENDATION_ONLY",
        "title": "Smart recommendations",
        "intent": intent,
        "budget_paise": round(budget * 100) if budget is not None else None,
        "suggestions": result.get("suggestion_items", []),
        "recommendations": result.get("suggestion_items", []),
        "cross_sell": result.get("recommendations", []),
        "suggestion_total_paise": result.get("suggestion_total_paise", 0),
        "suggestion_total": _money(result.get("suggestion_total_paise", 0)),
        "cart": result.get("cart", {}),
        "agent": _safe_agent(result["agent"]) if result.get("agent") else None,
        "agent_spending": _safe_json(result.get("agent_spending")),
        "warnings": result.get("warnings", []),
        "basket_gaps": result.get("warnings", []),
        "explanation": result.get(
            "explanation",
            "These recommendations use current Umon catalogue data. Nothing was added or purchased automatically.",
        ),
        "graph": graph_description(),
        "next_action": result.get("next_action", "present_recommendations"),
        "money_movement": False,
    }


@mcp.tool(app=_ui_tool_app(CART_UI_URI))
async def show_cart(ctx: Context) -> dict[str, Any]:
    """Render the authenticated user's one shared Umon cart."""
    user_id = await _user(ctx)
    return {
        "success": True,
        "cart": await service_get_cart(user_id),
        "money_movement": False,
    }


@mcp.tool(app=_ui_tool_app(CHECKOUT_UI_URI))
async def review_checkout(
    agent_id: str,
    confirmed: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Render the authoritative, read-only checkout decision."""
    if ctx is None:
        raise RuntimeError("MCP context is required.")

    result = await validate_checkout(
        agent_id=agent_id,
        confirmed=confirmed,
        ctx=ctx,
    )

    return {
        "success": True,
        "checkout": result,
        "money_movement": False,
    }


@mcp.tool(app=_ui_tool_app(ORDER_UI_URI))
async def show_order(
    order_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Render the authenticated user's order/payment state."""
    return await get_order_status(
        order_id=order_id,
        ctx=ctx,
    )

# ============================================================
# OAUTH MODELS
# ============================================================

class OAuthRegisterBody(BaseModel):
    client_name: str = "ChatGPT"
    redirect_uris: list[str] = Field(min_length=1)
    grant_types: list[str] = Field(
        default_factory=lambda: [
            "authorization_code",
            "refresh_token",
        ]
    )
    response_types: list[str] = Field(
        default_factory=lambda: ["code"]
    )
    token_endpoint_auth_method: str = "none"


class OAuthCompleteBody(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str = MCP_SCOPE
    state: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    resource: str = MCP_ENDPOINT
    clerk_token: str


class OAuthTokenBody(BaseModel):
    grant_type: str
    client_id: str
    client_secret: str | None = None
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None
    resource: str | None = None


# ============================================================
# OAUTH HELPERS
# ============================================================

def _valid_redirect_uri(uri: str) -> bool:
    try:
        parsed = urlparse(uri)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").lower()

    if host in {"localhost", "127.0.0.1"}:
        return True

    if host in {"chatgpt.com", "chat.openai.com"}:
        return True

    # Umon frontend is valid only as the consent bridge.
    return uri.startswith(FRONTEND_URL)


def _chatgpt_redirect_ok(uri: str) -> bool:
    try:
        parsed = urlparse(uri)
    except Exception:
        return False

    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower()
        in {"chatgpt.com", "chat.openai.com"}
        and bool(parsed.path)
    )


def _resource_is_valid(resource: str | None) -> bool:
    if not resource:
        return False
    return resource.rstrip("/") == MCP_ENDPOINT.rstrip("/")


def _redirect_with_params(
    redirect_uri: str,
    **params: str,
) -> RedirectResponse:
    encoded = urlencode(
        {
            key: value
            for key, value in params.items()
            if value is not None
        }
    )

    separator = "&" if "?" in redirect_uri else "?"

    return RedirectResponse(
        f"{redirect_uri}{separator}{encoded}",
        status_code=302,
    )


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(
        verifier.encode("utf-8")
    ).digest()

    return base64.urlsafe_b64encode(
        digest
    ).rstrip(b"=").decode("ascii")

# ============================================================
# OAUTH / CUSTOM HTTP ROUTES
# ============================================================

async def _read_request_payload(request: Request) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        data = await request.json()
        return data if isinstance(data, dict) else {}

    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        return {str(k): str(v) for k, v in form.items()}

    if "multipart/form-data" in content_type:
        form = await request.form()
        return {str(k): str(v) for k, v in form.items()}

    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _registered_client(client_id: str) -> dict[str, Any] | None:
    return await get_db().mcp_oauth_clients.find_one(
        {"client_id": client_id}
    )


@mcp.custom_route("/assets/image-proxy", methods=["GET"])
async def image_proxy(request: Request) -> Response:
    """Proxy allowlisted catalogue images for stable MCP App rendering."""
    raw_url = request.query_params.get("url", "").strip()
    if not raw_url:
        return Response("Missing image URL.", status_code=400)

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return Response("Invalid image URL.", status_code=400)

    host = parsed.hostname.lower().rstrip(".")
    if host not in UI_IMAGE_HOSTS:
        return Response("Image host is not allowlisted.", status_code=403)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=8.0,
            headers={"User-Agent": "Umon-MCP-Image-Proxy/1.0"},
        ) as client:
            response = await client.get(raw_url)

        # Re-check every redirect destination to prevent an allowlist bypass.
        destinations = [*response.history, response]
        for hop in destinations:
            hop_host = (hop.url.host or "").lower().rstrip(".")
            if hop_host not in UI_IMAGE_HOSTS:
                return Response("Image redirect is not allowlisted.", status_code=403)

        if response.status_code >= 400:
            return Response("Image unavailable.", status_code=404)

        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            return Response("Remote resource is not an image.", status_code=415)

        body = response.content
        if len(body) > 4 * 1024 * 1024:
            return Response("Image is too large.", status_code=413)

        return Response(
            body,
            status_code=200,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except httpx.HTTPError:
        return Response("Image fetch failed.", status_code=502)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    try:
        await get_db().command("ping")
    except Exception as exc:
        return JSONResponse(
            {
                "status": "degraded",
                "service": MCP_APP_NAME,
                "mongodb": False,
                "error": str(exc),
            },
            status_code=503,
        )

    return JSONResponse(
        {
            "status": "ok",
            "service": MCP_APP_NAME,
            "mongodb": True,
            "mcp_endpoint": MCP_ENDPOINT,
            "oauth_enabled": True,
        }
    )


@mcp.custom_route(
    "/.well-known/oauth-protected-resource",
    methods=["GET"],
)
async def oauth_protected_resource(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": MCP_ENDPOINT,
            "authorization_servers": [MCP_PUBLIC_URL],
            "scopes_supported": [MCP_SCOPE],
            "bearer_methods_supported": ["header"],
        }
    )


@mcp.custom_route(
    "/.well-known/oauth-protected-resource/mcp",
    methods=["GET"],
)
async def oauth_protected_resource_mcp(
    request: Request,
) -> JSONResponse:
    return await oauth_protected_resource(request)


@mcp.custom_route(
    "/.well-known/oauth-authorization-server",
    methods=["GET"],
)
async def oauth_authorization_server(
    request: Request,
) -> JSONResponse:
    return JSONResponse(
        {
            "issuer": MCP_PUBLIC_URL,
            "authorization_endpoint": (
                f"{MCP_PUBLIC_URL}/oauth/authorize"
            ),
            "token_endpoint": (
                f"{MCP_PUBLIC_URL}/oauth/token"
            ),
            "registration_endpoint": (
                f"{MCP_PUBLIC_URL}/oauth/register"
            ),
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
            ],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": [MCP_SCOPE],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )


@mcp.custom_route("/oauth/register", methods=["POST"])
async def oauth_register(
    request: Request,
) -> JSONResponse:
    await _cleanup_oauth()

    data = await _read_request_payload(request)

    client_name = str(
        data.get("client_name") or "ChatGPT"
    )

    redirect_uris = data.get("redirect_uris") or []

    if isinstance(redirect_uris, str):
        redirect_uris = [redirect_uris]

    grant_types = data.get(
        "grant_types"
    ) or ["authorization_code", "refresh_token"]

    if isinstance(grant_types, str):
        grant_types = [grant_types]

    response_types = data.get(
        "response_types"
    ) or ["code"]

    if isinstance(response_types, str):
        response_types = [response_types]

    token_endpoint_auth_method = str(
        data.get("token_endpoint_auth_method")
        or "none"
    )

    if not redirect_uris:
        raise HTTPException(
            status_code=400,
            detail="At least one redirect URI is required.",
        )

    for redirect_uri in redirect_uris:
        if not _valid_redirect_uri(str(redirect_uri)):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Redirect URI is not allowed: "
                    f"{redirect_uri}"
                ),
            )

    db = get_db()
    client_id = (
        "umon_client_"
        + secrets.token_urlsafe(24)
    )

    await db.mcp_oauth_clients.insert_one(
        {
            "_id": client_id,
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": [
                str(uri)
                for uri in redirect_uris
            ],
            "grant_types": grant_types,
            "response_types": response_types,
            "token_endpoint_auth_method": "none",
            "created_at": utc_now(),
        }
    )

    return JSONResponse(
        {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": [
                str(uri)
                for uri in redirect_uris
            ],
            "grant_types": grant_types,
            "response_types": response_types,
            "token_endpoint_auth_method": "none",
        },
        status_code=201,
    )


@mcp.custom_route("/oauth/authorize", methods=["GET"])
async def oauth_authorize(
    request: Request,
) -> RedirectResponse:
    params = request.query_params

    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    response_type = params.get(
        "response_type",
        "code",
    )
    scope = params.get(
        "scope",
        MCP_SCOPE,
    )
    state = params.get("state") or ""
    code_challenge = params.get(
        "code_challenge"
    ) or ""
    code_challenge_method = params.get(
        "code_challenge_method"
    ) or ""
    resource = params.get(
        "resource"
    ) or MCP_ENDPOINT

    if response_type != "code":
        raise HTTPException(
            status_code=400,
            detail="Only response_type=code is supported.",
        )

    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth client_id.",
        )

    if not redirect_uri or not _valid_redirect_uri(
        redirect_uri
    ):
        raise HTTPException(
            status_code=400,
            detail="Redirect URI is not allowed.",
        )

    if not _resource_is_valid(resource):
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth resource.",
        )

    scopes = set(scope.split())
    if MCP_SCOPE not in scopes:
        raise HTTPException(
            status_code=400,
            detail="Unsupported OAuth scope.",
        )

    if code_challenge_method not in {
        "",
        "S256",
    }:
        raise HTTPException(
            status_code=400,
            detail="Only PKCE S256 is supported.",
        )

    client = await _registered_client(client_id)

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Unknown OAuth client.",
        )

    if redirect_uri not in client.get(
        "redirect_uris",
        [],
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Redirect URI is not registered "
                "for this client."
            ),
        )

    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": (
                code_challenge_method or "S256"
            ),
            "resource": resource,
        }
    )

    return RedirectResponse(
        f"{FRONTEND_URL}/mcp/connect?{query}",
        status_code=302,
    )


@mcp.custom_route("/oauth/complete", methods=["POST"])
async def oauth_complete(
    request: Request,
) -> RedirectResponse:
    await _cleanup_oauth()

    data = await _read_request_payload(request)

    try:
        body = OAuthCompleteBody.model_validate(data)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid OAuth completion request: {exc}",
        ) from exc

    if not _chatgpt_redirect_ok(body.redirect_uri):
        raise HTTPException(
            status_code=400,
            detail=(
                "OAuth redirect URI must be "
                "a ChatGPT callback."
            ),
        )

    if body.resource != MCP_ENDPOINT:
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth resource.",
        )

    client = await _registered_client(body.client_id)

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Unknown OAuth client.",
        )

    if body.redirect_uri not in client.get(
        "redirect_uris",
        [],
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Redirect URI is not registered "
                "for this client."
            ),
        )

    if body.scope not in {
        MCP_SCOPE,
        f"{MCP_SCOPE} offline_access",
    }:
        scopes = set(
            body.scope.split()
        )
        if MCP_SCOPE not in scopes:
            raise HTTPException(
                status_code=400,
                detail="Unsupported OAuth scope.",
            )

    if body.code_challenge_method not in {
        None,
        "",
        "S256",
    }:
        raise HTTPException(
            status_code=400,
            detail="Only PKCE S256 is supported.",
        )

    if not body.code_challenge:
        raise HTTPException(
            status_code=400,
            detail="PKCE code_challenge is required.",
        )

    claims = await _verify_clerk_token(
        body.clerk_token
    )

    clerk_user_id = str(
        claims["sub"]
    )

    await _ensure_active_user(
        clerk_user_id,
        claims,
    )

    raw_code = (
        "umon_code_"
        + secrets.token_urlsafe(32)
    )

    await get_db().mcp_oauth_codes.insert_one(
        {
            "_id": _hash(raw_code),
            "code_hash": _hash(raw_code),
            "client_id": body.client_id,
            "redirect_uri": body.redirect_uri,
            "clerk_user_id": clerk_user_id,
            "scope": body.scope,
            "resource": body.resource,
            "code_challenge": body.code_challenge,
            "code_challenge_method": (
                body.code_challenge_method
                or "S256"
            ),
            "expires_at": utc_now()
            + timedelta(
                seconds=OAUTH_CODE_TTL_SECONDS
            ),
            "created_at": utc_now(),
        }
    )

    await audit(
        owner_clerk_user_id=clerk_user_id,
        action="MCP_OAUTH_CONSENT_GRANTED",
        result="SUCCESS",
        metadata={
            "client_id": body.client_id,
            "scope": body.scope,
            "resource": body.resource,
        },
    )

    return _redirect_with_params(
        body.redirect_uri,
        code=raw_code,
        state=body.state or "",
    )


@mcp.custom_route("/oauth/token", methods=["POST"])
async def oauth_token(
    request: Request,
) -> JSONResponse:
    await _cleanup_oauth()

    data = await _read_request_payload(request)

    try:
        body = OAuthTokenBody.model_validate(data)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid OAuth token request: {exc}",
        ) from exc

    if not body.client_id:
        raise HTTPException(
            status_code=400,
            detail="client_id is required.",
        )

    if body.resource and body.resource != MCP_ENDPOINT:
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth resource.",
        )

    client = await _registered_client(
        body.client_id
    )

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Unknown OAuth client.",
        )

    db = get_db()

    if body.grant_type == "authorization_code":
        if not body.code:
            raise HTTPException(
                status_code=400,
                detail="Authorization code is required.",
            )

        if not body.code_verifier:
            raise HTTPException(
                status_code=400,
                detail="code_verifier is required.",
            )

        code_record = (
            await db.mcp_oauth_codes.find_one_and_delete(
                {
                    "code_hash": _hash(body.code),
                    "client_id": body.client_id,
                }
            )
        )

        if not code_record:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid or expired "
                    "authorization code."
                ),
            )

        expires_at = code_record.get(
            "expires_at"
        )

        if not _token_datetime_is_valid(expires_at):
            raise HTTPException(
                status_code=400,
                detail="Authorization code expired.",
            )

        if (
            body.redirect_uri
            and body.redirect_uri
            != code_record.get("redirect_uri")
        ):
            raise HTTPException(
                status_code=400,
                detail="OAuth redirect URI mismatch.",
            )

        stored_resource = code_record.get(
            "resource",
            MCP_ENDPOINT,
        )

        if (
            body.resource
            and body.resource
            != stored_resource
        ):
            raise HTTPException(
                status_code=400,
                detail="OAuth resource mismatch.",
            )

        challenge = code_record.get(
            "code_challenge"
        )

        if challenge and not secrets.compare_digest(
            _pkce_s256(body.code_verifier),
            str(challenge),
        ):
            raise HTTPException(
                status_code=400,
                detail="PKCE verification failed.",
            )

        raw_access_token = (
            "umon_mcp_"
            + secrets.token_urlsafe(40)
        )

        raw_refresh_token = (
            "umon_refresh_"
            + secrets.token_urlsafe(40)
        )

        scope = code_record.get(
            "scope",
            MCP_SCOPE,
        )

        await db.mcp_oauth_tokens.insert_one(
            {
                "_id": _hash(raw_access_token),
                "token_hash": _hash(
                    raw_access_token
                ),
                "client_id": code_record[
                    "client_id"
                ],
                "clerk_user_id": code_record[
                    "clerk_user_id"
                ],
                "scope": scope,
                "resource": stored_resource,
                "expires_at": utc_now()
                + timedelta(
                    seconds=OAUTH_ACCESS_TTL_SECONDS
                ),
                "created_at": utc_now(),
            }
        )

        await db.mcp_oauth_refresh_tokens.insert_one(
            {
                "_id": _hash(raw_refresh_token),
                "token_hash": _hash(
                    raw_refresh_token
                ),
                "client_id": code_record[
                    "client_id"
                ],
                "clerk_user_id": code_record[
                    "clerk_user_id"
                ],
                "scope": scope,
                "resource": stored_resource,
                "expires_at": utc_now()
                + timedelta(
                    seconds=OAUTH_REFRESH_TTL_SECONDS
                ),
                "created_at": utc_now(),
            }
        )

        await audit(
            owner_clerk_user_id=code_record[
                "clerk_user_id"
            ],
            action="MCP_ACCESS_TOKEN_ISSUED",
            result="SUCCESS",
            metadata={
                "client_id": body.client_id,
                "scope": scope,
                "resource": stored_resource,
            },
        )

        response = JSONResponse(
            {
                "access_token": raw_access_token,
                "token_type": "Bearer",
                "expires_in": OAUTH_ACCESS_TTL_SECONDS,
                "refresh_token": raw_refresh_token,
                "scope": scope,
            }
        )

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

        return response

    if body.grant_type == "refresh_token":
        if not body.refresh_token:
            raise HTTPException(
                status_code=400,
                detail="refresh_token is required.",
            )

        refresh = await db.mcp_oauth_refresh_tokens.find_one(
            {
                "token_hash": _hash(
                    body.refresh_token
                ),
                "client_id": body.client_id,
            }
        )

        if not refresh:
            raise HTTPException(
                status_code=400,
                detail="Invalid refresh token.",
            )

        expires_at = refresh.get(
            "expires_at"
        )

        if not _token_datetime_is_valid(expires_at):
            raise HTTPException(
                status_code=400,
                detail="Refresh token expired.",
            )

        stored_resource = refresh.get(
            "resource",
            MCP_ENDPOINT,
        )

        if body.resource and body.resource != stored_resource:
            raise HTTPException(
                status_code=400,
                detail="OAuth resource mismatch.",
            )

        raw_access_token = (
            "umon_mcp_"
            + secrets.token_urlsafe(40)
        )

        scope = refresh.get(
            "scope",
            MCP_SCOPE,
        )

        await db.mcp_oauth_tokens.insert_one(
            {
                "_id": _hash(raw_access_token),
                "token_hash": _hash(
                    raw_access_token
                ),
                "client_id": refresh[
                    "client_id"
                ],
                "clerk_user_id": refresh[
                    "clerk_user_id"
                ],
                "scope": scope,
                "resource": stored_resource,
                "expires_at": utc_now()
                + timedelta(
                    seconds=OAUTH_ACCESS_TTL_SECONDS
                ),
                "created_at": utc_now(),
            }
        )

        response = JSONResponse(
            {
                "access_token": raw_access_token,
                "token_type": "Bearer",
                "expires_in": OAUTH_ACCESS_TTL_SECONDS,
                "scope": scope,
            }
        )

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

        return response

    raise HTTPException(
        status_code=400,
        detail=(
            "Unsupported grant_type: "
            f"{body.grant_type}"
        ),
    )


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "name": MCP_APP_NAME,
            "version": MCP_APP_VERSION,
            "status": "online",
            "mcp": MCP_ENDPOINT,
            "oauth": f"{MCP_PUBLIC_URL}/oauth/authorize",
        }
    )


# ============================================================
# START SERVER
# ============================================================

def main() -> None:
    host = os.getenv(
        "HOST",
        "0.0.0.0",
    )
    port = int(
        os.getenv(
            "PORT",
            "8002",
        )
    )

    print(
        f"Starting {MCP_APP_NAME} "
        f"on http://{host}:{port}/mcp"
    )

    mcp.run(
        transport="http",
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
