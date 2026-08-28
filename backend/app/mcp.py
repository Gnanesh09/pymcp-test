# from __future__ import annotations

# """
# Umon Mart — Remote MCP / ChatGPT integration.

# This module is deliberately a thin protocol adapter over the existing Umon
# commerce services. It does not create a second cart, wallet, policy engine,
# or payment system.

# Flow:
#     ChatGPT / MCP client
#         -> OAuth 2.1
#         -> /mcp (Streamable HTTP)
#         -> authenticated Clerk user
#         -> existing Umon services
#         -> catalog / cart / policy / checkout / orders / audit

# Money boundary:
#     The model never supplies the final charge amount. Umon recomputes the
#     current cart and the existing checkout service performs the authoritative
#     policy, balance, inventory, order, ledger and audit operations.

# Run as a dedicated MCP process during development:
#     uvicorn app.mcp:app --reload --port 8002

# Your normal Umon API can continue to run on port 8001.
# """

# from contextlib import asynccontextmanager
# from datetime import datetime, timedelta, timezone
# import base64
# import hashlib
# import os
# import secrets
# from typing import Any, AsyncIterator
# from urllib.parse import urlencode, urlparse

# import jwt
# from fastapi import FastAPI, HTTPException, Request
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
# from jwt import PyJWKClient
# from pydantic import BaseModel, Field

# from mcp.server.apps import Apps
# from mcp.server.mcpserver import Context, MCPServer
# from mcp.server.transport_security import TransportSecuritySettings

# from .config import settings
# from .db import lifespan as db_lifespan
# from .db import get_db, utc_now
# from .models import public_agent, public_product
# from .policies import evaluate_purchase
# from .security import get_current_claims
# from .services import (
#     add_to_cart as service_add_to_cart,
#     agent_stats,
#     audit,
#     checkout_with_agent_balance,
#     clear_cart as service_clear_cart,
#     get_cart as service_get_cart,
#     get_owned_agent,
#     get_recommendations as service_get_recommendations,
#     remove_cart_item as service_remove_cart_item,
#     search_products as service_search_products,
#     update_cart_item as service_update_cart_item,
# )


# # ============================================================
# # CONFIG
# # ============================================================

# MCP_APP_NAME = "Umon Mart"
# MCP_APP_VERSION = "1.0.0"
# MCP_SCOPE = "umon"

# FRONTEND_URL = os.getenv(
#     "UMON_FRONTEND_URL",
#     "http://localhost:3000",
# ).strip().rstrip("/")

# MCP_PUBLIC_URL = os.getenv(
#     "MCP_PUBLIC_URL",
#     "http://localhost:8002",
# ).strip().rstrip("/")

# MCP_ENDPOINT = f"{MCP_PUBLIC_URL}/mcp"

# OAUTH_CODE_TTL_SECONDS = 120
# OAUTH_ACCESS_TTL_SECONDS = 3600
# OAUTH_REFRESH_TTL_SECONDS = 60 * 60 * 24 * 30

# PRODUCT_UI_URI = "ui://umon/product-catalogue.html"


# # ============================================================
# # MONGO OAUTH STATE
# # ============================================================


# def _hash(value: str) -> str:
#     return hashlib.sha256(value.encode("utf-8")).hexdigest()


# async def _cleanup_oauth() -> None:
#     db = get_db()
#     now = utc_now()

#     await db.mcp_oauth_codes.delete_many(
#         {"expires_at": {"$lte": now}}
#     )

#     await db.mcp_oauth_tokens.delete_many(
#         {"expires_at": {"$lte": now}}
#     )

#     await db.mcp_oauth_refresh_tokens.delete_many(
#         {"expires_at": {"$lte": now}}
#     )


# # ============================================================
# # CLERK AUTH FOR OAUTH CONSENT / MCP FALLBACK
# # ============================================================

# _jwks_client = PyJWKClient(settings.clerk_jwks_url)


# async def _verify_clerk_token(token: str) -> dict[str, Any]:
#     if not token:
#         raise HTTPException(
#             status_code=401,
#             detail="Clerk session token is required.",
#         )

#     try:
#         signing_key = _jwks_client.get_signing_key_from_jwt(token)

#         decode_options: dict[str, Any] = {
#             "algorithms": ["RS256"],
#             "issuer": settings.clerk_issuer,
#             "leeway": 10,
#             "options": {"verify_aud": False},
#         }

#         claims = jwt.decode(
#             token,
#             signing_key.key,
#             **decode_options,
#         )

#         if settings.clerk_authorized_party:
#             azp = claims.get("azp")
#             if azp and azp != settings.clerk_authorized_party:
#                 raise HTTPException(
#                     status_code=401,
#                     detail="Unauthorized session issuer.",
#                 )

#         if not claims.get("sub"):
#             raise HTTPException(
#                 status_code=401,
#                 detail="Clerk token missing subject.",
#             )

#         return claims

#     except HTTPException:
#         raise
#     except Exception as exc:
#         raise HTTPException(
#             status_code=401,
#             detail=f"Invalid Clerk session token: {exc}",
#         ) from exc


# async def _ensure_active_user(
#     clerk_user_id: str,
#     claims: dict[str, Any] | None = None,
# ) -> None:
#     db = get_db()

#     now = utc_now()
#     user = await db.users.find_one_and_update(
#         {"clerk_user_id": clerk_user_id},
#         {
#             "$set": {
#                 "email": claims.get("email") if claims else None,
#                 "updated_at": now,
#             },
#             "$setOnInsert": {
#                 "clerk_user_id": clerk_user_id,
#                 "status": "ACTIVE",
#                 "created_at": now,
#             },
#         },
#         upsert=True,
#         return_document=True,
#     )

#     if not user or user.get("status") != "ACTIVE":
#         raise HTTPException(
#             status_code=403,
#             detail="Umon user account is not active.",
#         )


# # ============================================================
# # MCP AUTHORIZATION
# # ============================================================


# async def _resolve_mcp_user(ctx: Context) -> str:
#     headers = ctx.headers or {}
#     authorization = headers.get("authorization", "")

#     if not authorization.lower().startswith("bearer "):
#         raise PermissionError(
#             "Umon authentication is required."
#         )

#     bearer = authorization[7:].strip()
#     if not bearer:
#         raise PermissionError("Empty bearer token.")

#     await _cleanup_oauth()
#     db = get_db()

#     oauth_token = await db.mcp_oauth_tokens.find_one(
#         {"token_hash": _hash(bearer)}
#     )

#     if oauth_token:
#         expires_at = oauth_token.get("expires_at")
#         if not isinstance(expires_at, datetime) or expires_at <= utc_now():
#             raise PermissionError("Umon MCP access token expired.")

#         user_id = str(oauth_token["clerk_user_id"])
#         await _ensure_active_user(user_id)
#         return user_id

#     # Local development / MCP Inspector convenience: allow a valid Clerk JWT
#     # directly. ChatGPT will use the opaque OAuth token above.
#     try:
#         claims = await _verify_clerk_token(bearer)
#         user_id = str(claims["sub"])
#         await _ensure_active_user(user_id, claims)
#         return user_id
#     except HTTPException as exc:
#         raise PermissionError(str(exc.detail)) from exc


# async def _user(ctx: Context) -> str:
#     try:
#         return await _resolve_mcp_user(ctx)
#     except PermissionError as exc:
#         raise RuntimeError(str(exc)) from exc


# # ============================================================
# # SAFE PUBLIC REPRESENTATIONS
# # ============================================================


# def _money(paise: int) -> float:
#     return round(int(paise) / 100, 2)


# def _safe_json(value: Any) -> Any:
#     if isinstance(value, dict):
#         return {
#             str(key): _safe_json(item)
#             for key, item in value.items()
#             if key != "_id"
#         }
#     if isinstance(value, list):
#         return [_safe_json(item) for item in value]
#     if isinstance(value, datetime):
#         return value.isoformat()
#     return value


# def _safe_product(product: dict[str, Any]) -> dict[str, Any]:
#     public = public_product(product)
#     result = dict(public)

#     # Make the tool response unambiguous for LLMs.
#     if "price_paise" in result:
#         result["price"] = _money(int(result["price_paise"]))
#     if "mrp_paise" in result:
#         result["mrp"] = _money(int(result["mrp_paise"]))

#     return _safe_json(result)


# def _safe_agent(agent: dict[str, Any]) -> dict[str, Any]:
#     return _safe_json(public_agent(agent))


# def _error(
#     code: str,
#     message: str,
#     **extra: Any,
# ) -> dict[str, Any]:
#     return {
#         "success": False,
#         "error": {
#             "code": code,
#             "message": message,
#             **extra,
#         },
#     }


# # ============================================================
# # MCP SERVER
# # ============================================================

# mcp = MCPServer(
#     MCP_APP_NAME,
#     instructions=(
#         "Umon Mart makes this merchant sellable to AI buyers. "
#         "Use live catalog data before making product claims. "
#         "The shared cart belongs to the user, not an agent. "
#         "At checkout, use the user's selected purchasing agent. "
#         "The backend is authoritative for price, stock, merchant settings, "
#         "agent policy, balance, payment, order and audit state. "
#         "Never override BLOCK or CONFIRM decisions. "
#         "Never invent payment success. "
#         "Only call checkout after clear user authorization."
#     ),
# )


# # ============================================================
# # APPS UI — preserving the working pattern from the old project
# # ============================================================

# apps = Apps()


# PRODUCT_UI_HTML = """
# <!doctype html>
# <html>
# <head>
# <meta charset="utf-8" />
# <meta name="viewport" content="width=device-width,initial-scale=1" />
# <style>
# :root { color-scheme: light; }
# body {
#   margin: 0;
#   padding: 18px;
#   background: #f8fafc;
#   color: #0f172a;
#   font-family: Inter, ui-sans-serif, system-ui, sans-serif;
# }
# .header {
#   display: flex;
#   justify-content: space-between;
#   gap: 16px;
#   margin-bottom: 14px;
# }
# .title { font-weight: 750; font-size: 18px; letter-spacing: -.02em; }
# .sub { color: #64748b; font-size: 12px; margin-top: 4px; }
# .grid {
#   display: grid;
#   grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
#   gap: 10px;
# }
# .card {
#   overflow: hidden;
#   border: 1px solid #e2e8f0;
#   border-radius: 16px;
#   background: #fff;
# }
# .image {
#   width: 100%;
#   aspect-ratio: 1.1;
#   object-fit: cover;
#   background: #f1f5f9;
# }
# .content { padding: 12px; }
# .name { font-weight: 700; font-size: 13px; }
# .meta { color: #64748b; font-size: 11px; margin-top: 3px; }
# .price { margin-top: 9px; font-weight: 800; font-size: 15px; }
# .stock { margin-top: 4px; color: #64748b; font-size: 10px; }
# </style>
# </head>
# <body>
# <div class="header">
#   <div>
#     <div class="title">Umon Mart</div>
#     <div class="sub">Live products selected by the merchant</div>
#   </div>
# </div>
# <div id="app" class="grid"></div>
# <script>
#   // The tool result is rendered by the ChatGPT Apps host.
#   // This resource is intentionally display-only. Mutations are executed by
#   // typed MCP tools so every action still passes the backend authorization
#   // and audit layer.
# </script>
# </body>
# </html>
# """

# apps.add_html_resource(
#     PRODUCT_UI_URI,
#     PRODUCT_UI_HTML,
#     name="umon-product-catalogue",
#     title="Umon Mart Product Catalogue",
#     description="Live merchant catalogue for AI-assisted shopping.",
#     prefers_border=True,
# )


# # ============================================================
# # ACCOUNT / AGENT TOOLS
# # ============================================================

# @mcp.tool()
# async def list_my_agents(ctx: Context) -> dict[str, Any]:
#     """List the authenticated Umon user's purchasing agents."""
#     user_id = await _user(ctx)
#     db = get_db()

#     agents = await (
#         db.agents.find({"owner_clerk_user_id": user_id})
#         .sort("created_at", -1)
#         .limit(50)
#         .to_list(length=50)
#     )

#     return {
#         "success": True,
#         "agents": [_safe_agent(agent) for agent in agents],
#     }


# @mcp.tool()
# async def get_my_agent(
#     agent_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Get one purchasing agent owned by the authenticated user."""
#     user_id = await _user(ctx)

#     agent = await get_owned_agent(
#         user_id,
#         agent_id,
#     )

#     if not agent:
#         return _error(
#             "AGENT_NOT_FOUND",
#             "Agent not found or not owned by this user.",
#         )

#     return {
#         "success": True,
#         "agent": _safe_agent(agent),
#     }


# @mcp.tool()
# async def get_agent_policy(
#     agent_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Return the exact current purchasing policy for an owned agent."""
#     user_id = await _user(ctx)

#     agent = await get_owned_agent(
#         user_id,
#         agent_id,
#     )

#     if not agent:
#         return _error(
#             "AGENT_NOT_FOUND",
#             "Agent not found or not owned by this user.",
#         )

#     return {
#         "success": True,
#         "agent_id": agent_id,
#         "policy": _safe_json(agent.get("policy", {})),
#     }


# @mcp.tool()
# async def get_agent_spending(
#     agent_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Return balance, daily/monthly spend and purchasing limits."""
#     user_id = await _user(ctx)

#     try:
#         stats = await agent_stats(
#             user_id,
#             agent_id,
#         )
#     except ValueError as exc:
#         return _error(
#             "AGENT_NOT_FOUND",
#             str(exc),
#         )

#     return {
#         "success": True,
#         "agent": stats.get("agent"),
#         "balance": stats.get("balance"),
#         "spending": stats.get("spending"),
#         "funding": stats.get("funding"),
#         "limits": stats.get("limits"),
#     }


# # ============================================================
# # CATALOG
# # ============================================================

# @mcp.tool()
# @apps.tool(
#     resource_uri=PRODUCT_UI_URI,
#     title="Search Umon Products",
#     description=(
#         "Search Umon Mart's live merchant catalogue and return current "
#         "product offers for the user."
#     ),
# )
# async def search_offers(
#     query: str = "",
#     category: str | None = None,
#     max_price: float | None = None,
#     limit: int = 8,
#     ctx: Context | None = None,
# ) -> dict[str, Any]:
#     """Search active Umon offers using the current merchant catalogue."""
#     if ctx is None:
#         raise RuntimeError("MCP context is required.")

#     await _user(ctx)

#     if max_price is not None and max_price < 0:
#         return _error(
#             "INVALID_MAX_PRICE",
#             "Maximum price cannot be negative.",
#         )

#     products = await service_search_products(
#         query=query,
#         category=category,
#         max_price_paise=(
#             round(max_price * 100)
#             if max_price is not None
#             else None
#         ),
#         limit=max(1, min(int(limit), 20)),
#     )

#     return {
#         "success": True,
#         "query": query,
#         "category": category,
#         "count": len(products),
#         "products": [
#             _safe_product(product)
#             for product in products
#         ],
#     }


# @mcp.tool()
# async def get_offer(
#     product_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Get one live active offer by product id."""
#     await _user(ctx)
#     db = get_db()

#     product = await db.products.find_one(
#         {
#             "_id": product_id,
#             "merchant_id": settings.merchant_id,
#             "active": True,
#         }
#     )

#     if not product:
#         return _error(
#             "OFFER_NOT_FOUND",
#             "This offer is unavailable.",
#         )

#     return {
#         "success": True,
#         "offer": _safe_product(product),
#     }


# @mcp.tool()
# async def list_categories(ctx: Context) -> dict[str, Any]:
#     """List active product categories currently available in Umon Mart."""
#     await _user(ctx)
#     db = get_db()

#     categories = await db.products.distinct(
#         "category",
#         {
#             "merchant_id": settings.merchant_id,
#             "active": True,
#         },
#     )

#     return {
#         "success": True,
#         "categories": sorted(
#             str(category)
#             for category in categories
#         ),
#     }


# # ============================================================
# # CROSS-SELL / UPSELL
# # ============================================================

# @mcp.tool()
# async def get_recommendations(
#     product_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """
#     Return merchant-defined complementary offers.

#     Recommendations are advisory: this tool never adds items to the cart
#     and never spends money. The AI should only suggest relevant complements.
#     """
#     await _user(ctx)

#     products = await service_get_recommendations(
#         product_id
#     )

#     return {
#         "success": True,
#         "product_id": product_id,
#         "recommendations": [
#             _safe_json(product)
#             for product in products
#         ],
#     }


# @mcp.tool()
# async def get_cart_recommendations(
#     ctx: Context,
#     limit: int = 6,
# ) -> dict[str, Any]:
#     """Find useful complementary offers for products already in the shared cart."""
#     user_id = await _user(ctx)
#     cart = await service_get_cart(user_id)

#     existing_ids = {
#         str(item.get("product_id"))
#         for item in cart.get("items", [])
#     }

#     recommendations: list[dict[str, Any]] = []
#     seen: set[str] = set()

#     for item in cart.get("items", []):
#         product_id = str(item.get("product_id"))
#         for recommendation in await service_get_recommendations(product_id):
#             rec_id = str(recommendation.get("id"))
#             if rec_id in existing_ids or rec_id in seen:
#                 continue

#             recommendations.append(
#                 _safe_json(recommendation)
#             )
#             seen.add(rec_id)

#             if len(recommendations) >= max(1, min(limit, 12)):
#                 break

#         if len(recommendations) >= max(1, min(limit, 12)):
#             break

#     return {
#         "success": True,
#         "cart": cart,
#         "recommendations": recommendations,
#     }


# # ============================================================
# # SHARED CART
# # ============================================================

# @mcp.tool()
# async def create_cart(ctx: Context) -> dict[str, Any]:
#     """Get the user's ONE shared Umon Mart cart, creating it if necessary."""
#     user_id = await _user(ctx)
#     return {
#         "success": True,
#         "cart": await service_get_cart(user_id),
#     }


# @mcp.tool()
# async def get_cart(ctx: Context) -> dict[str, Any]:
#     """Return the authenticated user's current shared cart."""
#     user_id = await _user(ctx)
#     return {
#         "success": True,
#         "cart": await service_get_cart(user_id),
#     }


# @mcp.tool()
# async def add_to_cart(
#     product_id: str,
#     quantity: int = Field(
#         default=1,
#         ge=1,
#         le=50,
#     ),
#     ctx: Context | None = None,
# ) -> dict[str, Any]:
#     """Add an offer to the shared user cart; no agent is selected here."""
#     if ctx is None:
#         raise RuntimeError("MCP context is required.")

#     user_id = await _user(ctx)

#     try:
#         cart = await service_add_to_cart(
#             user_id,
#             product_id,
#             int(quantity),
#         )
#     except ValueError as exc:
#         await audit(
#             owner_clerk_user_id=user_id,
#             action="MCP_CART_ITEM_ADDED",
#             result="FAILED",
#             metadata={
#                 "product_id": product_id,
#                 "quantity": int(quantity),
#             },
#             reason=str(exc),
#         )
#         return _error(
#             "CART_UPDATE_FAILED",
#             str(exc),
#         )

#     await audit(
#         owner_clerk_user_id=user_id,
#         action="MCP_CART_ITEM_ADDED",
#         result="SUCCESS",
#         metadata={
#             "product_id": product_id,
#             "quantity": int(quantity),
#         },
#     )

#     return {
#         "success": True,
#         "cart": cart,
#     }


# @mcp.tool()
# async def update_cart_item(
#     product_id: str,
#     quantity: int = Field(
#         ge=1,
#         le=50,
#     ),
#     ctx: Context | None = None,
# ) -> dict[str, Any]:
#     """Set a shared-cart item's quantity."""
#     if ctx is None:
#         raise RuntimeError("MCP context is required.")

#     user_id = await _user(ctx)

#     try:
#         cart = await service_update_cart_item(
#             user_id,
#             product_id,
#             int(quantity),
#         )
#     except ValueError as exc:
#         return _error(
#             "CART_UPDATE_FAILED",
#             str(exc),
#         )

#     return {
#         "success": True,
#         "cart": cart,
#     }


# @mcp.tool()
# async def remove_from_cart(
#     product_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Remove an item from the user's shared cart."""
#     user_id = await _user(ctx)

#     try:
#         cart = await service_remove_cart_item(
#             user_id,
#             product_id,
#         )
#     except ValueError as exc:
#         return _error(
#             "CART_UPDATE_FAILED",
#             str(exc),
#         )

#     return {
#         "success": True,
#         "cart": cart,
#     }


# @mcp.tool()
# async def clear_cart(
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Clear the user's entire shared cart."""
#     user_id = await _user(ctx)

#     return {
#         "success": True,
#         "cart": await service_clear_cart(
#             user_id
#         ),
#     }


# # ============================================================
# # CHECKOUT PREFLIGHT
# # ============================================================

# async def _fresh_checkout_snapshot(
#     user_id: str,
# ) -> dict[str, Any]:
#     """Re-read all current product prices/stock and recompute the checkout total."""
#     db = get_db()

#     cart = await service_get_cart(user_id)

#     if not cart.get("items"):
#         return _error(
#             "CART_EMPTY",
#             "The shared cart is empty.",
#         )

#     fresh_items: list[dict[str, Any]] = []
#     categories: list[str] = []
#     subtotal_paise = 0

#     for item in cart.get("items", []):
#         product_id = str(item.get("product_id"))
#         quantity = int(item.get("quantity", 0))

#         if quantity < 1:
#             return _error(
#                 "INVALID_QUANTITY",
#                 "Cart contains an invalid quantity.",
#             )

#         product = await db.products.find_one(
#             {
#                 "_id": product_id,
#                 "merchant_id": settings.merchant_id,
#                 "active": True,
#             }
#         )

#         if not product:
#             return _error(
#                 "OFFER_UNAVAILABLE",
#                 f"{product_id} is no longer available.",
#             )

#         stock = int(product.get("stock", 0))
#         if stock < quantity:
#             return _error(
#                 "INSUFFICIENT_STOCK",
#                 f"Only {stock} units of {product['name']} are available.",
#                 product_id=product_id,
#             )

#         unit_price_paise = int(
#             product.get("price_paise", 0)
#         )
#         line_total_paise = unit_price_paise * quantity
#         subtotal_paise += line_total_paise

#         category = str(
#             product.get("category", "")
#         ).strip().lower()
#         categories.append(category)

#         fresh_items.append(
#             {
#                 "product_id": product_id,
#                 "name": product.get("name"),
#                 "brand": product.get("brand"),
#                 "category": category,
#                 "quantity": quantity,
#                 "unit_price_paise": unit_price_paise,
#                 "unit_price": _money(unit_price_paise),
#                 "line_total_paise": line_total_paise,
#                 "line_total": _money(line_total_paise),
#                 "stock_available": stock,
#                 "image": product.get("image"),
#             }
#         )

#     delivery_fee_paise = (
#         3900
#         if 0 < subtotal_paise < 49900
#         else 0
#     )

#     total_paise = (
#         subtotal_paise + delivery_fee_paise
#     )

#     merchant = await db.merchants.find_one(
#         {"_id": settings.merchant_id}
#     )

#     if not merchant:
#         return _error(
#             "MERCHANT_UNAVAILABLE",
#             "Umon Mart is currently unavailable.",
#         )

#     return {
#         "success": True,
#         "cart": {
#             "items": fresh_items,
#             "item_count": sum(
#                 int(item["quantity"])
#                 for item in fresh_items
#             ),
#             "subtotal_paise": subtotal_paise,
#             "subtotal": _money(subtotal_paise),
#             "delivery_fee_paise": delivery_fee_paise,
#             "delivery_fee": _money(delivery_fee_paise),
#             "total_paise": total_paise,
#             "total": _money(total_paise),
#             "currency": "INR",
#         },
#         "categories": sorted(set(categories)),
#         "merchant": _safe_json(merchant),
#     }


# @mcp.tool()
# async def get_checkout_options(
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Show the user's current cart, available agents and supported checkout methods."""
#     user_id = await _user(ctx)

#     snapshot = await _fresh_checkout_snapshot(
#         user_id
#     )
#     if not snapshot.get("success"):
#         return snapshot

#     db = get_db()
#     agents = await (
#         db.agents.find(
#             {
#                 "owner_clerk_user_id": user_id,
#                 "status": {
#                     "$in": [
#                         "ACTIVE",
#                         "DISABLED",
#                     ]
#                 },
#             }
#         )
#         .sort("created_at", -1)
#         .limit(50)
#         .to_list(length=50)
#     )

#     return {
#         "success": True,
#         "cart": snapshot["cart"],
#         "payment_methods": [
#             {
#                 "id": "AGENT_BALANCE",
#                 "label": "Umon purchasing agent balance",
#                 "description": (
#                     "Use an already-funded Umon agent within its configured guardrails."
#                 ),
#                 "mcp_supported": True,
#             },
#             {
#                 "id": "RAZORPAY",
#                 "label": "Direct Razorpay",
#                 "description": (
#                     "Normal Razorpay checkout is available through the Umon store UI."
#                 ),
#                 "mcp_supported": False,
#             },
#         ],
#         "agents": [
#             _safe_agent(agent)
#             for agent in agents
#         ],
#     }


# @mcp.tool()
# async def validate_checkout(
#     agent_id: str,
#     confirmed: bool = False,
#     ctx: Context | None = None,
# ) -> dict[str, Any]:
#     """
#     Read-only purchase preflight.

#     This never reserves balance, changes stock or creates an order.
#     """
#     if ctx is None:
#         raise RuntimeError("MCP context is required.")

#     user_id = await _user(ctx)

#     agent = await get_owned_agent(
#         user_id,
#         agent_id,
#     )

#     if not agent:
#         return _error(
#             "AGENT_NOT_FOUND",
#             "Agent not found or not owned by this user.",
#         )

#     snapshot = await _fresh_checkout_snapshot(
#         user_id
#     )

#     if not snapshot.get("success"):
#         return snapshot

#     policy = await evaluate_purchase(
#         agent=agent,
#         amount_paise=int(
#             snapshot["cart"]["total_paise"]
#         ),
#         categories=snapshot["categories"],
#         merchant=snapshot["merchant"],
#         confirmed=confirmed,
#     )

#     await audit(
#         owner_clerk_user_id=user_id,
#         action="MCP_CHECKOUT_VALIDATED",
#         result=str(policy.get("decision", "BLOCK")),
#         agent_id=agent_id,
#         amount_paise=int(
#             snapshot["cart"]["total_paise"]
#         ),
#         reason=policy.get("reason"),
#         metadata={
#             "confirmed": bool(confirmed),
#             "read_only": True,
#         },
#     )

#     return {
#         "success": True,
#         "decision": policy.get("decision", "BLOCK"),
#         "agent": _safe_agent(agent),
#         "cart": snapshot["cart"],
#         "merchant": {
#             "id": settings.merchant_id,
#             "name": settings.merchant_name,
#         },
#         "policy": _safe_json(policy),
#         "money_movement": False,
#         "next_step": (
#             "Call checkout only after clear user authorization."
#             if policy.get("decision") == "ALLOW"
#             else "Do not call checkout unless a new preflight returns ALLOW."
#         ),
#     }


# # ============================================================
# # MONEY ACTION
# # ============================================================

# @mcp.tool()
# async def checkout(
#     agent_id: str,
#     confirmed: bool = False,
#     ctx: Context | None = None,
# ) -> dict[str, Any]:
#     """
#     Execute the current shared cart using the selected agent balance.

#     The tool intentionally accepts no amount. Umon calculates the final total
#     from the authoritative current catalog, then the existing checkout service
#     performs the real authorization and money/ledger/order workflow.
#     """
#     if ctx is None:
#         raise RuntimeError("MCP context is required.")

#     user_id = await _user(ctx)

#     try:
#         result = await checkout_with_agent_balance(
#             user_id,
#             agent_id,
#             bool(confirmed),
#         )
#     except Exception as exc:
#         await audit(
#             owner_clerk_user_id=user_id,
#             action="MCP_CHECKOUT_FAILED",
#             result="FAILED",
#             agent_id=agent_id,
#             reason=str(exc),
#             metadata={
#                 "confirmed": bool(confirmed),
#             },
#         )
#         return {
#             "success": False,
#             "status": "FAILED",
#             "agent_id": agent_id,
#             "error": {
#                 "code": "CHECKOUT_FAILED",
#                 "message": str(exc),
#             },
#             "money_movement": False,
#             "recovery": (
#                 "No successful checkout result was returned. "
#                 "Do not claim that the order was paid. "
#                 "The user can inspect the audit trail or retry after resolving the failure."
#             ),
#         }

#     safe = _safe_json(result)

#     return {
#         "success": bool(result.get("success", False)),
#         **safe,
#         "agent_id": agent_id,
#         "money_movement": bool(result.get("success", False)),
#     }


# # ============================================================
# # ORDERS + AUDIT
# # ============================================================

# @mcp.tool()
# async def get_order_status(
#     order_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Return the current payment and order state for an owned order."""
#     user_id = await _user(ctx)
#     db = get_db()

#     order = await db.orders.find_one(
#         {
#             "_id": order_id,
#             "owner_clerk_user_id": user_id,
#         }
#     )

#     if not order:
#         return _error(
#             "ORDER_NOT_FOUND",
#             "Order not found.",
#         )

#     return {
#         "success": True,
#         "order": _safe_json(order),
#     }


# @mcp.tool()
# async def get_order(
#     order_id: str,
#     ctx: Context,
# ) -> dict[str, Any]:
#     """Get an authenticated user's order."""
#     return await get_order_status(
#         order_id,
#         ctx,
#     )


# @mcp.tool()
# async def list_my_orders(
#     ctx: Context,
#     limit: int = 20,
# ) -> dict[str, Any]:
#     """List the authenticated user's recent orders."""
#     user_id = await _user(ctx)
#     db = get_db()

#     docs = await (
#         db.orders.find(
#             {
#                 "owner_clerk_user_id": user_id,
#             }
#         )
#         .sort("created_at", -1)
#         .limit(max(1, min(int(limit), 50)))
#         .to_list(length=50)
#     )

#     return {
#         "success": True,
#         "count": len(docs),
#         "orders": [
#             _safe_json(order)
#             for order in docs
#         ],
#     }


# @mcp.tool()
# async def get_my_activity(
#     ctx: Context,
#     agent_id: str | None = None,
#     limit: int = 30,
# ) -> dict[str, Any]:
#     """Show the authenticated user's recent audit trail."""
#     user_id = await _user(ctx)
#     db = get_db()

#     query: dict[str, Any] = {
#         "owner_clerk_user_id": user_id,
#     }

#     if agent_id:
#         agent = await get_owned_agent(
#             user_id,
#             agent_id,
#         )
#         if not agent:
#             return _error(
#                 "AGENT_NOT_FOUND",
#                 "Agent not found or not owned by this user.",
#             )
#         query["agent_id"] = agent_id

#     events = await (
#         db.audit_events.find(query)
#         .sort("created_at", -1)
#         .limit(max(1, min(int(limit), 100)))
#         .to_list(length=100)
#     )

#     return {
#         "success": True,
#         "count": len(events),
#         "events": [
#             _safe_json(event)
#             for event in events
#         ],
#     }


# # ============================================================
# # OAUTH MODELS
# # ============================================================


# class OAuthRegisterBody(BaseModel):
#     client_name: str = "ChatGPT"
#     redirect_uris: list[str] = Field(min_length=1)
#     grant_types: list[str] = Field(
#         default_factory=lambda: [
#             "authorization_code",
#             "refresh_token",
#         ]
#     )
#     response_types: list[str] = Field(
#         default_factory=lambda: ["code"]
#     )
#     token_endpoint_auth_method: str = "none"

# class OAuthCompleteBody(BaseModel):
#     client_id: str
#     redirect_uri: str
#     scope: str = MCP_SCOPE
#     state: str | None = None
#     code_challenge: str | None = None
#     code_challenge_method: str | None = None
#     resource: str = MCP_ENDPOINT
#     clerk_token: str


# class OAuthTokenBody(BaseModel):
#     grant_type: str
#     client_id: str
#     client_secret: str | None = None
#     code: str | None = None
#     redirect_uri: str | None = None
#     code_verifier: str | None = None
#     refresh_token: str | None = None
#     resource: str | None = None


# # ============================================================
# # OAUTH HELPERS
# # ============================================================


# def _valid_redirect_uri(uri: str) -> bool:
#     try:
#         parsed = urlparse(uri)
#     except Exception:
#         return False

#     if parsed.scheme not in {"http", "https"}:
#         return False

#     host = (parsed.hostname or "").lower()

#     if host in {"localhost", "127.0.0.1"}:
#         return True

#     if host in {"chatgpt.com", "chat.openai.com"}:
#         return True

#     # Local Umon frontend is also valid for the consent bridge.
#     return uri.startswith(FRONTEND_URL)


# def _redirect_with_params(
#     redirect_uri: str,
#     **params: str,
# ) -> RedirectResponse:
#     encoded = urlencode(
#         {
#             key: value
#             for key, value in params.items()
#             if value is not None
#         }
#     )

#     separator = "&" if "?" in redirect_uri else "?"
#     return RedirectResponse(
#         f"{redirect_uri}{separator}{encoded}",
#         status_code=302,
#     )


# def _pkce_s256(verifier: str) -> str:
#     digest = hashlib.sha256(
#         verifier.encode("utf-8")
#     ).digest()

#     return base64.urlsafe_b64encode(
#         digest
#     ).rstrip(b"=").decode("ascii")


# # ============================================================
# # FASTAPI LIFESPAN
# # ============================================================

# @asynccontextmanager
# async def lifespan(app: FastAPI) -> AsyncIterator[None]:
#     # Start Umon's normal database lifecycle first.
#     async with db_lifespan(app):
#         # IMPORTANT:
#         # Streamable HTTP MCP requires the MCP session manager
#         # task group to be running for incoming /mcp requests.
#         async with mcp.session_manager.run():
#             yield


# app = FastAPI(
#     title="Umon Mart MCP",
#     version=MCP_APP_VERSION,
#     description="Remote MCP server for Umon agentic commerce.",
#     lifespan=lifespan,
# )


# # ============================================================
# # CORS
# # ============================================================

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         FRONTEND_URL,
#         "https://chatgpt.com",
#         "https://chat.openai.com",
#     ],
#     allow_credentials=True,
#     allow_methods=[
#         "GET",
#         "POST",
#         "OPTIONS",
#     ],
#     allow_headers=[
#         "*",
#     ],
#     expose_headers=[
#         "Mcp-Session-Id",
#     ],
# )


# # ============================================================
# # ROOT / HEALTH
# # ============================================================

# @app.get("/")
# async def root() -> dict[str, Any]:
#     return {
#         "name": MCP_APP_NAME,
#         "version": MCP_APP_VERSION,
#         "status": "online",
#         "mcp": MCP_ENDPOINT,
#         "oauth": f"{MCP_PUBLIC_URL}/oauth/authorize",
#     }


# @app.get("/health")
# async def health() -> dict[str, Any]:
#     try:
#         await get_db().command("ping")
#         mongo_ok = True
#     except Exception:
#         mongo_ok = False

#     return {
#         "status": "ok" if mongo_ok else "degraded",
#         "service": MCP_APP_NAME,
#         "mongodb": mongo_ok,
#         "mcp_endpoint": MCP_ENDPOINT,
#         "oauth_enabled": True,
#     }


# # ============================================================
# # OAUTH DISCOVERY
# # ============================================================

# @app.get("/.well-known/oauth-protected-resource")
# async def oauth_protected_resource() -> JSONResponse:
#     return JSONResponse(
#         {
#             "resource": MCP_ENDPOINT,
#             "authorization_servers": [MCP_PUBLIC_URL],
#             "scopes_supported": [MCP_SCOPE],
#             "bearer_methods_supported": ["header"],
#         }
#     )


# @app.get("/.well-known/oauth-protected-resource/mcp")
# async def oauth_protected_resource_mcp() -> JSONResponse:
#     return await oauth_protected_resource()


# @app.get("/.well-known/oauth-authorization-server")
# async def oauth_authorization_server() -> JSONResponse:
#     return JSONResponse(
#         {
#             "issuer": MCP_PUBLIC_URL,
#             "authorization_endpoint": f"{MCP_PUBLIC_URL}/oauth/authorize",
#             "token_endpoint": f"{MCP_PUBLIC_URL}/oauth/token",
#             "registration_endpoint": f"{MCP_PUBLIC_URL}/oauth/register",
#             "response_types_supported": ["code"],
#             "grant_types_supported": [
#                 "authorization_code",
#                 "refresh_token",
#             ],
#             "code_challenge_methods_supported": ["S256"],
#             "scopes_supported": [MCP_SCOPE],
#             "token_endpoint_auth_methods_supported": ["none"],
#         }
#     )


# # ============================================================
# # DYNAMIC CLIENT REGISTRATION
# # ============================================================

# @app.post("/oauth/register")
# async def oauth_register(
#     body: OAuthRegisterBody,
# ) -> JSONResponse:
#     for redirect_uri in body.redirect_uris:
#         if not _valid_redirect_uri(redirect_uri):
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Redirect URI is not allowed: {redirect_uri}",
#             )

#     db = get_db()
#     client_id = f"umon_client_{secrets.token_urlsafe(24)}"

#     await db.mcp_oauth_clients.insert_one(
#         {
#             "_id": client_id,
#             "client_id": client_id,
#             "client_name": body.client_name,
#             "redirect_uris": body.redirect_uris,
#             "grant_types": body.grant_types,
#             "response_types": body.response_types,
#             "token_endpoint_auth_method": body.token_endpoint_auth_method,
#             "created_at": utc_now(),
#         }
#     )

#     return JSONResponse(
#         {
#             "client_id": client_id,
#             "client_name": body.client_name,
#             "redirect_uris": body.redirect_uris,
#             "grant_types": body.grant_types,
#             "response_types": body.response_types,
#             "token_endpoint_auth_method": body.token_endpoint_auth_method,
#         }
#     )


# # ============================================================
# # AUTHORIZATION ENDPOINT
# # ============================================================

# @app.get("/oauth/authorize", response_class=HTMLResponse)
# async def oauth_authorize(request: Request) -> HTMLResponse:
#     params = request.query_params

#     client_id = params.get("client_id", "")
#     redirect_uri = params.get("redirect_uri", "")
#     response_type = params.get("response_type", "code")
#     scope = params.get("scope", MCP_SCOPE)
#     state = params.get("state") or ""
#     code_challenge = params.get("code_challenge") or ""
#     code_challenge_method = (
#         params.get("code_challenge_method") or ""
#     )
#     resource = params.get("resource") or MCP_ENDPOINT

#     if response_type != "code":
#         return HTMLResponse(
#             "Unsupported OAuth response_type.",
#             status_code=400,
#         )

#     if not client_id:
#         return HTMLResponse(
#             "Missing OAuth client_id.",
#             status_code=400,
#         )

#     if not _valid_redirect_uri(redirect_uri):
#         return HTMLResponse(
#             "Redirect URI is not allowed.",
#             status_code=400,
#         )

#     db = get_db()
#     client = await db.mcp_oauth_clients.find_one(
#         {"client_id": client_id}
#     )

#     if client and redirect_uri not in client.get(
#         "redirect_uris",
#         [],
#     ):
#         return HTMLResponse(
#             "Redirect URI is not registered for this client.",
#             status_code=400,
#         )

#     # Preserve OAuth parameters while moving the browser to Umon's Clerk UI.
#     query = urlencode(
#     {
#         "client_id": client_id,
#         "redirect_uri": redirect_uri,
#         "scope": scope,
#         "state": state,
#         "code_challenge": code_challenge,
#         "code_challenge_method": code_challenge_method,
#         "resource": resource,
#     }
# )

#     connect_url = f"{FRONTEND_URL}/mcp/connect?{query}"

#     html = f"""
# <!doctype html>
# <html>
# <head>
# <meta charset="utf-8" />
# <meta name="viewport" content="width=device-width,initial-scale=1" />
# <title>Connect Umon Mart</title>
# <style>
# body{{margin:0;background:#f8fafc;color:#0f172a;font-family:Inter,system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;padding:20px}}
# .card{{width:min(470px,100%);background:white;border:1px solid #e2e8f0;border-radius:24px;padding:30px;box-shadow:0 20px 60px rgba(15,23,42,.10)}}
# .mark{{width:44px;height:44px;display:grid;place-items:center;border-radius:13px;background:#0f172a;color:#fff;font-weight:800}}
# h1{{margin:22px 0 8px;font-size:28px;letter-spacing:-.03em}}
# p{{margin:0;color:#64748b;line-height:1.55}}
# .scope{{margin:22px 0;padding:16px;border-radius:15px;background:#f8fafc;color:#475569;font-size:13px;line-height:1.7}}
# .scope strong{{display:block;color:#0f172a;margin-bottom:4px}}
# a{{display:block;background:#0f172a;color:white;text-align:center;text-decoration:none;border-radius:12px;padding:13px 16px;font-weight:750}}
# small{{display:block;margin-top:13px;color:#94a3b8;font-size:11px;line-height:1.5}}
# </style>
# </head>
# <body>
# <div class="card">
# <div class="mark">U</div>
# <h1>Connect Umon Mart</h1>
# <p>Use your existing Umon Mart account with ChatGPT. Your products, cart and purchasing agents stay tied to the same signed-in user.</p>
# <div class="scope"><strong>ChatGPT will be able to</strong>Search live products<br/>View and update your shared cart<br/>View your purchasing agents and guardrails<br/>Request purchases through an eligible agent</div>
# <a href="{connect_url}">Continue to Umon</a>
# <small>You will sign in with Clerk if needed, then approve the connection. Money actions remain bounded by Umon's merchant and agent policies.</small>
# </div>
# </body>
# </html>
# """

#     return HTMLResponse(html)


# # ============================================================
# # CLERK CONSENT COMPLETION
# # ============================================================

# @app.post("/oauth/complete")
# async def oauth_complete(
#     body: OAuthCompleteBody,
# ):
#     if not _valid_redirect_uri(body.redirect_uri):
#         raise HTTPException(
#             status_code=400,
#             detail="Redirect URI is not allowed.",
#         )



#     db = get_db()
#     client = await db.mcp_oauth_clients.find_one(
#         {"client_id": body.client_id}
#     )

#     if client and body.redirect_uri not in client.get(
#         "redirect_uris",
#         [],
#     ):
#         raise HTTPException(
#             status_code=400,
#             detail="Redirect URI is not registered for this client.",
#         )

#     claims = await _verify_clerk_token(
#         body.clerk_token
#     )
#     clerk_user_id = str(claims["sub"])

#     await _ensure_active_user(
#         clerk_user_id,
#         claims,
#     )

#     raw_code = (
#         f"umon_code_{secrets.token_urlsafe(32)}"
#     )

#     await db.mcp_oauth_codes.insert_one(
#         {
#             "_id": _hash(raw_code),
#             "code_hash": _hash(raw_code),
#             "client_id": body.client_id,
#             "redirect_uri": body.redirect_uri,
#             "clerk_user_id": clerk_user_id,
#             "scope": body.scope,
#             "code_challenge": body.code_challenge,
#             "code_challenge_method": body.code_challenge_method,
#             "expires_at": utc_now() + timedelta(
#                 seconds=OAUTH_CODE_TTL_SECONDS
#             ),
#             "created_at": utc_now(),
#         }
#     )

#     await audit(
#         owner_clerk_user_id=clerk_user_id,
#         action="MCP_OAUTH_CONSENT_GRANTED",
#         result="SUCCESS",
#         metadata={
#             "client_id": body.client_id,
#             "scope": body.scope,
#         },
#     )

#     return _redirect_with_params(
#         body.redirect_uri,
#         code=raw_code,
#         state=body.state or "",
#     )


# # ============================================================
# # TOKEN ENDPOINT
# # ============================================================
# @app.post("/oauth/token")
# async def oauth_token(
#     grant_type: str = Form(...),
#     client_id: str = Form(...),
#     client_secret: str | None = Form(None),
#     code: str | None = Form(None),
#     redirect_uri: str | None = Form(None),
#     code_verifier: str | None = Form(None),
#     refresh_token: str | None = Form(None),
#     resource: str | None = Form(None),
# ) -> JSONResponse:
#     await _cleanup_oauth()

#     db = get_db()

#     # --------------------------------------------------------
#     # Validate requested resource
#     # --------------------------------------------------------

#     expected_resource = MCP_ENDPOINT

#     if resource and resource != expected_resource:
#         raise HTTPException(
#             status_code=400,
#             detail="Invalid resource.",
#         )

#     # --------------------------------------------------------
#     # Authorization code
#     # --------------------------------------------------------

#     if grant_type == "authorization_code":
#         if not code:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Authorization code is required.",
#             )

#         code_record = await db.mcp_oauth_codes.find_one_and_delete(
#             {
#                 "code_hash": _hash(code),
#                 "client_id": client_id,
#             }
#         )

#         if not code_record:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Invalid or expired authorization code.",
#             )

#         # ----------------------------------------------------
#         # Redirect URI binding
#         # ----------------------------------------------------

#         if (
#             redirect_uri
#             and redirect_uri != code_record.get("redirect_uri")
#         ):
#             raise HTTPException(
#                 status_code=400,
#                 detail="OAuth redirect URI mismatch.",
#             )

#         # ----------------------------------------------------
#         # Resource binding
#         # ----------------------------------------------------

#         stored_resource = code_record.get(
#             "resource",
#             MCP_ENDPOINT,
#         )

#         if resource and resource != stored_resource:
#             raise HTTPException(
#                 status_code=400,
#                 detail="OAuth resource mismatch.",
#             )

#         # ----------------------------------------------------
#         # PKCE
#         # ----------------------------------------------------

#         challenge = code_record.get("code_challenge")

#         if challenge:
#             if not code_verifier:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="PKCE code_verifier is required.",
#                 )

#             method = code_record.get(
#                 "code_challenge_method"
#             )

#             if method not in {None, "", "S256"}:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Only S256 PKCE is supported.",
#                 )

#             if not secrets.compare_digest(
#                 _pkce_s256(code_verifier),
#                 challenge,
#             ):
#                 raise HTTPException(
#                     status_code=400,
#                     detail="PKCE verification failed.",
#                 )

#         # ----------------------------------------------------
#         # Issue tokens
#         # ----------------------------------------------------

#         raw_access_token = (
#             f"umon_mcp_{secrets.token_urlsafe(40)}"
#         )

#         raw_refresh_token = (
#             f"umon_refresh_{secrets.token_urlsafe(40)}"
#         )

#         scope = code_record.get(
#             "scope",
#             MCP_SCOPE,
#         )

#         await db.mcp_oauth_tokens.insert_one(
#             {
#                 "_id": _hash(raw_access_token),
#                 "token_hash": _hash(raw_access_token),
#                 "client_id": code_record["client_id"],
#                 "clerk_user_id": code_record["clerk_user_id"],
#                 "scope": scope,
#                 "resource": stored_resource,
#                 "expires_at": utc_now()
#                 + timedelta(
#                     seconds=OAUTH_ACCESS_TTL_SECONDS
#                 ),
#                 "created_at": utc_now(),
#             }
#         )

#         await db.mcp_oauth_refresh_tokens.insert_one(
#             {
#                 "_id": _hash(raw_refresh_token),
#                 "token_hash": _hash(raw_refresh_token),
#                 "client_id": code_record["client_id"],
#                 "clerk_user_id": code_record["clerk_user_id"],
#                 "scope": scope,
#                 "resource": stored_resource,
#                 "expires_at": utc_now()
#                 + timedelta(
#                     seconds=OAUTH_REFRESH_TTL_SECONDS
#                 ),
#                 "created_at": utc_now(),
#             }
#         )

#         await audit(
#             owner_clerk_user_id=code_record[
#                 "clerk_user_id"
#             ],
#             action="MCP_ACCESS_TOKEN_ISSUED",
#             result="SUCCESS",
#             metadata={
#                 "client_id": code_record["client_id"],
#                 "scope": scope,
#                 "resource": stored_resource,
#             },
#         )

#         response = JSONResponse(
#             {
#                 "access_token": raw_access_token,
#                 "token_type": "Bearer",
#                 "expires_in": OAUTH_ACCESS_TTL_SECONDS,
#                 "refresh_token": raw_refresh_token,
#                 "scope": scope,
#             }
#         )

#         response.headers["Cache-Control"] = "no-store"
#         response.headers["Pragma"] = "no-cache"

#         return response

#     # --------------------------------------------------------
#     # Refresh token
#     # --------------------------------------------------------

#     if grant_type == "refresh_token":
#         if not refresh_token:
#             raise HTTPException(
#                 status_code=400,
#                 detail="refresh_token is required.",
#             )

#         refresh = await db.mcp_oauth_refresh_tokens.find_one(
#             {
#                 "token_hash": _hash(refresh_token),
#                 "client_id": client_id,
#             }
#         )

#         if not refresh:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Invalid refresh token.",
#             )

#         expires_at = refresh.get("expires_at")

#         if (
#             not isinstance(expires_at, datetime)
#             or expires_at <= utc_now()
#         ):
#             raise HTTPException(
#                 status_code=400,
#                 detail="Refresh token expired.",
#             )

#         stored_resource = refresh.get(
#             "resource",
#             MCP_ENDPOINT,
#         )

#         if resource and resource != stored_resource:
#             raise HTTPException(
#                 status_code=400,
#                 detail="OAuth resource mismatch.",
#             )

#         raw_access_token = (
#             f"umon_mcp_{secrets.token_urlsafe(40)}"
#         )

#         await db.mcp_oauth_tokens.insert_one(
#             {
#                 "_id": _hash(raw_access_token),
#                 "token_hash": _hash(raw_access_token),
#                 "client_id": refresh["client_id"],
#                 "clerk_user_id": refresh["clerk_user_id"],
#                 "scope": refresh.get(
#                     "scope",
#                     MCP_SCOPE,
#                 ),
#                 "resource": stored_resource,
#                 "expires_at": utc_now()
#                 + timedelta(
#                     seconds=OAUTH_ACCESS_TTL_SECONDS
#                 ),
#                 "created_at": utc_now(),
#             }
#         )

#         response = JSONResponse(
#             {
#                 "access_token": raw_access_token,
#                 "token_type": "Bearer",
#                 "expires_in": OAUTH_ACCESS_TTL_SECONDS,
#                 "scope": refresh.get(
#                     "scope",
#                     MCP_SCOPE,
#                 ),
#             }
#         )

#         response.headers["Cache-Control"] = "no-store"
#         response.headers["Pragma"] = "no-cache"

#         return response

#     raise HTTPException(
#         status_code=400,
#         detail="Unsupported grant_type.",
#     )


# # ============================================================
# # MCP STREAMABLE HTTP
# # ============================================================

# def _transport_host_values() -> list[str]:
#     parsed = urlparse(MCP_PUBLIC_URL)

#     host = parsed.hostname or "localhost"

#     values = {
#         host,
#         f"{host}:443",
#         "localhost",
#         "localhost:8002",
#         "127.0.0.1",
#         "127.0.0.1:8002",
#     }

#     if parsed.netloc:
#         values.add(parsed.netloc)

#     if parsed.port:
#         values.add(f"{host}:{parsed.port}")

#     # Render / reverse-proxy deployments may send the public hostname
#     # without an explicit port.
#     if host.endswith(".onrender.com"):
#         values.add(host)

#     return sorted(values)

# transport_security = TransportSecuritySettings(
#     enable_dns_rebinding_protection=True,
#     allowed_hosts=_transport_host_values(),
#     allowed_origins=[
#         FRONTEND_URL,
#         "https://chatgpt.com",
#         "https://chat.openai.com",
#     ],
# )

# mcp_http_app = mcp.streamable_http_app(
#     streamable_http_path="/",
#     json_response=True,
#     transport_security=transport_security,
# )

# app.mount(
#     "/mcp",
#     mcp_http_app,
# )





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
    uvicorn app.mcp:app --reload --port 8002

Your normal Umon API can continue to run on port 8001.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import os
import secrets
from typing import Any, AsyncIterator
from urllib.parse import urlencode, urlparse

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from mcp.server.apps import Apps
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

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

OAUTH_CODE_TTL_SECONDS = 120
OAUTH_ACCESS_TTL_SECONDS = 3600
OAUTH_REFRESH_TTL_SECONDS = 60 * 60 * 24 * 30

PRODUCT_UI_URI = "ui://umon/product-catalogue.html"


# ============================================================
# MONGO OAUTH STATE
# ============================================================


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


async def _resolve_mcp_user(ctx: Context) -> str:
    headers = ctx.headers or {}
    authorization = headers.get("authorization", "")

    if not authorization.lower().startswith("bearer "):
        raise PermissionError(
            "Umon authentication is required."
        )

    bearer = authorization[7:].strip()
    if not bearer:
        raise PermissionError("Empty bearer token.")

    await _cleanup_oauth()
    db = get_db()

    oauth_token = await db.mcp_oauth_tokens.find_one(
        {"token_hash": _hash(bearer)}
    )

    if oauth_token:
        expires_at = oauth_token.get("expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= utc_now():
            raise PermissionError("Umon MCP access token expired.")

        user_id = str(oauth_token["clerk_user_id"])
        await _ensure_active_user(user_id)
        return user_id

    # Local development / MCP Inspector convenience: allow a valid Clerk JWT
    # directly. ChatGPT will use the opaque OAuth token above.
    try:
        claims = await _verify_clerk_token(bearer)
        user_id = str(claims["sub"])
        await _ensure_active_user(user_id, claims)
        return user_id
    except HTTPException as exc:
        raise PermissionError(str(exc.detail)) from exc


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
    public = public_product(product)
    result = dict(public)

    # Make the tool response unambiguous for LLMs.
    if "price_paise" in result:
        result["price"] = _money(int(result["price_paise"]))
    if "mrp_paise" in result:
        result["mrp"] = _money(int(result["mrp_paise"]))

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

mcp = MCPServer(
    MCP_APP_NAME,
    instructions=(
        "Umon Mart makes this merchant sellable to AI buyers. "
        "Use live catalog data before making product claims. "
        "The shared cart belongs to the user, not an agent. "
        "At checkout, use the user's selected purchasing agent. "
        "The backend is authoritative for price, stock, merchant settings, "
        "agent policy, balance, payment, order and audit state. "
        "Never override BLOCK or CONFIRM decisions. "
        "Never invent payment success. "
        "Only call checkout after clear user authorization."
    ),
)


# ============================================================
# APPS UI — preserving the working pattern from the old project
# ============================================================

apps = Apps()


PRODUCT_UI_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
:root { color-scheme: light; }
body {
  margin: 0;
  padding: 18px;
  background: #f8fafc;
  color: #0f172a;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}
.header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.title { font-weight: 750; font-size: 18px; letter-spacing: -.02em; }
.sub { color: #64748b; font-size: 12px; margin-top: 4px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.card {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #fff;
}
.image {
  width: 100%;
  aspect-ratio: 1.1;
  object-fit: cover;
  background: #f1f5f9;
}
.content { padding: 12px; }
.name { font-weight: 700; font-size: 13px; }
.meta { color: #64748b; font-size: 11px; margin-top: 3px; }
.price { margin-top: 9px; font-weight: 800; font-size: 15px; }
.stock { margin-top: 4px; color: #64748b; font-size: 10px; }
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="title">Umon Mart</div>
    <div class="sub">Live products selected by the merchant</div>
  </div>
</div>
<div id="app" class="grid"></div>
<script>
  // The tool result is rendered by the ChatGPT Apps host.
  // This resource is intentionally display-only. Mutations are executed by
  // typed MCP tools so every action still passes the backend authorization
  // and audit layer.
</script>
</body>
</html>
"""

apps.add_html_resource(
    PRODUCT_UI_URI,
    PRODUCT_UI_HTML,
    name="umon-product-catalogue",
    title="Umon Mart Product Catalogue",
    description="Live merchant catalogue for AI-assisted shopping.",
    prefers_border=True,
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
@apps.tool(
    resource_uri=PRODUCT_UI_URI,
    title="Search Umon Products",
    description=(
        "Search Umon Mart's live merchant catalogue and return current "
        "product offers for the user."
    ),
)
async def search_offers(
    query: str = "",
    category: str | None = None,
    max_price: float | None = None,
    limit: int = 8,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Search active Umon offers using the current merchant catalogue."""
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
    """Get one live active offer by product id."""
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
    Return merchant-defined complementary offers.

    Recommendations are advisory: this tool never adds items to the cart
    and never spends money. The AI should only suggest relevant complements.
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
    """Find useful complementary offers for products already in the shared cart."""
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


@mcp.tool()
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
    clerk_token: str


class OAuthTokenBody(BaseModel):
    grant_type: str
    client_id: str
    client_secret: str | None = None
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None


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

    # Local Umon frontend is also valid for the consent bridge.
    return uri.startswith(FRONTEND_URL)


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
# FASTAPI LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Reuse the same production-tested Umon DB startup/index/seed lifecycle.
    async with db_lifespan(app):
        yield


app = FastAPI(
    title="Umon Mart MCP",
    version=MCP_APP_VERSION,
    description="Remote MCP server for Umon agentic commerce.",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
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
# ROOT / HEALTH
# ============================================================

@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": MCP_APP_NAME,
        "version": MCP_APP_VERSION,
        "status": "online",
        "mcp": MCP_ENDPOINT,
        "oauth": f"{MCP_PUBLIC_URL}/oauth/authorize",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        await get_db().command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False

    return {
        "status": "ok" if mongo_ok else "degraded",
        "service": MCP_APP_NAME,
        "mongodb": mongo_ok,
        "mcp_endpoint": MCP_ENDPOINT,
        "oauth_enabled": True,
    }


# ============================================================
# OAUTH DISCOVERY
# ============================================================

@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource() -> JSONResponse:
    return JSONResponse(
        {
            "resource": MCP_ENDPOINT,
            "authorization_servers": [MCP_PUBLIC_URL],
            "scopes_supported": [MCP_SCOPE],
            "bearer_methods_supported": ["header"],
        }
    )


@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_resource_mcp() -> JSONResponse:
    return await oauth_protected_resource()


@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server() -> JSONResponse:
    return JSONResponse(
        {
            "issuer": MCP_PUBLIC_URL,
            "authorization_endpoint": f"{MCP_PUBLIC_URL}/oauth/authorize",
            "token_endpoint": f"{MCP_PUBLIC_URL}/oauth/token",
            "registration_endpoint": f"{MCP_PUBLIC_URL}/oauth/register",
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


# ============================================================
# DYNAMIC CLIENT REGISTRATION
# ============================================================

@app.post("/oauth/register")
async def oauth_register(
    body: OAuthRegisterBody,
) -> JSONResponse:
    for redirect_uri in body.redirect_uris:
        if not _valid_redirect_uri(redirect_uri):
            raise HTTPException(
                status_code=400,
                detail=f"Redirect URI is not allowed: {redirect_uri}",
            )

    db = get_db()
    client_id = f"umon_client_{secrets.token_urlsafe(24)}"

    await db.mcp_oauth_clients.insert_one(
        {
            "_id": client_id,
            "client_id": client_id,
            "client_name": body.client_name,
            "redirect_uris": body.redirect_uris,
            "grant_types": body.grant_types,
            "response_types": body.response_types,
            "token_endpoint_auth_method": body.token_endpoint_auth_method,
            "created_at": utc_now(),
        }
    )

    return JSONResponse(
        {
            "client_id": client_id,
            "client_name": body.client_name,
            "redirect_uris": body.redirect_uris,
            "grant_types": body.grant_types,
            "response_types": body.response_types,
            "token_endpoint_auth_method": body.token_endpoint_auth_method,
        }
    )


# ============================================================
# AUTHORIZATION ENDPOINT
# ============================================================

@app.get("/oauth/authorize", response_class=HTMLResponse)
async def oauth_authorize(request: Request) -> HTMLResponse:
    params = request.query_params

    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    response_type = params.get("response_type", "code")
    scope = params.get("scope", MCP_SCOPE)
    state = params.get("state") or ""
    code_challenge = params.get("code_challenge") or ""
    code_challenge_method = (
        params.get("code_challenge_method") or ""
    )

    if response_type != "code":
        return HTMLResponse(
            "Unsupported OAuth response_type.",
            status_code=400,
        )

    if not client_id:
        return HTMLResponse(
            "Missing OAuth client_id.",
            status_code=400,
        )

    if not _valid_redirect_uri(redirect_uri):
        return HTMLResponse(
            "Redirect URI is not allowed.",
            status_code=400,
        )

    db = get_db()
    client = await db.mcp_oauth_clients.find_one(
        {"client_id": client_id}
    )

    if client and redirect_uri not in client.get(
        "redirect_uris",
        [],
    ):
        return HTMLResponse(
            "Redirect URI is not registered for this client.",
            status_code=400,
        )

    # Preserve OAuth parameters while moving the browser to Umon's Clerk UI.
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
    )

    connect_url = f"{FRONTEND_URL}/mcp/connect?{query}"

    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Connect Umon Mart</title>
<style>
body{{margin:0;background:#f8fafc;color:#0f172a;font-family:Inter,system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;padding:20px}}
.card{{width:min(470px,100%);background:white;border:1px solid #e2e8f0;border-radius:24px;padding:30px;box-shadow:0 20px 60px rgba(15,23,42,.10)}}
.mark{{width:44px;height:44px;display:grid;place-items:center;border-radius:13px;background:#0f172a;color:#fff;font-weight:800}}
h1{{margin:22px 0 8px;font-size:28px;letter-spacing:-.03em}}
p{{margin:0;color:#64748b;line-height:1.55}}
.scope{{margin:22px 0;padding:16px;border-radius:15px;background:#f8fafc;color:#475569;font-size:13px;line-height:1.7}}
.scope strong{{display:block;color:#0f172a;margin-bottom:4px}}
a{{display:block;background:#0f172a;color:white;text-align:center;text-decoration:none;border-radius:12px;padding:13px 16px;font-weight:750}}
small{{display:block;margin-top:13px;color:#94a3b8;font-size:11px;line-height:1.5}}
</style>
</head>
<body>
<div class="card">
<div class="mark">U</div>
<h1>Connect Umon Mart</h1>
<p>Use your existing Umon Mart account with ChatGPT. Your products, cart and purchasing agents stay tied to the same signed-in user.</p>
<div class="scope"><strong>ChatGPT will be able to</strong>Search live products<br/>View and update your shared cart<br/>View your purchasing agents and guardrails<br/>Request purchases through an eligible agent</div>
<a href="{connect_url}">Continue to Umon</a>
<small>You will sign in with Clerk if needed, then approve the connection. Money actions remain bounded by Umon's merchant and agent policies.</small>
</div>
</body>
</html>
"""

    return HTMLResponse(html)


# ============================================================
# CLERK CONSENT COMPLETION
# ============================================================

@app.post("/oauth/complete")
async def oauth_complete(
    body: OAuthCompleteBody,
):
    if not _valid_redirect_uri(body.redirect_uri):
        raise HTTPException(
            status_code=400,
            detail="Redirect URI is not allowed.",
        )

    db = get_db()
    client = await db.mcp_oauth_clients.find_one(
        {"client_id": body.client_id}
    )

    if client and body.redirect_uri not in client.get(
        "redirect_uris",
        [],
    ):
        raise HTTPException(
            status_code=400,
            detail="Redirect URI is not registered for this client.",
        )

    claims = await _verify_clerk_token(
        body.clerk_token
    )
    clerk_user_id = str(claims["sub"])

    await _ensure_active_user(
        clerk_user_id,
        claims,
    )

    raw_code = (
        f"umon_code_{secrets.token_urlsafe(32)}"
    )

    await db.mcp_oauth_codes.insert_one(
        {
            "_id": _hash(raw_code),
            "code_hash": _hash(raw_code),
            "client_id": body.client_id,
            "redirect_uri": body.redirect_uri,
            "clerk_user_id": clerk_user_id,
            "scope": body.scope,
            "code_challenge": body.code_challenge,
            "code_challenge_method": body.code_challenge_method,
            "expires_at": utc_now() + timedelta(
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
        },
    )

    return _redirect_with_params(
        body.redirect_uri,
        code=raw_code,
        state=body.state or "",
    )


# ============================================================
# TOKEN ENDPOINT
# ============================================================

@app.post("/oauth/token")
async def oauth_token(
    body: OAuthTokenBody,
) -> JSONResponse:
    await _cleanup_oauth()
    db = get_db()

    if body.grant_type == "authorization_code":
        if not body.code:
            raise HTTPException(
                status_code=400,
                detail="Authorization code is required.",
            )

        code_record = await db.mcp_oauth_codes.find_one_and_delete(
            {
                "code_hash": _hash(body.code),
                "client_id": body.client_id,
            }
        )

        if not code_record:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired authorization code.",
            )

        if body.redirect_uri and body.redirect_uri != code_record.get(
            "redirect_uri"
        ):
            raise HTTPException(
                status_code=400,
                detail="OAuth redirect URI mismatch.",
            )

        challenge = code_record.get(
            "code_challenge"
        )

        if challenge:
            if not body.code_verifier:
                raise HTTPException(
                    status_code=400,
                    detail="PKCE code_verifier is required.",
                )

            method = code_record.get(
                "code_challenge_method"
            )

            if method not in {None, "", "S256"}:
                raise HTTPException(
                    status_code=400,
                    detail="Only S256 PKCE is supported.",
                )

            if not secrets.compare_digest(
                _pkce_s256(body.code_verifier),
                challenge,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="PKCE verification failed.",
                )

        raw_access_token = (
            f"umon_mcp_{secrets.token_urlsafe(40)}"
        )
        raw_refresh_token = (
            f"umon_refresh_{secrets.token_urlsafe(40)}"
        )

        await db.mcp_oauth_tokens.insert_one(
            {
                "_id": _hash(raw_access_token),
                "token_hash": _hash(raw_access_token),
                "client_id": code_record["client_id"],
                "clerk_user_id": code_record["clerk_user_id"],
                "scope": code_record.get("scope", MCP_SCOPE),
                "expires_at": utc_now() + timedelta(
                    seconds=OAUTH_ACCESS_TTL_SECONDS
                ),
                "created_at": utc_now(),
            }
        )

        await db.mcp_oauth_refresh_tokens.insert_one(
            {
                "_id": _hash(raw_refresh_token),
                "token_hash": _hash(raw_refresh_token),
                "client_id": code_record["client_id"],
                "clerk_user_id": code_record["clerk_user_id"],
                "scope": code_record.get("scope", MCP_SCOPE),
                "expires_at": utc_now() + timedelta(
                    seconds=OAUTH_REFRESH_TTL_SECONDS
                ),
                "created_at": utc_now(),
            }
        )

        await audit(
            owner_clerk_user_id=code_record["clerk_user_id"],
            action="MCP_ACCESS_TOKEN_ISSUED",
            result="SUCCESS",
            metadata={
                "client_id": code_record["client_id"],
                "scope": code_record.get("scope", MCP_SCOPE),
            },
        )

        return JSONResponse(
            {
                "access_token": raw_access_token,
                "token_type": "Bearer",
                "expires_in": OAUTH_ACCESS_TTL_SECONDS,
                "refresh_token": raw_refresh_token,
                "scope": code_record.get(
                    "scope",
                    MCP_SCOPE,
                ),
            }
        )

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

        expires_at = refresh.get("expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= utc_now():
            raise HTTPException(
                status_code=400,
                detail="Refresh token expired.",
            )

        raw_access_token = (
            f"umon_mcp_{secrets.token_urlsafe(40)}"
        )

        await db.mcp_oauth_tokens.insert_one(
            {
                "_id": _hash(raw_access_token),
                "token_hash": _hash(raw_access_token),
                "client_id": refresh["client_id"],
                "clerk_user_id": refresh["clerk_user_id"],
                "scope": refresh.get("scope", MCP_SCOPE),
                "expires_at": utc_now() + timedelta(
                    seconds=OAUTH_ACCESS_TTL_SECONDS
                ),
                "created_at": utc_now(),
            }
        )

        return JSONResponse(
            {
                "access_token": raw_access_token,
                "token_type": "Bearer",
                "expires_in": OAUTH_ACCESS_TTL_SECONDS,
                "scope": refresh.get("scope", MCP_SCOPE),
            }
        )

    raise HTTPException(
        status_code=400,
        detail="Unsupported grant_type.",
    )


# ============================================================
# MCP STREAMABLE HTTP
# ============================================================


def _transport_host_values() -> list[str]:
    parsed = urlparse(MCP_PUBLIC_URL)
    host = parsed.hostname or "localhost"
    netloc = parsed.netloc or "localhost:8002"

    values = {
        netloc,
        host,
        "localhost:8002",
        "127.0.0.1:8002",
    }

    if parsed.port:
        values.add(f"{host}:{parsed.port}")

    return sorted(values)


transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=_transport_host_values(),
    allowed_origins=[
        FRONTEND_URL,
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
