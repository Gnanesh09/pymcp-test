from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from pymongo import ReturnDocument

from .config import settings
from .db import get_db, utc_now
from .models import public_agent, public_product
from .policies import (
    commit_agent_balance,
    evaluate_purchase,
    release_agent_balance,
    reserve_agent_balance,
)


async def audit(
    *,
    owner_clerk_user_id: str | None,
    action: str,
    result: str,
    agent_id: str | None = None,
    amount_paise: int | None = None,
    reason: Any = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    db = get_db()
    event_id = f"evt_{uuid.uuid4().hex}"

    await db.audit_events.insert_one(
        {
            "_id": event_id,
            "owner_clerk_user_id": owner_clerk_user_id,
            "agent_id": agent_id,
            "action": action,
            "result": result,
            "amount_paise": amount_paise,
            "reason": reason,
            "metadata": metadata or {},
            "created_at": utc_now(),
        }
    )

    return event_id


async def create_agent(
    *,
    owner_clerk_user_id: str,
    name: str,
    description: str | None,
    max_transaction_paise: int,
    daily_limit_paise: int,
    auto_purchase: bool,
    allowed_categories: list[str],
    blocked_categories: list[str],
) -> dict[str, Any]:
    db = get_db()
    agent_id = f"agt_{uuid.uuid4().hex}"

    now = utc_now()

    agent = {
        "_id": agent_id,
        "owner_clerk_user_id": owner_clerk_user_id,
        "merchant_id": settings.merchant_id,
        "name": name,
        "description": description,
        "status": "ACTIVE",
        "balance_available_paise": 0,
        "balance_reserved_paise": 0,
        "spent_today_paise": 0,
        "lifetime_funded_paise": 0,
        "lifetime_spent_paise": 0,
        "policy": {
            "max_transaction_paise": max_transaction_paise,
            "daily_limit_paise": daily_limit_paise,
            "auto_purchase": auto_purchase,
            "allowed_categories": [
                x.strip().lower() for x in allowed_categories
            ],
            "blocked_categories": [
                x.strip().lower() for x in blocked_categories
            ],
        },
        "created_at": now,
        "updated_at": now,
    }

    await db.agents.insert_one(agent)

    await audit(
        owner_clerk_user_id=owner_clerk_user_id,
        action="AGENT_CREATED",
        result="SUCCESS",
        agent_id=agent_id,
        metadata={"name": name},
    )

    return public_agent(agent)


async def get_owned_agent(
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any] | None:
    db = get_db()
    return await db.agents.find_one(
        {
            "_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
        }
    )


async def search_products(
    query: str,
    category: str | None,
    max_price_paise: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    db = get_db()

    terms = [
        x.strip().lower()
        for x in query.split()
        if x.strip()
    ]

    docs = await db.products.find(
        {
            "merchant_id": settings.merchant_id,
            "active": True,
        }
    ).to_list(length=None)

    matches: list[tuple[int, float, int, dict[str, Any]]] = []

    for p in docs:
        if category and p["category"].lower() != category.lower():
            continue
        if max_price_paise is not None and p["price_paise"] > max_price_paise:
            continue

        searchable = " ".join(
            [
                p["name"],
                p["brand"],
                p["category"],
                p["description"],
                *p.get("tags", []),
            ]
        ).lower()

        score = sum(1 for term in terms if term in searchable)

        if score:
            matches.append(
                (
                    score,
                    float(p.get("rating", 0)),
                    int(p["price_paise"]),
                    p,
                )
            )

    matches.sort(key=lambda x: (-x[0], -x[1], x[2]))

    return [public_product(x[3]) for x in matches[: max(1, min(limit, 50))]]


async def get_recommendations(
    product_id: str,
) -> list[dict[str, Any]]:
    db = get_db()

    product = await db.products.find_one(
        {"_id": product_id, "merchant_id": settings.merchant_id}
    )

    if not product:
        return []

    ids = product.get("cross_sell_ids", [])
    if not ids:
        return []

    docs = await db.products.find(
        {
            "_id": {"$in": ids},
            "merchant_id": settings.merchant_id,
            "active": True,
        }
    ).to_list(length=None)

    return [
        {
            **public_product(p),
            "recommendation_type": "CROSS_SELL",
            "reason": f"Often useful with {product['name']}.",
        }
        for p in docs
    ]


async def build_cart(
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any]:
    db = get_db()

    cart = await db.carts.find_one(
        {
            "owner_clerk_user_id": owner_clerk_user_id,
            "agent_id": agent_id,
            "status": "ACTIVE",
        }
    )

    if not cart:
        cart = {
            "_id": f"cart_{uuid.uuid4().hex}",
            "owner_clerk_user_id": owner_clerk_user_id,
            "agent_id": agent_id,
            "merchant_id": settings.merchant_id,
            "items": [],
            "status": "ACTIVE",
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        await db.carts.insert_one(cart)

    return cart


async def add_to_cart(
    owner_clerk_user_id: str,
    agent_id: str,
    product_id: str,
    quantity: int,
) -> dict[str, Any]:
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    db = get_db()

    await get_owned_agent(owner_clerk_user_id, agent_id) or (
        (_ for _ in ()).throw(ValueError("Agent not found."))
    )

    product = await db.products.find_one(
        {
            "_id": product_id,
            "merchant_id": settings.merchant_id,
            "active": True,
        }
    )

    if not product:
        raise ValueError("Product not found.")

    if int(product["stock"]) < quantity:
        raise ValueError(
            f"Only {product['stock']} units of {product['name']} are available."
        )

    cart = await build_cart(owner_clerk_user_id, agent_id)
    items = cart.get("items", [])

    found = False
    for item in items:
        if item["product_id"] == product_id:
            new_qty = int(item["quantity"]) + quantity
            if int(product["stock"]) < new_qty:
                raise ValueError(
                    f"Only {product['stock']} units of {product['name']} are available."
                )
            item["quantity"] = new_qty
            item["unit_price_paise"] = int(product["price_paise"])
            item["line_total_paise"] = (
                item["quantity"] * item["unit_price_paise"]
            )
            found = True
            break

    if not found:
        items.append(
            {
                "product_id": product_id,
                "name": product["name"],
                "category": product["category"],
                "quantity": quantity,
                "unit_price_paise": int(product["price_paise"]),
                "line_total_paise": int(product["price_paise"]) * quantity,
                "image": product["image"],
            }
        )

    subtotal = sum(x["line_total_paise"] for x in items)
    delivery = 3900 if 0 < subtotal < 49900 else 0

    cart.update(
        {
            "items": items,
            "subtotal_paise": subtotal,
            "delivery_fee_paise": delivery,
            "total_paise": subtotal + delivery,
            "updated_at": utc_now(),
        }
    )

    await db.carts.replace_one({"_id": cart["_id"]}, cart)

    return cart



async def get_cart(
    *,
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any]:
    cart = await build_cart(owner_clerk_user_id, agent_id)
    return cart


async def update_cart_item(
    *,
    owner_clerk_user_id: str,
    agent_id: str,
    product_id: str,
    quantity: int,
) -> dict[str, Any]:
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    db = get_db()
    cart = await build_cart(owner_clerk_user_id, agent_id)

    target = next(
        (x for x in cart.get("items", []) if x["product_id"] == product_id),
        None,
    )
    if not target:
        raise ValueError("Product is not in the cart.")

    product = await db.products.find_one({
        "_id": product_id,
        "merchant_id": settings.merchant_id,
        "active": True,
    })
    if not product:
        raise ValueError("Product is no longer available.")
    if int(product["stock"]) < quantity:
        raise ValueError(
            f"Only {product['stock']} units of {product['name']} are available."
        )

    target["quantity"] = quantity
    target["unit_price_paise"] = int(product["price_paise"])
    target["line_total_paise"] = quantity * int(product["price_paise"])
    target["name"] = product["name"]
    target["category"] = product["category"]
    target["image"] = product["image"]

    subtotal = sum(x["line_total_paise"] for x in cart["items"])
    delivery = 3900 if 0 < subtotal < 49900 else 0
    cart.update({
        "subtotal_paise": subtotal,
        "delivery_fee_paise": delivery,
        "total_paise": subtotal + delivery,
        "updated_at": utc_now(),
    })
    await db.carts.replace_one({"_id": cart["_id"]}, cart)
    return cart


async def remove_cart_item(
    *,
    owner_clerk_user_id: str,
    agent_id: str,
    product_id: str,
) -> dict[str, Any]:
    db = get_db()
    cart = await build_cart(owner_clerk_user_id, agent_id)
    original = len(cart.get("items", []))
    items = [x for x in cart.get("items", []) if x["product_id"] != product_id]
    if len(items) == original:
        raise ValueError("Product is not in the cart.")

    subtotal = sum(x["line_total_paise"] for x in items)
    delivery = 3900 if 0 < subtotal < 49900 else 0
    cart.update({
        "items": items,
        "subtotal_paise": subtotal,
        "delivery_fee_paise": delivery,
        "total_paise": subtotal + delivery,
        "updated_at": utc_now(),
    })
    await db.carts.replace_one({"_id": cart["_id"]}, cart)
    return cart


async def clear_cart(
    *,
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any]:
    db = get_db()
    cart = await build_cart(owner_clerk_user_id, agent_id)
    cart.update({
        "items": [],
        "subtotal_paise": 0,
        "delivery_fee_paise": 0,
        "total_paise": 0,
        "updated_at": utc_now(),
    })
    await db.carts.replace_one({"_id": cart["_id"]}, cart)
    return cart


async def create_agent_funding_order(
    owner_clerk_user_id: str,
    agent_id: str,
    amount_paise: int,
) -> dict[str, Any]:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise ValueError("Razorpay credentials are not configured.")

    if amount_paise < 100:
        raise ValueError("Minimum funding amount is ₹1.")

    db = get_db()
    agent = await get_owned_agent(owner_clerk_user_id, agent_id)

    if not agent:
        raise ValueError("Agent not found.")

    import httpx

    receipt = f"umon_fund_{uuid.uuid4().hex[:20]}"

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.razorpay.com/v1/orders",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json={
                "amount": amount_paise,
                "currency": settings.razorpay_currency,
                "receipt": receipt,
                "notes": {
                    "type": "agent_funding",
                    "agent_id": agent_id,
                    "owner_clerk_user_id": owner_clerk_user_id,
                },
            },
        )

    response.raise_for_status()
    data = response.json()

    payment_id = f"fund_{uuid.uuid4().hex}"

    await db.payments.insert_one(
        {
            "_id": payment_id,
            "type": "AGENT_FUNDING",
            "status": "CREATED",
            "agent_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
            "amount_paise": amount_paise,
            "currency": settings.razorpay_currency,
            "razorpay_order_id": data["id"],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
    )

    await audit(
        owner_clerk_user_id=owner_clerk_user_id,
        action="AGENT_FUNDING_ORDER_CREATED",
        result="SUCCESS",
        agent_id=agent_id,
        amount_paise=amount_paise,
        metadata={"razorpay_order_id": data["id"]},
    )

    return {
        "payment_id": payment_id,
        "razorpay_order_id": data["id"],
        "amount_paise": amount_paise,
        "currency": settings.razorpay_currency,
        "key_id": settings.razorpay_key_id,
    }


async def verify_agent_funding(
    owner_clerk_user_id: str,
    agent_id: str,
    payment_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict[str, Any]:
    if not settings.razorpay_key_secret:
        raise ValueError("Razorpay credentials are not configured.")

    db = get_db()

    payment = await db.payments.find_one(
        {
            "_id": payment_id,
            "type": "AGENT_FUNDING",
            "agent_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
        }
    )

    if not payment:
        raise ValueError("Funding payment not found.")

    if payment.get("status") == "SUCCEEDED":
        agent = await get_owned_agent(owner_clerk_user_id, agent_id)
        return {
            "success": True,
            "status": "ALREADY_APPLIED",
            "agent": public_agent(agent),
        }

    import hmac
    import hashlib

    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, razorpay_signature):
        raise ValueError("Invalid Razorpay payment signature.")

    # Idempotent state transition.
    transitioned = await db.payments.find_one_and_update(
        {
            "_id": payment_id,
            "status": {"$ne": "SUCCEEDED"},
        },
        {
            "$set": {
                "status": "SUCCEEDED",
                "provider_payment_id": razorpay_payment_id,
                "updated_at": utc_now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not transitioned:
        agent = await get_owned_agent(owner_clerk_user_id, agent_id)
        return {
            "success": True,
            "status": "ALREADY_APPLIED",
            "agent": public_agent(agent),
        }

    amount_paise = int(payment["amount_paise"])
    ledger_id = f"funding:{razorpay_payment_id}"

    try:
        await db.ledger_entries.insert_one(
            {
                "_id": ledger_id,
                "entry_id": ledger_id,
                "agent_id": agent_id,
                "owner_clerk_user_id": owner_clerk_user_id,
                "type": "CREDIT",
                "amount_paise": amount_paise,
                "reference": razorpay_payment_id,
                "reason": "Verified Razorpay agent funding.",
                "created_at": utc_now(),
            }
        )
    except Exception:
        # If ledger already exists, treat this as idempotent.
        existing = await db.ledger_entries.find_one({"_id": ledger_id})
        if not existing:
            raise

    agent = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
        },
        {
            "$inc": {
                "balance_available_paise": amount_paise,
                "lifetime_funded_paise": amount_paise,
            },
            "$set": {"updated_at": utc_now()},
        },
        return_document=ReturnDocument.AFTER,
    )

    await audit(
        owner_clerk_user_id=owner_clerk_user_id,
        action="AGENT_FUNDED",
        result="SUCCESS",
        agent_id=agent_id,
        amount_paise=amount_paise,
        reason="Razorpay payment verified and ledger credited.",
        metadata={"razorpay_payment_id": razorpay_payment_id},
    )

    return {
        "success": True,
        "status": "FUNDED",
        "agent": public_agent(agent),
    }


async def checkout_with_agent_balance(
    owner_clerk_user_id: str,
    agent_id: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    db = get_db()

    agent = await get_owned_agent(owner_clerk_user_id, agent_id)
    if not agent:
        raise ValueError("Agent not found.")

    cart = await db.carts.find_one(
        {
            "owner_clerk_user_id": owner_clerk_user_id,
            "agent_id": agent_id,
            "status": "ACTIVE",
        }
    )

    if not cart or not cart.get("items"):
        raise ValueError("Cart is empty.")

    # Re-read current product prices and stock.
    current_items = []
    categories = []

    for item in cart["items"]:
        product = await db.products.find_one(
            {
                "_id": item["product_id"],
                "merchant_id": settings.merchant_id,
                "active": True,
            }
        )

        if not product:
            raise ValueError(
                f"Product {item['product_id']} is no longer available."
            )

        quantity = int(item["quantity"])
        if int(product["stock"]) < quantity:
            raise ValueError(
                f"Only {product['stock']} units of {product['name']} are available."
            )

        current_items.append(
            {
                "product_id": product["_id"],
                "name": product["name"],
                "category": product["category"],
                "quantity": quantity,
                "unit_price_paise": int(product["price_paise"]),
                "line_total_paise": int(product["price_paise"]) * quantity,
            }
        )
        categories.append(product["category"])

    subtotal = sum(x["line_total_paise"] for x in current_items)
    delivery = 3900 if 0 < subtotal < 49900 else 0
    total = subtotal + delivery

    merchant = await db.merchants.find_one(
        {"_id": settings.merchant_id}
    )
    if not merchant:
        raise ValueError("Merchant is unavailable.")

    policy_result = await evaluate_purchase(
        user_id=owner_clerk_user_id,
        agent=agent,
        amount_paise=total,
        categories=categories,
        merchant=merchant,
        confirmed=confirmed,
    )

    await audit(
        owner_clerk_user_id=owner_clerk_user_id,
        action="PURCHASE_POLICY_EVALUATED",
        result=policy_result["decision"],
        agent_id=agent_id,
        amount_paise=total,
        reason=policy_result.get("reason"),
        metadata={"code": policy_result.get("code")},
    )

    if policy_result["decision"] != "ALLOW":
        return {
            "success": False,
            "status": policy_result["decision"],
            "policy": policy_result,
            "total_paise": total,
            "total": round(total / 100, 2),
        }

    reservation_id = f"res_{uuid.uuid4().hex}"
    agent = await reserve_agent_balance(
        agent_id=agent_id,
        owner_clerk_user_id=owner_clerk_user_id,
        amount_paise=total,
        reservation_id=reservation_id,
    )

    await db.ledger_entries.insert_one(
        {
            "_id": reservation_id,
            "entry_id": reservation_id,
            "agent_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
            "type": "RESERVE",
            "amount_paise": total,
            "reference": reservation_id,
            "reason": "Reserved for agent checkout.",
            "created_at": utc_now(),
        }
    )

    # Reserve inventory atomically, product by product.
    changed = []

    try:
        for item in current_items:
            updated = await db.products.find_one_and_update(
                {
                    "_id": item["product_id"],
                    "stock": {"$gte": item["quantity"]},
                    "active": True,
                },
                {
                    "$inc": {"stock": -item["quantity"]}
                },
                return_document=ReturnDocument.AFTER,
            )

            if not updated:
                raise ValueError(
                    f"Inventory changed for {item['name']}."
                )

            changed.append(
                {
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                }
            )

        order_id = f"ord_{uuid.uuid4().hex}"

        await db.orders.insert_one(
            {
                "_id": order_id,
                "owner_clerk_user_id": owner_clerk_user_id,
                "agent_id": agent_id,
                "merchant_id": settings.merchant_id,
                "payment_method": "AGENT_BALANCE",
                "status": "CONFIRMED",
                "payment_status": "PAID",
                "amount_paise": total,
                "currency": "INR",
                "items": current_items,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )

        await commit_agent_balance(
            agent_id=agent_id,
            owner_clerk_user_id=owner_clerk_user_id,
            amount_paise=total,
        )

        await db.ledger_entries.insert_one(
            {
                "_id": f"debit:{order_id}",
                "entry_id": f"debit:{order_id}",
                "agent_id": agent_id,
                "owner_clerk_user_id": owner_clerk_user_id,
                "type": "DEBIT",
                "amount_paise": total,
                "reference": order_id,
                "reason": "Agent balance committed to merchant order.",
                "created_at": utc_now(),
            }
        )

        await db.carts.update_one(
            {"_id": cart["_id"]},
            {
                "$set": {
                    "status": "COMPLETED",
                    "updated_at": utc_now(),
                }
            },
        )

        final_agent = await get_owned_agent(
            owner_clerk_user_id,
            agent_id,
        )

        await audit(
            owner_clerk_user_id=owner_clerk_user_id,
            action="ORDER_COMPLETED",
            result="SUCCESS",
            agent_id=agent_id,
            amount_paise=total,
            reason="Purchase completed using funded agent balance.",
            metadata={"order_id": order_id},
        )

        return {
            "success": True,
            "status": "COMPLETED",
            "order": {
                "id": order_id,
                "amount_paise": total,
                "amount": round(total / 100, 2),
                "currency": "INR",
                "status": "CONFIRMED",
                "payment_method": "AGENT_BALANCE",
                "items": current_items,
            },
            "agent": public_agent(final_agent),
            "policy": policy_result,
        }

    except Exception as exc:
        for changed_item in changed:
            await db.products.update_one(
                {"_id": changed_item["product_id"]},
                {
                    "$inc": {
                        "stock": changed_item["quantity"]
                    }
                },
            )

        await release_agent_balance(
            agent_id=agent_id,
            owner_clerk_user_id=owner_clerk_user_id,
            amount_paise=total,
        )

        await audit(
            owner_clerk_user_id=owner_clerk_user_id,
            action="PURCHASE_FAILED",
            result="FAILED",
            agent_id=agent_id,
            amount_paise=total,
            reason=str(exc),
            metadata={"reservation_id": reservation_id},
        )

        raise
