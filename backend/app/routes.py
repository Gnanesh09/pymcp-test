from typing import Any
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
# Add imports to your existing backend/app/routes.py


from .agent_graph import run_multi_agent, public_result


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
    admin_audit,
        admin_create_product,
        admin_dashboard,
        admin_delete_product,
        admin_get_merchant,
        admin_list_agents,
        admin_list_orders,
        admin_list_payments,
        admin_list_products,
        admin_list_users,
        admin_update_merchant,
        admin_update_product,
)

router = APIRouter()
class AgentCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=80,
    )

    description: str | None = Field(
        default=None,
        max_length=500,
    )

    max_transaction: float = Field(
        gt=0,
    )

    daily_limit: float = Field(
        gt=0,
    )

    auto_purchase: bool = False

    category_mode: str = Field(
        default="ALL",
    )

    allowed_categories: list[str] = Field(
        default_factory=list,
    )

    blocked_categories: list[str] = Field(
        default_factory=list,
    )


class AgentUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=80,
    )

    description: str | None = Field(
        default=None,
        max_length=500,
    )

class AgentPolicyPatch(BaseModel):
    max_transaction: float | None = Field(
        default=None,
        gt=0,
    )

    daily_limit: float | None = Field(
        default=None,
        gt=0,
    )

    auto_purchase: bool | None = None

    category_mode: str | None = Field(
        default=None,
    )

    allowed_categories: list[str] | None = Field(
        default=None,
    )

    blocked_categories: list[str] | None = Field(
        default=None,
    )

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
async def create_agent_route(
    body: AgentCreate,
    user=Depends(get_current_user),
):
    category_mode = (
        body.category_mode
        .strip()
        .upper()
    )

    if category_mode not in {
        "ALL",
        "SELECTED",
    }:
        raise HTTPException(
            400,
            "category_mode must be ALL or SELECTED.",
        )

    if (
        category_mode == "SELECTED"
        and not body.allowed_categories
    ):
        raise HTTPException(
            400,
            "Select at least one category or choose Everything.",
        )

    return {
        "success": True,
        "agent": await create_agent(
            owner_clerk_user_id=
                user["clerk_user_id"],

            name=
                body.name,

            description=
                body.description,

            max_transaction_paise=
                round(
                    body.max_transaction
                    * 100
                ),

            daily_limit_paise=
                round(
                    body.daily_limit
                    * 100
                ),

            auto_purchase=
                body.auto_purchase,

            category_mode=
                category_mode,

            allowed_categories=
                body.allowed_categories,

            blocked_categories=
                body.blocked_categories,
        ),
    }
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
async def patch_agent_policy(
    agent_id: str,
    body: AgentPolicyPatch,
    user=Depends(get_current_user),
):
    try:
        updated_agent = await update_agent_policy(
            owner_clerk_user_id=user["clerk_user_id"],
            agent_id=agent_id,

            max_transaction=body.max_transaction,
            daily_limit=body.daily_limit,
            auto_purchase=body.auto_purchase,

            category_mode=body.category_mode,

            allowed_categories=body.allowed_categories,
            blocked_categories=body.blocked_categories,
        )

        return {
            "success": True,
            "agent": updated_agent,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

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



# ============================================================
# DEV ADMIN
# ============================================================
#
# NO ADMIN AUTHENTICATION YET.
# LOCAL / BUILDATHON USE ONLY.
#
# DO NOT expose these endpoints publicly.
# ============================================================


class AdminMerchantUpdate(BaseModel):
    name: str | None = None
    status: str | None = None

    ai_discovery: bool | None = None
    ai_purchasing: bool | None = None
    ai_checkout: bool | None = None

    recommendations_enabled: bool | None = None

    max_order_value: float | None = None

    allowed_categories: list[str] | None = None


class AdminProductCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=150,
    )

    brand: str = ""

    category: str = Field(
        min_length=1,
        max_length=80,
    )

    price: float = Field(
        gt=0,
    )

    mrp: float = Field(
        gt=0,
    )

    stock: int = Field(
        ge=0,
    )

    unit: str = ""

    description: str = ""

    image: str | None = None

    tags: list[str] = Field(
        default_factory=list,
    )


class AdminProductUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    category: str | None = None

    price: float | None = Field(
        default=None,
        gt=0,
    )

    mrp: float | None = Field(
        default=None,
        gt=0,
    )

    stock: int | None = Field(
        default=None,
        ge=0,
    )

    unit: str | None = None
    description: str | None = None
    image: str | None = None

    tags: list[str] | None = None

    active: bool | None = None


@router.get("/admin/dashboard")
async def admin_dashboard_route():
    return {
        "success": True,
        **await admin_dashboard(),
    }


@router.get("/admin/merchant")
async def admin_merchant_route():
    return {
        "success": True,
        "merchant":
            await admin_get_merchant(),
    }


@router.patch("/admin/merchant")
async def admin_merchant_update_route(
    body: AdminMerchantUpdate,
):
    try:
        merchant = await admin_update_merchant(
            name=body.name,
            status=body.status,
            ai_discovery=body.ai_discovery,
            ai_purchasing=body.ai_purchasing,
            ai_checkout=body.ai_checkout,
            recommendations_enabled=
                body.recommendations_enabled,
            max_order_value=
                body.max_order_value,
            allowed_categories=
                body.allowed_categories,
        )

        return {
            "success": True,
            "merchant":
                merchant,
        }

    except ValueError as exc:
        raise HTTPException(
            400,
            str(exc),
        ) from exc


@router.get("/admin/products")
async def admin_products_route(
    q: str = "",
    include_inactive: bool = True,
):
    return {
        "success": True,
        "products":
            await admin_list_products(
                query=q,
                include_inactive=
                    include_inactive,
            ),
    }


@router.post("/admin/products")
async def admin_create_product_route(
    body: AdminProductCreate,
):
    try:
        product = await admin_create_product(
            name=body.name,
            brand=body.brand,
            category=body.category,
            price_paise=
                round(
                    body.price * 100
                ),
            mrp_paise=
                round(
                    body.mrp * 100
                ),
            stock=body.stock,
            unit=body.unit,
            description=body.description,
            image=body.image,
            tags=body.tags,
        )

        return {
            "success": True,
            "product":
                product,
        }

    except ValueError as exc:
        raise HTTPException(
            400,
            str(exc),
        ) from exc


@router.patch(
    "/admin/products/{product_id}"
)
async def admin_update_product_route(
    product_id: str,
    body: AdminProductUpdate,
):
    try:
        product = await admin_update_product(
            product_id,

            name=body.name,
            brand=body.brand,
            category=body.category,

            price_paise=(
                round(
                    body.price * 100
                )
                if body.price is not None
                else None
            ),

            mrp_paise=(
                round(
                    body.mrp * 100
                )
                if body.mrp is not None
                else None
            ),

            stock=body.stock,
            unit=body.unit,
            description=body.description,
            image=body.image,
            tags=body.tags,
            active=body.active,
        )

        return {
            "success": True,
            "product":
                product,
        }

    except ValueError as exc:
        raise HTTPException(
            400,
            str(exc),
        ) from exc


@router.delete(
    "/admin/products/{product_id}"
)
async def admin_delete_product_route(
    product_id: str,
):
    try:
        product = await admin_delete_product(
            product_id
        )

        return {
            "success": True,
            "product":
                product,
        }

    except ValueError as exc:
        raise HTTPException(
            404,
            str(exc),
        ) from exc


@router.get("/admin/orders")
async def admin_orders_route(
    status: str | None = None,
    payment_status: str | None = None,
    limit: int = 200,
):
    return {
        "success": True,
        "orders":
            await admin_list_orders(
                status=status,
                payment_status=
                    payment_status,
                limit=limit,
            ),
    }


@router.get("/admin/payments")
async def admin_payments_route(
    status: str | None = None,
    payment_type: str | None = None,
    limit: int = 200,
):
    return {
        "success": True,
        "payments":
            await admin_list_payments(
                status=status,
                payment_type=
                    payment_type,
                limit=limit,
            ),
    }


@router.get("/admin/users")
async def admin_users_route(
    q: str = "",
    limit: int = 200,
):
    return {
        "success": True,
        "users":
            await admin_list_users(
                query=q,
                limit=limit,
            ),
    }


@router.get("/admin/agents")
async def admin_agents_route(
    status: str | None = None,
    limit: int = 200,
):
    return {
        "success": True,
        "agents":
            await admin_list_agents(
                status=status,
                limit=limit,
            ),
    }


@router.get("/admin/audit")
async def admin_audit_route(
    result: str | None = None,
    action: str | None = None,
    limit: int = 300,
):
    return {
        "success": True,
        "events":
            await admin_audit(
                result=result,
                action=action,
                limit=limit,
            ),
    }
    
    
    

# ============================================================
# REQUEST MODEL
# ============================================================

class AgentChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000,
    )

    selected_agent_id: str | None = None


# ============================================================
# POST /api/agent/chat
# ============================================================

@router.post("/agent/chat")
async def agent_chat(
    body: AgentChatRequest,
    user=Depends(get_current_user),
):
    """
    Run one ephemeral Umon multi-agent shopping interaction.

    The authenticated Clerk user is always taken from the backend session;
    the browser never supplies the user ID.

    This endpoint does NOT:
      - persist the conversation
      - add products to the cart
      - change agent balances
      - perform checkout
      - modify inventory

    It returns verified recommendations which the frontend can render and
    allow the user to add explicitly.
    """
    try:
        result = await run_multi_agent(
            user_id=user["clerk_user_id"],
            message=body.message,
            selected_agent_id=body.selected_agent_id,
        )

        return public_result(result)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        # Do not expose provider internals or credentials.
        raise HTTPException(
            status_code=502,
            detail=(
                "Umon AI could not complete this request. "
                "No purchase was made."
            ),
        ) from exc
