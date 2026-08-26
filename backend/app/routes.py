from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from .db import get_db
from .config import settings
from .models import public_agent, public_product
from .security import get_current_user
from .services import (
    add_to_cart,
    audit,
    build_cart,
    checkout_with_agent_balance,
    create_agent,
    create_agent_funding_order,
    get_owned_agent,
    get_recommendations,
    search_products,
    verify_agent_funding,
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


class AgentPolicyPatch(BaseModel):
    max_transaction: float | None = Field(default=None, gt=0)
    daily_limit: float | None = Field(default=None, gt=0)
    auto_purchase: bool | None = None
    allowed_categories: list[str] | None = None
    blocked_categories: list[str] | None = None
    status: str | None = None


class FundingCreate(BaseModel):
    amount: float = Field(gt=0)


class FundingVerify(BaseModel):
    payment_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class AddCartItem(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)


class CheckoutRequest(BaseModel):
    agent_id: str


@router.get("/health")
async def health() -> dict[str, str]:
    db = get_db()
    await db.command("ping")
    return {"status": "ok"}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "success": True,
        "user": {
            "clerk_user_id": user["clerk_user_id"],
            "email": user.get("email"),
            "status": user["status"],
        },
    }


@router.post("/agents")
async def create_agent_route(
    body: AgentCreate,
    user=Depends(get_current_user),
):
    agent = await create_agent(
        owner_clerk_user_id=user["clerk_user_id"],
        name=body.name,
        description=body.description,
        max_transaction_paise=round(body.max_transaction * 100),
        daily_limit_paise=round(body.daily_limit * 100),
        auto_purchase=body.auto_purchase,
        allowed_categories=body.allowed_categories,
        blocked_categories=body.blocked_categories,
    )
    return {"success": True, "agent": agent}


@router.get("/agents")
async def list_agents(user=Depends(get_current_user)):
    db = get_db()
    docs = await db.agents.find(
        {"owner_clerk_user_id": user["clerk_user_id"]}
    ).sort("created_at", -1).to_list(length=100)

    return {
        "success": True,
        "agents": [public_agent(x) for x in docs],
    }


@router.get("/agents/{agent_id}")
async def get_agent_route(
    agent_id: str,
    user=Depends(get_current_user),
):
    agent = await get_owned_agent(
        user["clerk_user_id"],
        agent_id,
    )

    if not agent:
        raise HTTPException(404, "Agent not found.")

    return {"success": True, "agent": public_agent(agent)}


@router.patch("/agents/{agent_id}/policy")
async def update_agent_policy(
    agent_id: str,
    body: AgentPolicyPatch,
    user=Depends(get_current_user),
):
    db = get_db()

    agent = await get_owned_agent(
        user["clerk_user_id"],
        agent_id,
    )

    if not agent:
        raise HTTPException(404, "Agent not found.")

    update: dict[str, Any] = {}

    if body.max_transaction is not None:
        update["policy.max_transaction_paise"] = round(
            body.max_transaction * 100
        )

    if body.daily_limit is not None:
        update["policy.daily_limit_paise"] = round(
            body.daily_limit * 100
        )

    if body.auto_purchase is not None:
        update["policy.auto_purchase"] = body.auto_purchase

    if body.allowed_categories is not None:
        update["policy.allowed_categories"] = [
            x.strip().lower()
            for x in body.allowed_categories
        ]

    if body.blocked_categories is not None:
        update["policy.blocked_categories"] = [
            x.strip().lower()
            for x in body.blocked_categories
        ]

    if body.status is not None:
        if body.status not in {
            "ACTIVE",
            "DISABLED",
            "REVOKED",
        }:
            raise HTTPException(400, "Invalid agent status.")
        update["status"] = body.status

    update["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )

    updated = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id": user["clerk_user_id"],
        },
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )

    await audit(
        owner_clerk_user_id=user["clerk_user_id"],
        action="AGENT_POLICY_UPDATED",
        result="SUCCESS",
        agent_id=agent_id,
        metadata=update,
    )

    return {
        "success": True,
        "agent": public_agent(updated),
    }


@router.get("/agents/{agent_id}/balance")
async def agent_balance(
    agent_id: str,
    user=Depends(get_current_user),
):
    agent = await get_owned_agent(
        user["clerk_user_id"],
        agent_id,
    )

    if not agent:
        raise HTTPException(404, "Agent not found.")

    return {
        "success": True,
        "balance_available_paise": agent.get(
            "balance_available_paise", 0
        ),
        "balance_available": round(
            agent.get("balance_available_paise", 0) / 100,
            2,
        ),
        "balance_reserved_paise": agent.get(
            "balance_reserved_paise", 0
        ),
        "spent_today_paise": agent.get(
            "spent_today_paise", 0
        ),
        "lifetime_funded_paise": agent.get(
            "lifetime_funded_paise", 0
        ),
        "lifetime_spent_paise": agent.get(
            "lifetime_spent_paise", 0
        ),
    }


@router.post("/agents/{agent_id}/funding-order")
async def funding_order(
    agent_id: str,
    body: FundingCreate,
    user=Depends(get_current_user),
):
    try:
        result = await create_agent_funding_order(
            owner_clerk_user_id=user["clerk_user_id"],
            agent_id=agent_id,
            amount_paise=round(body.amount * 100),
        )
        return {"success": True, **result}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/agents/{agent_id}/funding/verify")
async def funding_verify(
    agent_id: str,
    body: FundingVerify,
    user=Depends(get_current_user),
):
    try:
        return await verify_agent_funding(
            owner_clerk_user_id=user["clerk_user_id"],
            agent_id=agent_id,
            payment_id=body.payment_id,
            razorpay_order_id=body.razorpay_order_id,
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_signature=body.razorpay_signature,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/products")
async def products(
    q: str = Query(default=""),
    category: str | None = None,
    max_price: float | None = None,
    limit: int = 20,
):
    results = await search_products(
        query=q,
        category=category,
        max_price_paise=(
            round(max_price * 100)
            if max_price is not None
            else None
        ),
        limit=limit,
    )
    return {
        "success": True,
        "products": results,
    }


@router.get("/products/{product_id}/recommendations")
async def product_recommendations(product_id: str):
    return {
        "success": True,
        "products": await get_recommendations(product_id),
    }


@router.get("/cart")
async def get_cart(
    agent_id: str,
    user=Depends(get_current_user),
):
    await get_owned_agent(
        user["clerk_user_id"],
        agent_id,
    ) or (_ for _ in ()).throw(
        HTTPException(404, "Agent not found.")
    )

    cart = await build_cart(
        user["clerk_user_id"],
        agent_id,
    )

    return {"success": True, "cart": cart}


@router.post("/cart/items")
async def cart_add(
    body: AddCartItem,
    agent_id: str,
    user=Depends(get_current_user),
):
    try:
        cart = await add_to_cart(
            owner_clerk_user_id=user["clerk_user_id"],
            agent_id=agent_id,
            product_id=body.product_id,
            quantity=body.quantity,
        )

        await audit(
            owner_clerk_user_id=user["clerk_user_id"],
            action="CART_ITEM_ADDED",
            result="SUCCESS",
            agent_id=agent_id,
            metadata={
                "product_id": body.product_id,
                "quantity": body.quantity,
            },
        )

        return {"success": True, "cart": cart}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/checkout/agent-balance")
async def checkout_agent_balance(
    body: CheckoutRequest,
    user=Depends(get_current_user),
):
    try:
        return await checkout_with_agent_balance(
            owner_clerk_user_id=user["clerk_user_id"],
            agent_id=body.agent_id,
        )
    except (ValueError, HTTPException) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, str(exc)) from exc


@router.get("/orders")
async def list_orders(user=Depends(get_current_user)):
    db = get_db()
    orders = await db.orders.find(
        {"owner_clerk_user_id": user["clerk_user_id"]}
    ).sort("created_at", -1).limit(100).to_list(length=100)

    return {
        "success": True,
        "orders": [
            {
                "id": x["_id"],
                "status": x["status"],
                "payment_status": x["payment_status"],
                "amount": round(x["amount_paise"] / 100, 2),
                "amount_paise": x["amount_paise"],
                "items": x["items"],
                "created_at": x["created_at"],
            }
            for x in orders
        ],
    }


@router.get("/audit")
async def audit_events(
    agent_id: str | None = None,
    user=Depends(get_current_user),
):
    db = get_db()

    query = {
        "owner_clerk_user_id": user["clerk_user_id"]
    }
    if agent_id:
        query["agent_id"] = agent_id

    events = await db.audit_events.find(
        query
    ).sort("created_at", -1).limit(100).to_list(length=100)

    return {
        "success": True,
        "events": [
            {
                "id": x["_id"],
                "action": x["action"],
                "result": x["result"],
                "agent_id": x.get("agent_id"),
                "amount_paise": x.get("amount_paise"),
                "reason": x.get("reason"),
                "metadata": x.get("metadata", {}),
                "created_at": x["created_at"],
            }
            for x in events
        ],
    }


@router.post("/payments/webhook")
async def razorpay_webhook(request: Request):
    # Webhook verification is intentionally isolated here.
    # Wire this with RAZORPAY_WEBHOOK_SECRET before enabling
    # production-style webhook processing.
    if not settings.razorpay_webhook_secret:
        raise HTTPException(
            503,
            "Razorpay webhook secret is not configured.",
        )

    import hmac
    import hashlib

    payload = await request.body()
    signature = request.headers.get(
        "X-Razorpay-Signature",
        "",
    )

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid webhook signature.")

    # We deliberately don't mutate the agent balance here yet.
    # Funding is finalized by the provider-payment verification
    # endpoint, which is idempotent and bound to the user's agent.
    return {"success": True}
