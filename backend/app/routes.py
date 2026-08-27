from typing import Any
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .config import settings
from .db import get_db
from .models import public_agent
from .security import get_current_user
from .services import (
    add_to_cart,
    agent_stats,
    audit,
    checkout_with_agent_balance,
    clear_cart,
    create_agent,
    create_agent_funding_order,
    create_direct_razorpay_order,
    get_cart,
    get_owned_agent,
    get_recommendations,
    remove_cart_item,
    revoke_agent,
    search_products,
    update_agent,
    update_agent_policy,
    update_cart_item,
    verify_agent_funding,
    verify_direct_razorpay_order,
)

router = APIRouter()


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    max_transaction: float = Field(gt=0)
    daily_limit: float = Field(gt=0)
    auto_purchase: bool = False
    allowed_categories: list[str] = []
    blocked_categories: list[str] = []


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class AgentPolicyPatch(BaseModel):
    max_transaction: float | None = Field(default=None, gt=0)
    daily_limit: float | None = Field(default=None, gt=0)
    auto_purchase: bool | None = None
    allowed_categories: list[str] | None = None
    blocked_categories: list[str] | None = None


class AgentStatusPatch(BaseModel):
    status: str


class FundingCreate(BaseModel):
    amount: float = Field(gt=0)


class FundingVerify(BaseModel):
    payment_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class CartItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class AgentCheckoutRequest(BaseModel):
    agent_id: str
    confirmed: bool = False


class DirectPaymentVerify(BaseModel):
    payment_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.get("/health")
async def health() -> dict[str, str]:
    await get_db().command("ping")
    return {"status": "ok"}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"success": True, "user": {"clerk_user_id": user["clerk_user_id"], "email": user.get("email"), "status": user["status"]}}


# ----------------------------- AGENTS -----------------------------

@router.post("/agents")
async def create_agent_route(body: AgentCreate, user=Depends(get_current_user)):
    return {"success": True, "agent": await create_agent(
        owner_clerk_user_id=user["clerk_user_id"],
        name=body.name,
        description=body.description,
        max_transaction_paise=round(body.max_transaction * 100),
        daily_limit_paise=round(body.daily_limit * 100),
        auto_purchase=body.auto_purchase,
        allowed_categories=body.allowed_categories,
        blocked_categories=body.blocked_categories,
    )}


@router.get("/agents")
async def list_agents(user=Depends(get_current_user)):
    docs = await get_db().agents.find({"owner_clerk_user_id": user["clerk_user_id"]}).sort("created_at", -1).to_list(length=100)
    return {"success": True, "agents": [public_agent(x) for x in docs]}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, user=Depends(get_current_user)):
    agent = await get_owned_agent(user["clerk_user_id"], agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found.")
    return {"success": True, "agent": public_agent(agent)}


@router.patch("/agents/{agent_id}")
async def patch_agent(agent_id: str, body: AgentUpdate, user=Depends(get_current_user)):
    try:
        return {"success": True, "agent": await update_agent(owner_clerk_user_id=user["clerk_user_id"], agent_id=agent_id, name=body.name, description=body.description)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, user=Depends(get_current_user)):
    try:
        return {"success": True, "agent": await revoke_agent(user["clerk_user_id"], agent_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/agents/{agent_id}/status")
async def agent_status(agent_id: str, body: AgentStatusPatch, user=Depends(get_current_user)):
    try:
        return {"success": True, "agent": await update_agent(owner_clerk_user_id=user["clerk_user_id"], agent_id=agent_id, status=body.status)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/agents/{agent_id}/policy")
async def patch_policy(agent_id: str, body: AgentPolicyPatch, user=Depends(get_current_user)):
    try:
        return {"success": True, "agent": await update_agent_policy(owner_clerk_user_id=user["clerk_user_id"], agent_id=agent_id, **body.model_dump(exclude_none=True))}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/agents/{agent_id}/stats")
async def agent_stats_route(agent_id: str, user=Depends(get_current_user)):
    try:
        return {"success": True, **await agent_stats(user["clerk_user_id"], agent_id)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/agents/{agent_id}/balance")
async def agent_balance(agent_id: str, user=Depends(get_current_user)):
    try:
        stats = await agent_stats(user["clerk_user_id"], agent_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    agent = stats["agent"]
    return {"success": True, "balance_available_paise": agent["balance_available_paise"], "balance_available": agent["balance_available"], "balance_reserved_paise": agent["balance_reserved_paise"], "spent_today_paise": stats["spent_today_paise"], "spent_this_month_paise": stats["spent_this_month_paise"]}


@router.post("/agents/{agent_id}/funding-order")
async def funding_order(agent_id: str, body: FundingCreate, user=Depends(get_current_user)):
    try:
        return {"success": True, **await create_agent_funding_order(user["clerk_user_id"], agent_id, round(body.amount * 100))}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/agents/{agent_id}/funding/verify")
async def funding_verify(agent_id: str, body: FundingVerify, user=Depends(get_current_user)):
    try:
        return await verify_agent_funding(user["clerk_user_id"], agent_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ----------------------------- CATALOG -----------------------------

@router.get("/products")
async def products(q: str = Query(default=""), category: str | None = None, max_price: float | None = None, limit: int = 20):
    return {"success": True, "products": await search_products(q, category, round(max_price * 100) if max_price is not None else None, limit)}


@router.get("/products/{product_id}/recommendations")
async def recommendations(product_id: str):
    return {"success": True, "products": await get_recommendations(product_id)}


# ----------------------------- SINGLE CART -----------------------------

@router.get("/cart")
async def current_cart(user=Depends(get_current_user)):
    return {"success": True, "cart": await get_cart(user["clerk_user_id"])}


@router.post("/cart/items")
async def add_cart(body: CartItemCreate, user=Depends(get_current_user)):
    try:
        cart = await add_to_cart(user["clerk_user_id"], body.product_id, body.quantity)
        await audit(owner_clerk_user_id=user["clerk_user_id"], action="CART_ITEM_ADDED", result="SUCCESS", metadata={"product_id": body.product_id, "quantity": body.quantity})
        return {"success": True, "cart": cart}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/cart/items/{product_id}")
async def update_cart(product_id: str, body: CartItemUpdate, user=Depends(get_current_user)):
    try:
        return {"success": True, "cart": await update_cart_item(user["clerk_user_id"], product_id, body.quantity)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/cart/items/{product_id}")
async def remove_cart(product_id: str, user=Depends(get_current_user)):
    try:
        return {"success": True, "cart": await remove_cart_item(user["clerk_user_id"], product_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/cart/clear")
async def clear_cart_route(user=Depends(get_current_user)):
    return {"success": True, "cart": await clear_cart(user["clerk_user_id"])}


# ----------------------------- CHECKOUT -----------------------------

@router.post("/checkout/agent-balance")
async def agent_balance_checkout(body: AgentCheckoutRequest, user=Depends(get_current_user)):
    try:
        return await checkout_with_agent_balance(user["clerk_user_id"], body.agent_id, body.confirmed)
    except (ValueError, HTTPException) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, str(exc)) from exc


@router.post("/checkout/razorpay")
async def razorpay_checkout(user=Depends(get_current_user)):
    try:
        return {"success": True, **await create_direct_razorpay_order(user["clerk_user_id"])}
    except (ValueError, HTTPException) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, str(exc)) from exc


@router.post("/checkout/razorpay/verify")
async def razorpay_verify(body: DirectPaymentVerify, user=Depends(get_current_user)):
    try:
        return await verify_direct_razorpay_order(user["clerk_user_id"], **body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ----------------------------- ORDERS -----------------------------

@router.get("/orders")
async def list_orders(user=Depends(get_current_user)):
    docs = await get_db().orders.find({"owner_clerk_user_id": user["clerk_user_id"]}).sort("created_at", -1).limit(100).to_list(length=100)
    return {"success": True, "orders": [{"id":x["_id"],"status":x["status"],"payment_status":x["payment_status"],"payment_method":x.get("payment_method"),"agent_id":x.get("agent_id"),"amount_paise":x["amount_paise"],"amount":round(x["amount_paise"]/100,2),"items":x["items"],"created_at":x["created_at"]} for x in docs]}


@router.get("/orders/{order_id}")
async def order_detail(order_id: str, user=Depends(get_current_user)):
    order = await get_db().orders.find_one({"_id":order_id,"owner_clerk_user_id":user["clerk_user_id"]})
    if not order: raise HTTPException(404,"Order not found.")
    return {"success":True,"order":order}


# ----------------------------- AUDIT -----------------------------

@router.get("/audit")
async def audit_events(agent_id: str | None = None, user=Depends(get_current_user)):
    query: dict[str, Any] = {"owner_clerk_user_id": user["clerk_user_id"]}
    if agent_id: query["agent_id"] = agent_id
    docs = await get_db().audit_events.find(query).sort("created_at", -1).limit(200).to_list(length=200)
    return {"success":True,"events":[{"id":x["_id"],"action":x["action"],"result":x["result"],"agent_id":x.get("agent_id"),"amount_paise":x.get("amount_paise"),"reason":x.get("reason"),"metadata":x.get("metadata",{}),"created_at":x["created_at"]} for x in docs]}


# ----------------------------- RAZORPAY WEBHOOK -----------------------------

@router.post("/payments/webhook")
async def razorpay_webhook(request: Request):
    if not settings.razorpay_webhook_secret:
        raise HTTPException(503,"Razorpay webhook secret is not configured.")
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401,"Invalid webhook signature.")
    await audit(owner_clerk_user_id=None, action="RAZORPAY_WEBHOOK_RECEIVED", result="SUCCESS")
    return {"success":True}
