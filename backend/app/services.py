from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import uuid
from typing import Any

import httpx
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


# ============================================================
# GENERAL HELPERS
# ============================================================

def _cart_payload(
    cart: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Convert internal cart document into a safe API response.

    owner_clerk_user_id is intentionally removed from the
    response because it is an internal authorization field.
    """
    if not cart:
        return {
            "id": None,
            "merchant_id": settings.merchant_id,
            "items": [],
            "subtotal_paise": 0,
            "delivery_fee_paise": 0,
            "total_paise": 0,
            "currency": "INR",
            "status": "ACTIVE",
        }

    result = dict(cart)

    result["id"] = result.pop("_id", None)

    result.pop(
        "owner_clerk_user_id",
        None,
    )

    return result


def _money(paise: int) -> float:
    return round(int(paise) / 100, 2)


def _normalize_categories(
    values: list[str] | None,
) -> list[str]:
    if not values:
        return []

    return sorted(
        {
            str(value).strip().lower()
            for value in values
            if str(value).strip()
        }
    )


# ============================================================
# AUDIT
# ============================================================

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
    """
    Durable audit event.

    Never store:
      - passwords
      - Clerk tokens
      - MCP tokens
      - Razorpay secret
      - card information
      - CVV
    """
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


# ============================================================
# AGENTS
# ============================================================
async def create_agent(
    *,
    owner_clerk_user_id: str,
    name: str,
    description: str | None,
    max_transaction_paise: int,
    daily_limit_paise: int,
    auto_purchase: bool,
    category_mode: str = "ALL",
    allowed_categories: list[str] | None = None,
    blocked_categories: list[str] | None = None,
) -> dict[str, Any]:

    db = get_db()

    name = name.strip()

    if not name:
        raise ValueError(
            "Agent name is required."
        )

    if max_transaction_paise <= 0:
        raise ValueError(
            "Transaction limit must be greater than zero."
        )

    if daily_limit_paise <= 0:
        raise ValueError(
            "Daily limit must be greater than zero."
        )

    if max_transaction_paise > daily_limit_paise:
        raise ValueError(
            "Transaction limit cannot exceed daily limit."
        )

    category_mode = (
        str(category_mode)
        .strip()
        .upper()
    )

    if category_mode not in {
        "ALL",
        "SELECTED",
    }:
        raise ValueError(
            "category_mode must be ALL or SELECTED."
        )

    allowed = sorted(
        {
            str(value)
            .strip()
            .lower()
            for value in (
                allowed_categories
                or []
            )
            if str(value).strip()
        }
    )

    blocked = sorted(
        {
            str(value)
            .strip()
            .lower()
            for value in (
                blocked_categories
                or []
            )
            if str(value).strip()
        }
    )

    if (
        category_mode == "SELECTED"
        and not allowed
    ):
        raise ValueError(
            "Select at least one category."
        )

    overlap = sorted(
        set(allowed)
        & set(blocked)
    )

    if overlap:
        raise ValueError(
            "Category cannot be both allowed and blocked: "
            + ", ".join(overlap)
        )

    # ALL means allowed_categories is not restrictive.
    if category_mode == "ALL":
        allowed = []

    now = utc_now()

    agent = {
        "_id":
            f"agt_{uuid.uuid4().hex}",

        "owner_clerk_user_id":
            owner_clerk_user_id,

        "merchant_id":
            settings.merchant_id,

        "name":
            name,

        "description":
            (
                description.strip()
                if description
                else None
            ),

        "status":
            "ACTIVE",

        "balance_available_paise":
            0,

        "balance_reserved_paise":
            0,

        "lifetime_funded_paise":
            0,

        "lifetime_spent_paise":
            0,

        "funding_refs":
            [],

        "policy": {
            "max_transaction_paise":
                max_transaction_paise,

            "daily_limit_paise":
                daily_limit_paise,

            "auto_purchase":
                bool(auto_purchase),

            "category_mode":
                category_mode,

            "allowed_categories":
                allowed,

            "blocked_categories":
                blocked,
        },

        "created_at":
            now,

        "updated_at":
            now,
    }

    await db.agents.insert_one(
        agent
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "AGENT_CREATED",
        result=
            "SUCCESS",
        agent_id=
            agent["_id"],
        metadata={
            "name":
                name,
            "category_mode":
                category_mode,
        },
    )

    return public_agent(agent)

async def get_owned_agent(
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any] | None:
    """
    Never look up an agent by id alone.

    Ownership is always part of the query.
    """
    return await get_db().agents.find_one(
        {
            "_id": agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
        }
    )


async def update_agent(
    *,
    owner_clerk_user_id: str,
    agent_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    db = get_db()

    update: dict[str, Any] = {
        "updated_at": utc_now()
    }

    if name is not None:
        cleaned_name = name.strip()

        if not cleaned_name:
            raise ValueError(
                "Agent name cannot be empty."
            )

        update["name"] = cleaned_name

    if description is not None:
        update["description"] = (
            description.strip()
        )

    if status is not None:
        if status not in {
            "ACTIVE",
            "DISABLED",
            "REVOKED",
        }:
            raise ValueError(
                "Invalid agent status."
            )

        update["status"] = status

    agent = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
        },
        {
            "$set": update,
        },
        return_document=ReturnDocument.AFTER,
    )

    if not agent:
        raise ValueError(
            "Agent not found."
        )

    await audit(
        owner_clerk_user_id=owner_clerk_user_id,
        action="AGENT_UPDATED",
        result="SUCCESS",
        agent_id=agent_id,
        metadata={
            key: value
            for key, value in update.items()
            if key != "updated_at"
        },
    )

    return public_agent(agent)


async def revoke_agent(
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any]:
    return await update_agent(
        owner_clerk_user_id=
            owner_clerk_user_id,
        agent_id=agent_id,
        status="REVOKED",
    )
async def update_agent_policy(
    *,
    owner_clerk_user_id: str,
    agent_id: str,
    max_transaction: float | None = None,
    daily_limit: float | None = None,
    auto_purchase: bool | None = None,
    category_mode: str | None = None,
    allowed_categories: list[str] | None = None,
    blocked_categories: list[str] | None = None,
) -> dict[str, Any]:
    """
    Update an agent's purchasing policy.

    Policy updates are partial: omitted fields keep their current value.
    The final merged policy is validated before it is persisted.
    """

    db = get_db()

    agent = await get_owned_agent(
        owner_clerk_user_id,
        agent_id,
    )

    if not agent:
        raise ValueError("Agent not found.")

    current_policy = dict(
        agent.get("policy", {})
    )

    set_values: dict[str, Any] = {
        "updated_at": utc_now(),
    }

    # --------------------------------------------------------
    # Limits
    # --------------------------------------------------------

    if max_transaction is not None:
        value = float(max_transaction)

        if value <= 0:
            raise ValueError(
                "Transaction limit must be greater than zero."
            )

        set_values[
            "policy.max_transaction_paise"
        ] = round(value * 100)

    if daily_limit is not None:
        value = float(daily_limit)

        if value <= 0:
            raise ValueError(
                "Daily limit must be greater than zero."
            )

        set_values[
            "policy.daily_limit_paise"
        ] = round(value * 100)

    # --------------------------------------------------------
    # Autonomous purchasing
    # --------------------------------------------------------

    if auto_purchase is not None:
        set_values[
            "policy.auto_purchase"
        ] = bool(auto_purchase)

    # --------------------------------------------------------
    # Category mode
    # --------------------------------------------------------

    if category_mode is not None:
        mode = str(
            category_mode
        ).strip().upper()

        if mode not in {"ALL", "SELECTED"}:
            raise ValueError(
                "category_mode must be ALL or SELECTED."
            )

        set_values[
            "policy.category_mode"
        ] = mode

        # ALL means there is no allow-list restriction.
        # Explicit blocked categories may still apply.
        if mode == "ALL":
            set_values[
                "policy.allowed_categories"
            ] = []

    # --------------------------------------------------------
    # Allowed categories
    # --------------------------------------------------------

    if allowed_categories is not None:
        set_values[
            "policy.allowed_categories"
        ] = _normalize_categories(
            allowed_categories
        )

    # --------------------------------------------------------
    # Blocked categories
    # --------------------------------------------------------

    if blocked_categories is not None:
        set_values[
            "policy.blocked_categories"
        ] = _normalize_categories(
            blocked_categories
        )

    # --------------------------------------------------------
    # Validate final merged category policy
    # --------------------------------------------------------

    final_mode = str(
        set_values.get(
            "policy.category_mode",
            current_policy.get(
                "category_mode",
                "ALL",
            ),
        )
    ).strip().upper()

    final_allowed = set(
        _normalize_categories(
            list(
                set_values.get(
                    "policy.allowed_categories",
                    current_policy.get(
                        "allowed_categories",
                        [],
                    ),
                )
            )
        )
    )

    final_blocked = set(
        _normalize_categories(
            list(
                set_values.get(
                    "policy.blocked_categories",
                    current_policy.get(
                        "blocked_categories",
                        [],
                    ),
                )
            )
        )
    )

    if final_mode not in {"ALL", "SELECTED"}:
        raise ValueError(
            "Invalid category mode."
        )

    if (
        final_mode == "SELECTED"
        and not final_allowed
    ):
        raise ValueError(
            "Select at least one category."
        )

    overlap = sorted(
        final_allowed & final_blocked
    )

    if overlap:
        raise ValueError(
            "A category cannot be both allowed and blocked: "
            + ", ".join(overlap)
        )

    # --------------------------------------------------------
    # Validate final merged spending limits
    # --------------------------------------------------------

    final_max = int(
        set_values.get(
            "policy.max_transaction_paise",
            current_policy.get(
                "max_transaction_paise",
                0,
            ),
        )
    )

    final_daily = int(
        set_values.get(
            "policy.daily_limit_paise",
            current_policy.get(
                "daily_limit_paise",
                0,
            ),
        )
    )

    if final_max <= 0:
        raise ValueError(
            "Transaction limit must be greater than zero."
        )

    if final_daily <= 0:
        raise ValueError(
            "Daily limit must be greater than zero."
        )

    if final_max > final_daily:
        raise ValueError(
            "Transaction limit cannot exceed daily limit."
        )

    # --------------------------------------------------------
    # Persist policy
    # --------------------------------------------------------

    updated = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
        },
        {
            "$set": set_values,
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        raise ValueError("Agent not found.")

    # --------------------------------------------------------
    # Audit policy change
    # --------------------------------------------------------

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "AGENT_POLICY_UPDATED",
        result=
            "SUCCESS",
        agent_id=
            agent_id,
        metadata={
            "category_mode":
                final_mode,
            "allowed_categories":
                sorted(final_allowed),
            "blocked_categories":
                sorted(final_blocked),
            "max_transaction_paise":
                final_max,
            "daily_limit_paise":
                final_daily,
            "auto_purchase":
                set_values.get(
                    "policy.auto_purchase",
                    current_policy.get(
                        "auto_purchase",
                        False,
                    ),
                ),
        },
    )

    return public_agent(updated)

# ============================================================
# AGENT STATS
# ============================================================

async def agent_stats(
    owner_clerk_user_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """
    Full agent financial/control dashboard.

    Important PyMongo async detail:

        cursor = await collection.aggregate(...)
        rows = await cursor.to_list(...)

    In the installed async API, aggregate() itself is awaitable.
    """

    db = get_db()

    agent = await get_owned_agent(
        owner_clerk_user_id,
        agent_id,
    )

    if not agent:
        raise ValueError(
            "Agent not found."
        )

    now = datetime.now(
        timezone.utc
    )

    start_of_day = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    start_of_month = start_of_day.replace(
        day=1
    )

    ownership_match = {
        "agent_id": agent_id,
        "owner_clerk_user_id":
            owner_clerk_user_id,
        "type": "DEBIT",
    }

    # --------------------------------------------------------
    # Today
    # --------------------------------------------------------

    day_cursor = await db.ledger_entries.aggregate(
        [
            {
                "$match": {
                    **ownership_match,
                    "created_at": {
                        "$gte":
                            start_of_day,
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum":
                            "$amount_paise"
                    },
                }
            },
        ]
    )

    day = await day_cursor.to_list(
        length=1
    )

    # --------------------------------------------------------
    # Current month
    # --------------------------------------------------------

    month_cursor = await db.ledger_entries.aggregate(
        [
            {
                "$match": {
                    **ownership_match,
                    "created_at": {
                        "$gte":
                            start_of_month,
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum":
                            "$amount_paise"
                    },
                }
            },
        ]
    )

    month = await month_cursor.to_list(
        length=1
    )

    # --------------------------------------------------------
    # Recent ledger
    # --------------------------------------------------------

    recent = await (
        db.ledger_entries
        .find(
            {
                "agent_id":
                    agent_id,
                "owner_clerk_user_id":
                    owner_clerk_user_id,
            }
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(100)
        .to_list(
            length=100
        )
    )

    # --------------------------------------------------------
    # Agent orders
    # --------------------------------------------------------

    orders = await (
        db.orders
        .find(
            {
                "owner_clerk_user_id":
                    owner_clerk_user_id,
                "agent_id":
                    agent_id,
            }
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(100)
        .to_list(
            length=100
        )
    )

    # --------------------------------------------------------
    # Audit events for this agent
    # --------------------------------------------------------

    activity = await (
        db.audit_events
        .find(
            {
                "owner_clerk_user_id":
                    owner_clerk_user_id,
                "agent_id":
                    agent_id,
            }
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(100)
        .to_list(
            length=100
        )
    )

    spent_today_paise = (
        int(day[0]["total"])
        if day
        else 0
    )

    spent_this_month_paise = (
        int(month[0]["total"])
        if month
        else 0
    )

    lifetime_funded_paise = int(
        agent.get(
            "lifetime_funded_paise",
            0,
        )
    )

    lifetime_spent_paise = int(
        agent.get(
            "lifetime_spent_paise",
            0,
        )
    )

    available_paise = int(
        agent.get(
            "balance_available_paise",
            0,
        )
    )

    reserved_paise = int(
        agent.get(
            "balance_reserved_paise",
            0,
        )
    )

    policy = agent.get(
        "policy",
        {},
    )

    daily_limit_paise = int(
        policy.get(
            "daily_limit_paise",
            0,
        )
    )

    transaction_limit_paise = int(
        policy.get(
            "max_transaction_paise",
            0,
        )
    )

    daily_remaining_paise = max(
        0,
        daily_limit_paise
        - spent_today_paise,
    )

    return {
        "agent": public_agent(agent),

        "balance": {
            "available_paise":
                available_paise,
            "available":
                _money(
                    available_paise
                ),
            "reserved_paise":
                reserved_paise,
            "reserved":
                _money(
                    reserved_paise
                ),
        },

        "spending": {
            "today_paise":
                spent_today_paise,
            "today":
                _money(
                    spent_today_paise
                ),

            "daily_limit_paise":
                daily_limit_paise,
            "daily_limit":
                _money(
                    daily_limit_paise
                ),

            "daily_remaining_paise":
                daily_remaining_paise,
            "daily_remaining":
                _money(
                    daily_remaining_paise
                ),

            "this_month_paise":
                spent_this_month_paise,
            "this_month":
                _money(
                    spent_this_month_paise
                ),

            "lifetime_paise":
                lifetime_spent_paise,
            "lifetime":
                _money(
                    lifetime_spent_paise
                ),
        },

        "funding": {
            "lifetime_funded_paise":
                lifetime_funded_paise,
            "lifetime_funded":
                _money(
                    lifetime_funded_paise
                ),
        },

        "limits": {
            "transaction_paise":
                transaction_limit_paise,
            "transaction":
                _money(
                    transaction_limit_paise
                ),
        },

        "ledger": [
            {
                "id":
                    entry["_id"],
                "type":
                    entry.get(
                        "type"
                    ),
                "amount_paise":
                    entry.get(
                        "amount_paise",
                        0,
                    ),
                "amount":
                    _money(
                        entry.get(
                            "amount_paise",
                            0,
                        )
                    ),
                "reason":
                    entry.get(
                        "reason"
                    ),
                "reference":
                    entry.get(
                        "reference"
                    ),
                "created_at":
                    entry.get(
                        "created_at"
                    ),
            }
            for entry in recent
        ],

        "orders": [
            {
                "id":
                    order["_id"],
                "status":
                    order.get(
                        "status"
                    ),
                "payment_status":
                    order.get(
                        "payment_status"
                    ),
                "payment_method":
                    order.get(
                        "payment_method"
                    ),
                "amount_paise":
                    order.get(
                        "amount_paise",
                        0,
                    ),
                "amount":
                    _money(
                        order.get(
                            "amount_paise",
                            0,
                        )
                    ),
                "created_at":
                    order.get(
                        "created_at"
                    ),
            }
            for order in orders
        ],

        "activity": [
            {
                "id":
                    event["_id"],
                "action":
                    event.get(
                        "action"
                    ),
                "result":
                    event.get(
                        "result"
                    ),
                "amount_paise":
                    event.get(
                        "amount_paise"
                    ),
                "amount":
                    (
                        _money(
                            event[
                                "amount_paise"
                            ]
                        )
                        if event.get(
                            "amount_paise"
                        )
                        is not None
                        else None
                    ),
                "reason":
                    event.get(
                        "reason"
                    ),
                "metadata":
                    event.get(
                        "metadata",
                        {},
                    ),
                "created_at":
                    event.get(
                        "created_at"
                    ),
            }
            for event in activity
        ],
    }


# ============================================================
# CATALOG
# ============================================================

async def search_products(
    query: str,
    category: str | None,
    max_price_paise: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    db = get_db()

    limit = max(
        1,
        min(
            int(limit),
            50,
        ),
    )

    terms = [
        x.strip().lower()
        for x in query.split()
        if x.strip()
    ]

    docs = await (
        db.products
        .find(
            {
                "merchant_id":
                    settings.merchant_id,
                "active":
                    True,
            }
        )
        .to_list(
            length=None
        )
    )

    matches: list[
        tuple[
            int,
            float,
            int,
            dict[str, Any],
        ]
    ] = []

    for product in docs:
        product_category = str(
            product.get(
                "category",
                "",
            )
        ).lower()

        if (
            category
            and product_category
            != category.lower()
        ):
            continue

        price_paise = int(
            product.get(
                "price_paise",
                0,
            )
        )

        if (
            max_price_paise is not None
            and price_paise
            > max_price_paise
        ):
            continue

        searchable = " ".join(
            [
                str(
                    product.get(
                        "name",
                        "",
                    )
                ),
                str(
                    product.get(
                        "brand",
                        "",
                    )
                ),
                str(
                    product.get(
                        "category",
                        "",
                    )
                ),
                str(
                    product.get(
                        "description",
                        "",
                    )
                ),
                *[
                    str(tag)
                    for tag in product.get(
                        "tags",
                        [],
                    )
                ],
            ]
        ).lower()

        score = (
            sum(
                1
                for term in terms
                if term in searchable
            )
            if terms
            else 0
        )

        if not terms or score:
            matches.append(
                (
                    score,
                    float(
                        product.get(
                            "rating",
                            0,
                        )
                    ),
                    price_paise,
                    product,
                )
            )

    matches.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            item[2],
        )
    )

    return [
        public_product(item[3])
        for item in matches[:limit]
    ]


async def get_recommendations(
    product_id: str,
) -> list[dict[str, Any]]:
    db = get_db()

    product = await db.products.find_one(
        {
            "_id": product_id,
            "merchant_id":
                settings.merchant_id,
            "active":
                True,
        }
    )

    if not product:
        return []

    ids = product.get(
        "cross_sell_ids",
        [],
    )

    if not ids:
        return []

    docs = await (
        db.products
        .find(
            {
                "_id": {
                    "$in": ids
                },
                "merchant_id":
                    settings.merchant_id,
                "active":
                    True,
            }
        )
        .to_list(
            length=len(ids)
        )
    )

    return [
        {
            **public_product(
                item
            ),
            "recommendation_type":
                "CROSS_SELL",
            "reason":
                f"Often useful with "
                f"{product['name']}.",
        }
        for item in docs
    ]


# ============================================================
# SHARED USER CART
# ============================================================

async def get_or_create_cart(
    owner_clerk_user_id: str,
) -> dict[str, Any]:
    """
    One cart per authenticated user per merchant.

    IMPORTANT:
    There is deliberately NO agent_id in this document.
    The user chooses the payment method only at checkout.
    """
    db = get_db()

    cart = await db.carts.find_one(
        {
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "merchant_id":
                settings.merchant_id,
            "status":
                "ACTIVE",
        }
    )

    if cart:
        return cart

    cart = {
        "_id":
            f"cart_{uuid.uuid4().hex}",
        "owner_clerk_user_id":
            owner_clerk_user_id,
        "merchant_id":
            settings.merchant_id,
        "items":
            [],
        "subtotal_paise":
            0,
        "delivery_fee_paise":
            0,
        "total_paise":
            0,
        "currency":
            "INR",
        "status":
            "ACTIVE",
        "created_at":
            utc_now(),
        "updated_at":
            utc_now(),
    }

    await db.carts.insert_one(
        cart
    )

    return cart


def recalc_cart(
    cart: dict[str, Any],
) -> dict[str, Any]:
    subtotal = sum(
        int(
            item.get(
                "line_total_paise",
                0,
            )
        )
        for item in cart.get(
            "items",
            [],
        )
    )

    delivery = (
        3900
        if 0 < subtotal < 49900
        else 0
    )

    cart["subtotal_paise"] = (
        subtotal
    )

    cart["delivery_fee_paise"] = (
        delivery
    )

    cart["total_paise"] = (
        subtotal
        + delivery
    )

    return cart


async def get_cart(
    owner_clerk_user_id: str,
) -> dict[str, Any]:
    return _cart_payload(
        await get_or_create_cart(
            owner_clerk_user_id
        )
    )


async def add_to_cart(
    owner_clerk_user_id: str,
    product_id: str,
    quantity: int,
) -> dict[str, Any]:
    if quantity < 1:
        raise ValueError(
            "Quantity must be at least 1."
        )

    db = get_db()

    product = await db.products.find_one(
        {
            "_id":
                product_id,
            "merchant_id":
                settings.merchant_id,
            "active":
                True,
        }
    )

    if not product:
        raise ValueError(
            "Product not found."
        )

    cart = await get_or_create_cart(
        owner_clerk_user_id
    )

    items = cart.get(
        "items",
        [],
    )

    target = next(
        (
            item
            for item in items
            if item.get(
                "product_id"
            ) == product_id
        ),
        None,
    )

    existing_quantity = (
        int(
            target.get(
                "quantity",
                0,
            )
        )
        if target
        else 0
    )

    new_quantity = (
        existing_quantity
        + quantity
    )

    stock = int(
        product.get(
            "stock",
            0,
        )
    )

    if stock < new_quantity:
        raise ValueError(
            f"Only {stock} units of "
            f"{product['name']} are available."
        )

    unit_price = int(
        product["price_paise"]
    )

    item = {
        "product_id":
            product_id,
        "name":
            product["name"],
        "category":
            product["category"],
        "quantity":
            new_quantity,
        "unit_price_paise":
            unit_price,
        "line_total_paise":
            new_quantity * unit_price,
        "image":
            product.get(
                "image"
            ),
    }

    if target:
        target.update(item)
    else:
        items.append(item)

    cart["items"] = items

    recalc_cart(cart)

    cart["updated_at"] = utc_now()

    await db.carts.replace_one(
        {
            "_id":
                cart["_id"],
            "owner_clerk_user_id":
                owner_clerk_user_id,
        },
        cart,
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "CART_ITEM_ADDED",
        result=
            "SUCCESS",
        metadata={
            "product_id":
                product_id,
            "quantity":
                quantity,
        },
    )

    return _cart_payload(cart)


async def update_cart_item(
    owner_clerk_user_id: str,
    product_id: str,
    quantity: int,
) -> dict[str, Any]:
    if quantity < 1:
        raise ValueError(
            "Quantity must be at least 1."
        )

    db = get_db()

    cart = await get_or_create_cart(
        owner_clerk_user_id
    )

    target = next(
        (
            item
            for item in cart.get(
                "items",
                [],
            )
            if item.get(
                "product_id"
            ) == product_id
        ),
        None,
    )

    if not target:
        raise ValueError(
            "Product is not in the cart."
        )

    product = await db.products.find_one(
        {
            "_id":
                product_id,
            "merchant_id":
                settings.merchant_id,
            "active":
                True,
        }
    )

    if not product:
        raise ValueError(
            "Product is no longer available."
        )

    stock = int(
        product.get(
            "stock",
            0,
        )
    )

    if stock < quantity:
        raise ValueError(
            f"Only {stock} units of "
            f"{product['name']} are available."
        )

    unit_price = int(
        product["price_paise"]
    )

    target.update(
        {
            "quantity":
                quantity,
            "unit_price_paise":
                unit_price,
            "line_total_paise":
                quantity * unit_price,
            "name":
                product["name"],
            "category":
                product["category"],
            "image":
                product.get(
                    "image"
                ),
        }
    )

    recalc_cart(cart)

    cart["updated_at"] = utc_now()

    await db.carts.replace_one(
        {
            "_id":
                cart["_id"],
            "owner_clerk_user_id":
                owner_clerk_user_id,
        },
        cart,
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "CART_ITEM_UPDATED",
        result=
            "SUCCESS",
        metadata={
            "product_id":
                product_id,
            "quantity":
                quantity,
        },
    )

    return _cart_payload(cart)


async def remove_cart_item(
    owner_clerk_user_id: str,
    product_id: str,
) -> dict[str, Any]:
    db = get_db()

    cart = await get_or_create_cart(
        owner_clerk_user_id
    )

    before = len(
        cart.get(
            "items",
            [],
        )
    )

    cart["items"] = [
        item
        for item in cart.get(
            "items",
            [],
        )
        if item.get(
            "product_id"
        ) != product_id
    ]

    if len(
        cart["items"]
    ) == before:
        raise ValueError(
            "Product is not in the cart."
        )

    recalc_cart(cart)

    cart["updated_at"] = utc_now()

    await db.carts.replace_one(
        {
            "_id":
                cart["_id"],
            "owner_clerk_user_id":
                owner_clerk_user_id,
        },
        cart,
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "CART_ITEM_REMOVED",
        result=
            "SUCCESS",
        metadata={
            "product_id":
                product_id
        },
    )

    return _cart_payload(cart)


async def clear_cart(
    owner_clerk_user_id: str,
) -> dict[str, Any]:
    db = get_db()

    cart = await get_or_create_cart(
        owner_clerk_user_id
    )

    cart["items"] = []

    recalc_cart(cart)

    cart["updated_at"] = utc_now()

    await db.carts.replace_one(
        {
            "_id":
                cart["_id"],
            "owner_clerk_user_id":
                owner_clerk_user_id,
        },
        cart,
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "CART_CLEARED",
        result=
            "SUCCESS",
    )

    return _cart_payload(cart)


# ============================================================
# CURRENT CART VALIDATION
# ============================================================

async def _validate_current_cart(
    db: Any,
    cart: dict[str, Any],
) -> dict[str, Any]:
    """
    Re-read every product.

    Never trust the cart's previously captured price
    or stock as the checkout authority.
    """

    items: list[
        dict[str, Any]
    ] = []

    categories: list[str] = []

    for cart_item in cart.get(
        "items",
        [],
    ):
        product_id = cart_item[
            "product_id"
        ]

        product = await db.products.find_one(
            {
                "_id":
                    product_id,
                "merchant_id":
                    settings.merchant_id,
                "active":
                    True,
            }
        )

        if not product:
            raise ValueError(
                f"Product {product_id} "
                "is no longer available."
            )

        quantity = int(
            cart_item[
                "quantity"
            ]
        )

        if quantity < 1:
            raise ValueError(
                "Invalid cart quantity."
            )

        stock = int(
            product.get(
                "stock",
                0,
            )
        )

        if stock < quantity:
            raise ValueError(
                f"Only {stock} units of "
                f"{product['name']} are available."
            )

        unit_price_paise = int(
            product[
                "price_paise"
            ]
        )

        items.append(
            {
                "product_id":
                    product["_id"],
                "name":
                    product["name"],
                "category":
                    product["category"],
                "quantity":
                    quantity,
                "unit_price_paise":
                    unit_price_paise,
                "line_total_paise":
                    quantity
                    * unit_price_paise,
                "image":
                    product.get(
                        "image"
                    ),
            }
        )

        categories.append(
            str(
                product[
                    "category"
                ]
            ).lower()
        )

    subtotal_paise = sum(
        item[
            "line_total_paise"
        ]
        for item in items
    )

    delivery_fee_paise = (
        3900
        if 0 < subtotal_paise < 49900
        else 0
    )

    total_paise = (
        subtotal_paise
        + delivery_fee_paise
    )

    return {
        "items":
            items,
        "categories":
            categories,
        "subtotal_paise":
            subtotal_paise,
        "delivery_fee_paise":
            delivery_fee_paise,
        "total_paise":
            total_paise,
    }


# ============================================================
# RAZORPAY — AGENT FUNDING
# ============================================================

async def create_agent_funding_order(
    owner_clerk_user_id: str,
    agent_id: str,
    amount_paise: int,
) -> dict[str, Any]:
    if (
        not settings.razorpay_key_id
        or not settings.razorpay_key_secret
    ):
        raise ValueError(
            "Razorpay credentials are not configured."
        )

    if amount_paise < 100:
        raise ValueError(
            "Minimum funding amount is ₹1."
        )

    agent = await get_owned_agent(
        owner_clerk_user_id,
        agent_id,
    )

    if not agent:
        raise ValueError(
            "Agent not found."
        )

    if agent.get(
        "status"
    ) != "ACTIVE":
        raise ValueError(
            "Only active agents can be funded."
        )

    receipt = (
        f"umon_fund_"
        f"{uuid.uuid4().hex[:20]}"
    )

    async with httpx.AsyncClient(
        timeout=20
    ) as client:
        response = await client.post(
            "https://api.razorpay.com/v1/orders",
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret,
            ),
            json={
                "amount":
                    amount_paise,
                "currency":
                    settings.razorpay_currency,
                "receipt":
                    receipt,
                "notes": {
                    "type":
                        "agent_funding",
                    "agent_id":
                        agent_id,
                    "owner_clerk_user_id":
                        owner_clerk_user_id,
                },
            },
        )

    response.raise_for_status()

    data = response.json()

    payment_ref = (
        f"fund_{uuid.uuid4().hex}"
    )

    db = get_db()

    await db.payments.insert_one(
        {
            "_id":
                payment_ref,
            "type":
                "AGENT_FUNDING",
            "status":
                "CREATED",
            "agent_id":
                agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "amount_paise":
                amount_paise,
            "currency":
                settings.razorpay_currency,
            "razorpay_order_id":
                data["id"],
            "receipt":
                receipt,
            "created_at":
                utc_now(),
            "updated_at":
                utc_now(),
        }
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "AGENT_FUNDING_ORDER_CREATED",
        result=
            "SUCCESS",
        agent_id=
            agent_id,
        amount_paise=
            amount_paise,
        metadata={
            "razorpay_order_id":
                data["id"]
        },
    )

    return {
        "payment_id":
            payment_ref,
        "razorpay_order_id":
            data["id"],
        "amount_paise":
            amount_paise,
        "currency":
            settings.razorpay_currency,
        "key_id":
            settings.razorpay_key_id,
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
        raise ValueError(
            "Razorpay credentials are not configured."
        )

    db = get_db()

    payment = await db.payments.find_one(
        {
            "_id":
                payment_id,
            "type":
                "AGENT_FUNDING",
            "agent_id":
                agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
        }
    )

    if not payment:
        raise ValueError(
            "Funding payment not found."
        )

    stored_order_id = payment.get(
        "razorpay_order_id"
    )

    if (
        stored_order_id
        != razorpay_order_id
    ):
        raise ValueError(
            "Razorpay order mismatch."
        )

    # Idempotent fast path.
    if payment.get(
        "status"
    ) == "SUCCEEDED":
        current_agent = (
            await get_owned_agent(
                owner_clerk_user_id,
                agent_id,
            )
        )

        return {
            "success":
                True,
            "status":
                "ALREADY_APPLIED",
            "agent":
                public_agent(
                    current_agent
                ),
        }

    message = (
        f"{razorpay_order_id}"
        f"|{razorpay_payment_id}"
    ).encode()

    expected_signature = hmac.new(
        settings.razorpay_key_secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_signature,
        razorpay_signature,
    ):
        raise ValueError(
            "Invalid Razorpay payment signature."
        )

    amount_paise = int(
        payment[
            "amount_paise"
        ]
    )

    # --------------------------------------------------------
    # Provider payment can only be applied once.
    # --------------------------------------------------------

    ledger_id = (
        f"funding:"
        f"{razorpay_payment_id}"
    )

    # First make sure the payment provider reference is not
    # already attached to another funding payment.
    existing_funding = await db.payments.find_one(
        {
            "type":
                "AGENT_FUNDING",
            "provider_payment_id":
                razorpay_payment_id,
            "_id":
                {
                    "$ne":
                        payment_id
                },
        }
    )

    if existing_funding:
        raise ValueError(
            "This Razorpay payment has already been used."
        )

    # --------------------------------------------------------
    # Atomically claim provider payment + provider ref.
    # --------------------------------------------------------

    claimed_payment = (
        await db.payments.find_one_and_update(
            {
                "_id":
                    payment_id,
                "status":
                    {
                        "$ne":
                            "SUCCEEDED"
                    },
            },
            {
                "$set": {
                    "status":
                        "SUCCEEDED",
                    "provider_payment_id":
                        razorpay_payment_id,
                    "updated_at":
                        utc_now(),
                }
            },
            return_document=
                ReturnDocument.AFTER,
        )
    )

    if not claimed_payment:
        current_agent = (
            await get_owned_agent(
                owner_clerk_user_id,
                agent_id,
            )
        )

        return {
            "success":
                True,
            "status":
                "ALREADY_APPLIED",
            "agent":
                public_agent(
                    current_agent
                ),
        }

    # --------------------------------------------------------
    # Idempotent agent credit.
    # --------------------------------------------------------

    credited_agent = (
        await db.agents.find_one_and_update(
            {
                "_id":
                    agent_id,
                "owner_clerk_user_id":
                    owner_clerk_user_id,
                "status":
                    "ACTIVE",
                "funding_refs":
                    {
                        "$ne":
                            razorpay_payment_id
                    },
            },
            {
                "$inc": {
                    "balance_available_paise":
                        amount_paise,
                    "lifetime_funded_paise":
                        amount_paise,
                },
                "$addToSet": {
                    "funding_refs":
                        razorpay_payment_id
                },
                "$set": {
                    "updated_at":
                        utc_now(),
                },
            },
            return_document=
                ReturnDocument.AFTER,
        )
    )

    if not credited_agent:
        existing_ref = await db.agents.find_one(
            {
                "_id":
                    agent_id,
                "owner_clerk_user_id":
                    owner_clerk_user_id,
                "funding_refs":
                    razorpay_payment_id,
            }
        )

        if existing_ref:
            return {
                "success":
                    True,
                "status":
                    "ALREADY_APPLIED",
                "agent":
                    public_agent(
                        existing_ref
                    ),
            }

        raise ValueError(
            "Unable to credit agent funding."
        )

    # --------------------------------------------------------
    # Durable ledger.
    # --------------------------------------------------------

    try:
        await db.ledger_entries.insert_one(
            {
                "_id":
                    ledger_id,
                "entry_id":
                    ledger_id,
                "agent_id":
                    agent_id,
                "owner_clerk_user_id":
                    owner_clerk_user_id,
                "type":
                    "CREDIT",
                "amount_paise":
                    amount_paise,
                "reference":
                    razorpay_payment_id,
                "reason":
                    "Verified Razorpay agent funding.",
                "created_at":
                    utc_now(),
            }
        )
    except Exception:
        existing_ledger = (
            await db.ledger_entries.find_one(
                {
                    "_id":
                        ledger_id
                }
            )
        )

        if not existing_ledger:
            # We already credited the balance. Do not silently
            # continue because the ledger is required for audit.
            raise

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "AGENT_FUNDED",
        result=
            "SUCCESS",
        agent_id=
            agent_id,
        amount_paise=
            amount_paise,
        reason=
            "Razorpay payment verified and agent ledger credited.",
        metadata={
            "razorpay_payment_id":
                razorpay_payment_id,
            "razorpay_order_id":
                razorpay_order_id,
        },
    )

    return {
        "success":
            True,
        "status":
            "FUNDED",
        "agent":
            public_agent(
                credited_agent
            ),
    }


# ============================================================
# RAZORPAY — DIRECT USER CHECKOUT
# ============================================================

async def create_direct_razorpay_order(
    owner_clerk_user_id: str,
) -> dict[str, Any]:
    if (
        not settings.razorpay_key_id
        or not settings.razorpay_key_secret
    ):
        raise ValueError(
            "Razorpay credentials are not configured."
        )

    db = get_db()

    cart = await get_or_create_cart(
        owner_clerk_user_id
    )

    if not cart.get(
        "items"
    ):
        raise ValueError(
            "Cart is empty."
        )

    validated = await _validate_current_cart(
        db,
        cart,
    )

    total_paise = int(
        validated[
            "total_paise"
        ]
    )

    payment_ref = (
        f"pay_{uuid.uuid4().hex}"
    )

    receipt = (
        f"umon_pay_"
        f"{uuid.uuid4().hex[:20]}"
    )

    async with httpx.AsyncClient(
        timeout=20
    ) as client:
        response = await client.post(
            "https://api.razorpay.com/v1/orders",
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret,
            ),
            json={
                "amount":
                    total_paise,
                "currency":
                    "INR",
                "receipt":
                    receipt,
                "notes": {
                    "type":
                        "store_checkout",
                    "owner_clerk_user_id":
                        owner_clerk_user_id,
                    "payment_ref":
                        payment_ref,
                },
            },
        )

    response.raise_for_status()

    data = response.json()

    order_id = (
        f"ord_{uuid.uuid4().hex}"
    )

    await db.orders.insert_one(
        {
            "_id":
                order_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "merchant_id":
                settings.merchant_id,
            "payment_method":
                "RAZORPAY",
            "agent_id":
                None,
            "status":
                "PAYMENT_PENDING",
            "payment_status":
                "PENDING",
            "amount_paise":
                total_paise,
            "currency":
                "INR",
            "items":
                validated["items"],
            "created_at":
                utc_now(),
            "updated_at":
                utc_now(),
        }
    )

    await db.payments.insert_one(
        {
            "_id":
                payment_ref,
            "type":
                "STORE_CHECKOUT",
            "status":
                "CREATED",
            "order_id":
                order_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "amount_paise":
                total_paise,
            "currency":
                "INR",
            "razorpay_order_id":
                data["id"],
            "created_at":
                utc_now(),
            "updated_at":
                utc_now(),
        }
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "RAZORPAY_CHECKOUT_CREATED",
        result=
            "SUCCESS",
        amount_paise=
            total_paise,
        metadata={
            "order_id":
                order_id,
            "razorpay_order_id":
                data["id"],
        },
    )

    return {
        "payment_id":
            payment_ref,
        "order_id":
            order_id,
        "razorpay_order_id":
            data["id"],
        "amount_paise":
            total_paise,
        "currency":
            "INR",
        "key_id":
            settings.razorpay_key_id,
    }


async def _decrement_inventory_for_order(
    db: Any,
    order: dict[str, Any],
) -> None:
    """
    Atomically decrement every product in the order.

    If one item fails, restore all previously decremented
    items.
    """

    changed: list[
        dict[str, Any]
    ] = []

    try:
        for item in order.get(
            "items",
            [],
        ):
            product_id = item[
                "product_id"
            ]

            quantity = int(
                item[
                    "quantity"
                ]
            )

            updated = (
                await db.products.find_one_and_update(
                    {
                        "_id":
                            product_id,
                        "merchant_id":
                            settings.merchant_id,
                        "stock":
                            {
                                "$gte":
                                    quantity
                            },
                        "active":
                            True,
                    },
                    {
                        "$inc": {
                            "stock":
                                -quantity
                        }
                    },
                    return_document=
                        ReturnDocument.AFTER,
                )
            )

            if not updated:
                raise ValueError(
                    "Inventory changed for "
                    f"{item['name']}."
                )

            changed.append(
                item
            )

    except Exception:
        for item in changed:
            await db.products.update_one(
                {
                    "_id":
                        item["product_id"],
                    "merchant_id":
                        settings.merchant_id,
                },
                {
                    "$inc": {
                        "stock":
                            int(
                                item[
                                    "quantity"
                                ]
                            )
                    }
                },
            )

        raise


async def verify_direct_razorpay_order(
    owner_clerk_user_id: str,
    payment_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict[str, Any]:
    if not settings.razorpay_key_secret:
        raise ValueError(
            "Razorpay credentials are not configured."
        )

    db = get_db()

    payment = await db.payments.find_one(
        {
            "_id":
                payment_id,
            "type":
                "STORE_CHECKOUT",
            "owner_clerk_user_id":
                owner_clerk_user_id,
        }
    )

    if not payment:
        raise ValueError(
            "Payment not found."
        )

    if (
        payment.get(
            "razorpay_order_id"
        )
        != razorpay_order_id
    ):
        raise ValueError(
            "Razorpay order mismatch."
        )

    expected_signature = hmac.new(
        settings.razorpay_key_secret.encode(),
        (
            f"{razorpay_order_id}"
            f"|{razorpay_payment_id}"
        ).encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_signature,
        razorpay_signature,
    ):
        raise ValueError(
            "Invalid Razorpay payment signature."
        )

    # Idempotent provider-payment claim.
    claimed_payment = (
        await db.payments.find_one_and_update(
            {
                "_id":
                    payment_id,
                "status":
                    {
                        "$ne":
                            "SUCCEEDED"
                    },
            },
            {
                "$set": {
                    "status":
                        "SUCCEEDED",
                    "provider_payment_id":
                        razorpay_payment_id,
                    "updated_at":
                        utc_now(),
                }
            },
            return_document=
                ReturnDocument.AFTER,
        )
    )

    if not claimed_payment:
        order = await db.orders.find_one(
            {
                "_id":
                    payment.get(
                        "order_id"
                    ),
                "owner_clerk_user_id":
                    owner_clerk_user_id,
            }
        )

        return {
            "success":
                True,
            "status":
                order.get(
                    "status",
                    "PAID",
                )
                if order
                else "PAID",
            "order_id":
                payment.get(
                    "order_id"
                ),
        }

    order_id = payment.get(
        "order_id"
    )

    if not order_id:
        raise ValueError(
            "Payment is not linked to an order."
        )

    order = await db.orders.find_one(
        {
            "_id":
                order_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
        }
    )

    if not order:
        raise ValueError(
            "Order not found."
        )

    # Already completed path.
    if order.get(
        "payment_status"
    ) == "PAID":
        return {
            "success":
                True,
            "status":
                order.get(
                    "status",
                    "CONFIRMED",
                ),
            "order_id":
                order_id,
        }

    # --------------------------------------------------------
    # Provider has now confirmed the payment.
    # Inventory/order processing may still fail.
    # We DO NOT tell the user the payment failed.
    # --------------------------------------------------------

    try:
        await _decrement_inventory_for_order(
            db,
            order,
        )

    except Exception as exc:
        await db.orders.update_one(
            {
                "_id":
                    order_id,
                "owner_clerk_user_id":
                    owner_clerk_user_id,
            },
            {
                "$set": {
                    "status":
                        "MERCHANT_PENDING",
                    "payment_status":
                        "PAID",
                    "failure_reason":
                        str(exc),
                    "updated_at":
                        utc_now(),
                }
            },
        )

        await audit(
            owner_clerk_user_id=
                owner_clerk_user_id,
            action=
                "ORDER_MERCHANT_PENDING",
            result=
                "PENDING",
            amount_paise=
                order.get(
                    "amount_paise",
                    0,
                ),
            reason=
                str(exc),
            metadata={
                "order_id":
                    order_id,
                "payment_method":
                    "RAZORPAY",
                "razorpay_payment_id":
                    razorpay_payment_id,
            },
        )

        return {
            "success":
                True,
            "status":
                "MERCHANT_PENDING",
            "order_id":
                order_id,
            "message":
                "Payment succeeded, but the "
                "merchant order needs recovery.",
        }

    # --------------------------------------------------------
    # Mark order confirmed.
    # --------------------------------------------------------

    await db.orders.update_one(
        {
            "_id":
                order_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
        },
        {
            "$set": {
                "status":
                    "CONFIRMED",
                "payment_status":
                    "PAID",
                "updated_at":
                    utc_now(),
            }
        },
    )

    # Clear only the ACTIVE cart after successful order creation.
    await db.carts.update_one(
        {
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "merchant_id":
                settings.merchant_id,
            "status":
                "ACTIVE",
        },
        {
            "$set": {
                "items":
                    [],
                "subtotal_paise":
                    0,
                "delivery_fee_paise":
                    0,
                "total_paise":
                    0,
                "status":
                    "ACTIVE",
                "updated_at":
                    utc_now(),
            }
        },
    )

    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "ORDER_COMPLETED",
        result=
            "SUCCESS",
        amount_paise=
            order.get(
                "amount_paise",
                0,
            ),
        metadata={
            "order_id":
                order_id,
            "payment_method":
                "RAZORPAY",
            "razorpay_payment_id":
                razorpay_payment_id,
        },
    )

    return {
        "success":
            True,
        "status":
            "PAID",
        "order_id":
            order_id,
    }


# ============================================================
# AGENT-BALANCE CHECKOUT
# ============================================================

async def checkout_with_agent_balance(
    owner_clerk_user_id: str,
    agent_id: str,
    confirmed: bool = False,
) -> dict[str, Any]:

    db = get_db()

    # 1. Make sure this agent belongs to this user.
    agent = await get_owned_agent(
        owner_clerk_user_id,
        agent_id,
    )

    if not agent:
        raise ValueError(
            "Agent not found."
        )

    # 2. ONE shared user cart.
    cart = await get_or_create_cart(
        owner_clerk_user_id
    )

    if not cart.get("items"):
        raise ValueError(
            "Cart is empty."
        )

    # 3. Re-read current product data.
    validated = await _validate_current_cart(
        db,
        cart,
    )

    total_paise = int(
        validated["total_paise"]
    )

    # 4. Merchant configuration.
    merchant = await db.merchants.find_one(
        {
            "_id":
                settings.merchant_id
        }
    )

    if not merchant:
        raise ValueError(
            "Merchant is unavailable."
        )

    # 5. AUTHORITATIVE POLICY ENGINE.
    policy = await evaluate_purchase(
        agent=agent,
        amount_paise=total_paise,
        categories=validated["categories"],
        merchant=merchant,
        confirmed=confirmed,
    )

    # 6. Always audit the decision.
    await audit(
        owner_clerk_user_id=
            owner_clerk_user_id,
        action=
            "PURCHASE_POLICY_EVALUATED",
        result=
            policy["decision"],
        agent_id=
            agent_id,
        amount_paise=
            total_paise,
        reason=
            policy.get("reason"),
        metadata={
            "code":
                policy.get("code"),
        },
    )

    # 7. BLOCK / CONFIRM means NO MONEY MOVEMENT.
    if policy["decision"] != "ALLOW":
        return {
            "success":
                False,
            "status":
                policy["decision"],
            "policy":
                policy,
            "total_paise":
                total_paise,
            "total":
                round(
                    total_paise / 100,
                    2,
                ),
        }

    # 8. Reserve agent funds atomically.
    reservation_id = (
        f"res_{uuid.uuid4().hex}"
    )

    await reserve_agent_balance(
        agent_id=
            agent_id,
        owner_clerk_user_id=
            owner_clerk_user_id,
        amount_paise=
            total_paise,
    )

    try:

        # 9. Consume inventory atomically.
        changed = []

        for item in validated["items"]:
            updated = (
                await db.products.find_one_and_update(
                    {
                        "_id":
                            item["product_id"],
                        "merchant_id":
                            settings.merchant_id,
                        "stock":
                            {
                                "$gte":
                                    int(
                                        item["quantity"]
                                    )
                            },
                        "active":
                            True,
                    },
                    {
                        "$inc": {
                            "stock":
                                -int(
                                    item["quantity"]
                                )
                        }
                    },
                    return_document=
                        ReturnDocument.AFTER,
                )
            )

            if not updated:
                raise ValueError(
                    f"Inventory changed for "
                    f"{item['name']}."
                )

            changed.append(item)

        # 10. Create merchant order.
        order_id = (
            f"ord_{uuid.uuid4().hex}"
        )

        order_document = {
            "_id":
                order_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "agent_id":
                agent_id,
            "merchant_id":
                settings.merchant_id,
            "payment_method":
                "AGENT_BALANCE",
            "status":
                "CONFIRMED",
            "payment_status":
                "PAID",
            "amount_paise":
                total_paise,
            "currency":
                "INR",
            "items":
                validated["items"],
            "created_at":
                utc_now(),
            "updated_at":
                utc_now(),
        }

        await db.orders.insert_one(
            order_document
        )

        # 11. Permanently consume reservation.
        await commit_agent_balance(
            agent_id=
                agent_id,
            owner_clerk_user_id=
                owner_clerk_user_id,
            amount_paise=
                total_paise,
        )

        # 12. Durable debit ledger.
        debit_id = (
            f"debit:{order_id}"
        )

        await db.ledger_entries.insert_one(
            {
                "_id":
                    debit_id,
                "entry_id":
                    debit_id,
                "agent_id":
                    agent_id,
                "owner_clerk_user_id":
                    owner_clerk_user_id,
                "type":
                    "DEBIT",
                "amount_paise":
                    total_paise,
                "reference":
                    order_id,
                "reason":
                    "Agent balance committed to merchant order.",
                "created_at":
                    utc_now(),
            }
        )

        # 13. Clear the ONE shared cart.
        await db.carts.update_one(
            {
                "_id":
                    cart["_id"],
                "owner_clerk_user_id":
                    owner_clerk_user_id,
            },
            {
                "$set": {
                    "items": [],
                    "subtotal_paise": 0,
                    "delivery_fee_paise": 0,
                    "total_paise": 0,
                    "status": "ACTIVE",
                    "updated_at":
                        utc_now(),
                }
            },
        )

        final_agent = await get_owned_agent(
            owner_clerk_user_id,
            agent_id,
        )

        await audit(
            owner_clerk_user_id=
                owner_clerk_user_id,
            action=
                "ORDER_COMPLETED",
            result=
                "SUCCESS",
            agent_id=
                agent_id,
            amount_paise=
                total_paise,
            reason=
                "Purchase completed using agent balance.",
            metadata={
                "order_id":
                    order_id,
                "payment_method":
                    "AGENT_BALANCE",
            },
        )

        return {
            "success":
                True,
            "status":
                "COMPLETED",
            "order": {
                "id":
                    order_id,
                "amount_paise":
                    total_paise,
                "amount":
                    round(
                        total_paise / 100,
                        2,
                    ),
                "currency":
                    "INR",
                "status":
                    "CONFIRMED",
                "payment_method":
                    "AGENT_BALANCE",
                "items":
                    validated["items"],
            },
            "agent":
                public_agent(
                    final_agent
                ),
            "policy":
                policy,
        }

    except Exception as exc:

        # Restore inventory.
        for item in changed:
            await db.products.update_one(
                {
                    "_id":
                        item["product_id"],
                    "merchant_id":
                        settings.merchant_id,
                },
                {
                    "$inc": {
                        "stock":
                            int(
                                item["quantity"]
                            )
                    },
                },
            )

        # Restore reserved agent money.
        await release_agent_balance(
            agent_id=
                agent_id,
            owner_clerk_user_id=
                owner_clerk_user_id,
            amount_paise=
                total_paise,
        )

        release_id = (
            f"release:{reservation_id}"
        )

        try:
            await db.ledger_entries.insert_one(
                {
                    "_id":
                        release_id,
                    "entry_id":
                        release_id,
                    "agent_id":
                        agent_id,
                    "owner_clerk_user_id":
                        owner_clerk_user_id,
                    "type":
                        "RELEASE",
                    "amount_paise":
                        total_paise,
                    "reference":
                        reservation_id,
                    "reason":
                        "Released reserved balance after failed checkout.",
                    "created_at":
                        utc_now(),
                }
            )
        except Exception:
            existing_release = (
                await db.ledger_entries.find_one(
                    {
                        "_id":
                            release_id
                    }
                )
            )

            if not existing_release:
                raise

        await audit(
            owner_clerk_user_id=
                owner_clerk_user_id,
            action=
                "PURCHASE_FAILED",
            result=
                "FAILED",
            agent_id=
                agent_id,
            amount_paise=
                total_paise,
            reason=
                str(exc),
            metadata={
                "reservation_id":
                    reservation_id,
            },
        )

        raise


# ============================================================
# DEV ADMIN / MERCHANT CONTROL CENTER
#
# IMPORTANT:
# These endpoints intentionally have NO admin authentication
# for the local/buildathon environment.
#
# NEVER expose /api/admin/* publicly without authentication.
# ============================================================


async def admin_dashboard() -> dict[str, Any]:
    db = get_db()

    users_count = await db.users.count_documents({})
    agents_count = await db.agents.count_documents({})
    active_agents_count = await db.agents.count_documents(
        {
            "status": "ACTIVE",
        }
    )

    orders_count = await db.orders.count_documents({})

    paid_orders_count = await db.orders.count_documents(
        {
            "payment_status": "PAID",
        }
    )

    pending_payment_count = await db.orders.count_documents(
        {
            "payment_status": {
                "$in": [
                    "PENDING",
                    "PROCESSING",
                    "UNKNOWN",
                ]
            }
        }
    )

    products_count = await db.products.count_documents(
        {
            "merchant_id":
                settings.merchant_id,
        }
    )

    active_products_count = await db.products.count_documents(
        {
            "merchant_id":
                settings.merchant_id,
            "active":
                True,
        }
    )

    gmv_cursor = await db.orders.aggregate(
        [
            {
                "$match": {
                    "merchant_id":
                        settings.merchant_id,
                    "payment_status":
                        "PAID",
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum":
                            "$amount_paise",
                    },
                }
            },
        ]
    )

    gmv_rows = await gmv_cursor.to_list(
        length=1
    )

    gmv_paise = (
        int(gmv_rows[0]["total"])
        if gmv_rows
        else 0
    )

    agent_balance_cursor = await db.agents.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "available": {
                        "$sum":
                            "$balance_available_paise",
                    },
                    "reserved": {
                        "$sum":
                            "$balance_reserved_paise",
                    },
                }
            }
        ]
    )

    agent_balance_rows = (
        await agent_balance_cursor.to_list(
            length=1
        )
    )

    total_agent_available = (
        int(
            agent_balance_rows[0].get(
                "available",
                0,
            )
        )
        if agent_balance_rows
        else 0
    )

    total_agent_reserved = (
        int(
            agent_balance_rows[0].get(
                "reserved",
                0,
            )
        )
        if agent_balance_rows
        else 0
    )

    merchant = await db.merchants.find_one(
        {
            "_id":
                settings.merchant_id,
        }
    )

    recent_orders = await (
        db.orders
        .find(
            {
                "merchant_id":
                    settings.merchant_id,
            }
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(10)
        .to_list(
            length=10
        )
    )

    recent_audit = await (
        db.audit_events
        .find({})
        .sort(
            "created_at",
            -1,
        )
        .limit(20)
        .to_list(
            length=20
        )
    )

    return {
        "merchant": merchant,
        "metrics": {
            "users":
                users_count,
            "agents":
                agents_count,
            "active_agents":
                active_agents_count,
            "orders":
                orders_count,
            "paid_orders":
                paid_orders_count,
            "pending_payments":
                pending_payment_count,
            "products":
                products_count,
            "active_products":
                active_products_count,
            "gmv_paise":
                gmv_paise,
            "gmv":
                _money(
                    gmv_paise
                ),
            "agent_available_paise":
                total_agent_available,
            "agent_available":
                _money(
                    total_agent_available
                ),
            "agent_reserved_paise":
                total_agent_reserved,
            "agent_reserved":
                _money(
                    total_agent_reserved
                ),
        },
        "recent_orders": [
            {
                "id":
                    order["_id"],
                "status":
                    order.get("status"),
                "payment_status":
                    order.get(
                        "payment_status"
                    ),
                "payment_method":
                    order.get(
                        "payment_method"
                    ),
                "agent_id":
                    order.get(
                        "agent_id"
                    ),
                "amount_paise":
                    int(
                        order.get(
                            "amount_paise",
                            0,
                        )
                    ),
                "amount":
                    _money(
                        order.get(
                            "amount_paise",
                            0,
                        )
                    ),
                "created_at":
                    order.get(
                        "created_at"
                    ),
            }
            for order in recent_orders
        ],
        "recent_audit": [
            {
                "id":
                    event["_id"],
                "action":
                    event.get(
                        "action"
                    ),
                "result":
                    event.get(
                        "result"
                    ),
                "agent_id":
                    event.get(
                        "agent_id"
                    ),
                "amount_paise":
                    event.get(
                        "amount_paise"
                    ),
                "amount":
                    (
                        _money(
                            event[
                                "amount_paise"
                            ]
                        )
                        if event.get(
                            "amount_paise"
                        )
                        is not None
                        else None
                    ),
                "reason":
                    event.get(
                        "reason"
                    ),
                "created_at":
                    event.get(
                        "created_at"
                    ),
            }
            for event in recent_audit
        ],
    }


async def admin_get_merchant() -> dict[str, Any]:
    db = get_db()

    merchant = await db.merchants.find_one(
        {
            "_id":
                settings.merchant_id,
        }
    )

    if not merchant:
        raise ValueError(
            "Merchant not found."
        )

    return merchant


async def admin_update_merchant(
    *,
    name: str | None = None,
    status: str | None = None,
    ai_discovery: bool | None = None,
    ai_purchasing: bool | None = None,
    ai_checkout: bool | None = None,
    recommendations_enabled: bool | None = None,
    max_order_value: float | None = None,
    allowed_categories: list[str] | None = None,
) -> dict[str, Any]:

    db = get_db()

    merchant = await admin_get_merchant()

    updates: dict[str, Any] = {
        "updated_at":
            utc_now(),
    }

    if name is not None:
        cleaned_name = name.strip()

        if not cleaned_name:
            raise ValueError(
                "Merchant name cannot be empty."
            )

        updates["name"] = cleaned_name

    if status is not None:
        normalized_status = (
            status.strip().upper()
        )

        if normalized_status not in {
            "ACTIVE",
            "DISABLED",
        }:
            raise ValueError(
                "Merchant status must be ACTIVE or DISABLED."
            )

        updates["status"] = (
            normalized_status
        )

    if ai_discovery is not None:
        updates[
            "ai_discovery"
        ] = bool(
            ai_discovery
        )

    if ai_purchasing is not None:
        updates[
            "ai_purchasing"
        ] = bool(
            ai_purchasing
        )

    if ai_checkout is not None:
        updates[
            "ai_checkout"
        ] = bool(
            ai_checkout
        )

    if recommendations_enabled is not None:
        updates[
            "recommendations_enabled"
        ] = bool(
            recommendations_enabled
        )

    if max_order_value is not None:
        if max_order_value <= 0:
            raise ValueError(
                "Maximum order value must be greater than zero."
            )

        updates[
            "max_order_value"
        ] = round(
            max_order_value * 100
        )

    if allowed_categories is not None:
        normalized_categories = sorted(
            {
                str(value)
                .strip()
                .lower()
                for value in allowed_categories
                if str(value).strip()
            }
        )

        updates[
            "allowed_categories"
        ] = normalized_categories

    updated = await db.merchants.find_one_and_update(
        {
            "_id":
                settings.merchant_id,
        },
        {
            "$set":
                updates,
        },
        return_document=
            ReturnDocument.AFTER,
    )

    if not updated:
        raise ValueError(
            "Merchant not found."
        )

    return updated


async def admin_list_products(
    *,
    query: str = "",
    include_inactive: bool = True,
) -> list[dict[str, Any]]:

    db = get_db()

    mongo_query: dict[str, Any] = {
        "merchant_id":
            settings.merchant_id,
    }

    if not include_inactive:
        mongo_query[
            "active"
        ] = True

    query = query.strip()

    if query:
        mongo_query[
            "$or"
        ] = [
            {
                "name": {
                    "$regex":
                        query,
                    "$options":
                        "i",
                }
            },
            {
                "brand": {
                    "$regex":
                        query,
                    "$options":
                        "i",
                }
            },
            {
                "category": {
                    "$regex":
                        query,
                    "$options":
                        "i",
                }
            },
        ]

    products = await (
        db.products
        .find(mongo_query)
        .sort(
            "name",
            1,
        )
        .limit(200)
        .to_list(
            length=200
        )
    )

    return [
        public_product(
            product
        )
        for product in products
    ]


async def admin_create_product(
    *,
    name: str,
    brand: str,
    category: str,
    price_paise: int,
    mrp_paise: int,
    stock: int,
    unit: str,
    description: str,
    image: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:

    db = get_db()

    if price_paise <= 0:
        raise ValueError(
            "Price must be greater than zero."
        )

    if mrp_paise < price_paise:
        raise ValueError(
            "MRP cannot be lower than selling price."
        )

    if stock < 0:
        raise ValueError(
            "Stock cannot be negative."
        )

    normalized_category = (
        category.strip().lower()
    )

    if not normalized_category:
        raise ValueError(
            "Category is required."
        )

    now = utc_now()

    product = {
        "_id":
            f"p_{uuid.uuid4().hex}",
        "merchant_id":
            settings.merchant_id,
        "name":
            name.strip(),
        "brand":
            brand.strip(),
        "category":
            normalized_category,
        "price_paise":
            int(price_paise),
        "mrp_paise":
            int(mrp_paise),
        "rating":
            0,
        "stock":
            int(stock),
        "unit":
            unit.strip(),
        "description":
            description.strip(),
        "image":
            image.strip()
            if image
            else None,
        "tags":
            sorted(
                {
                    str(tag)
                    .strip()
                    .lower()
                    for tag in (
                        tags or []
                    )
                    if str(tag).strip()
                }
            ),
        "active":
            True,
        "created_at":
            now,
        "updated_at":
            now,
    }

    await db.products.insert_one(
        product
    )

    return public_product(
        product
    )


async def admin_update_product(
    product_id: str,
    *,
    name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    price_paise: int | None = None,
    mrp_paise: int | None = None,
    stock: int | None = None,
    unit: str | None = None,
    description: str | None = None,
    image: str | None = None,
    tags: list[str] | None = None,
    active: bool | None = None,
) -> dict[str, Any]:

    db = get_db()

    existing = await db.products.find_one(
        {
            "_id":
                product_id,
            "merchant_id":
                settings.merchant_id,
        }
    )

    if not existing:
        raise ValueError(
            "Product not found."
        )

    updates: dict[str, Any] = {
        "updated_at":
            utc_now(),
    }

    if name is not None:
        if not name.strip():
            raise ValueError(
                "Product name cannot be empty."
            )

        updates[
            "name"
        ] = name.strip()

    if brand is not None:
        updates[
            "brand"
        ] = brand.strip()

    if category is not None:
        if not category.strip():
            raise ValueError(
                "Category cannot be empty."
            )

        updates[
            "category"
        ] = category.strip().lower()

    if price_paise is not None:
        if price_paise <= 0:
            raise ValueError(
                "Price must be greater than zero."
            )

        current_mrp = int(
            existing.get(
                "mrp_paise",
                price_paise,
            )
        )

        if (
            mrp_paise is None
            and price_paise > current_mrp
        ):
            raise ValueError(
                "Price cannot exceed MRP."
            )

        updates[
            "price_paise"
        ] = int(price_paise)

    if mrp_paise is not None:
        if mrp_paise <= 0:
            raise ValueError(
                "MRP must be greater than zero."
            )

        final_price = int(
            updates.get(
                "price_paise",
                existing.get(
                    "price_paise",
                    0,
                ),
            )
        )

        if mrp_paise < final_price:
            raise ValueError(
                "MRP cannot be lower than selling price."
            )

        updates[
            "mrp_paise"
        ] = int(mrp_paise)

    if stock is not None:
        if stock < 0:
            raise ValueError(
                "Stock cannot be negative."
            )

        updates[
            "stock"
        ] = int(stock)

    if unit is not None:
        updates[
            "unit"
        ] = unit.strip()

    if description is not None:
        updates[
            "description"
        ] = description.strip()

    if image is not None:
        updates[
            "image"
        ] = image.strip() or None

    if tags is not None:
        updates[
            "tags"
        ] = sorted(
            {
                str(tag)
                .strip()
                .lower()
                for tag in tags
                if str(tag).strip()
            }
        )

    if active is not None:
        updates[
            "active"
        ] = bool(active)

    updated = await db.products.find_one_and_update(
        {
            "_id":
                product_id,
            "merchant_id":
                settings.merchant_id,
        },
        {
            "$set":
                updates,
        },
        return_document=
            ReturnDocument.AFTER,
    )

    if not updated:
        raise ValueError(
            "Product not found."
        )

    return public_product(
        updated
    )


async def admin_delete_product(
    product_id: str,
) -> dict[str, Any]:

    db = get_db()

    product = await db.products.find_one_and_update(
        {
            "_id":
                product_id,
            "merchant_id":
                settings.merchant_id,
        },
        {
            "$set": {
                "active":
                    False,
                "updated_at":
                    utc_now(),
            }
        },
        return_document=
            ReturnDocument.AFTER,
    )

    if not product:
        raise ValueError(
            "Product not found."
        )

    return public_product(
        product
    )


async def admin_list_orders(
    *,
    status: str | None = None,
    payment_status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:

    db = get_db()

    query: dict[str, Any] = {
        "merchant_id":
            settings.merchant_id,
    }

    if status:
        query[
            "status"
        ] = status

    if payment_status:
        query[
            "payment_status"
        ] = payment_status

    orders = await (
        db.orders
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            max(
                1,
                min(
                    int(limit),
                    500,
                ),
            )
        )
        .to_list(
            length=500
        )
    )

    return [
        {
            "id":
                order["_id"],
            "owner_clerk_user_id":
                order.get(
                    "owner_clerk_user_id"
                ),
            "agent_id":
                order.get(
                    "agent_id"
                ),
            "status":
                order.get(
                    "status"
                ),
            "payment_status":
                order.get(
                    "payment_status"
                ),
            "payment_method":
                order.get(
                    "payment_method"
                ),
            "amount_paise":
                int(
                    order.get(
                        "amount_paise",
                        0,
                    )
                ),
            "amount":
                _money(
                    order.get(
                        "amount_paise",
                        0,
                    )
                ),
            "currency":
                order.get(
                    "currency",
                    "INR",
                ),
            "items":
                order.get(
                    "items",
                    [],
                ),
            "created_at":
                order.get(
                    "created_at"
                ),
            "updated_at":
                order.get(
                    "updated_at"
                ),
        }
        for order in orders
    ]


async def admin_list_payments(
    *,
    status: str | None = None,
    payment_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:

    db = get_db()

    query: dict[str, Any] = {}

    if status:
        query[
            "status"
        ] = status

    if payment_type:
        query[
            "type"
        ] = payment_type

    payments = await (
        db.payments
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            max(
                1,
                min(
                    int(limit),
                    500,
                ),
            )
        )
        .to_list(
            length=500
        )
    )

    return [
        {
            "id":
                payment["_id"],
            "type":
                payment.get(
                    "type"
                ),
            "status":
                payment.get(
                    "status"
                ),
            "agent_id":
                payment.get(
                    "agent_id"
                ),
            "order_id":
                payment.get(
                    "order_id"
                ),
            "owner_clerk_user_id":
                payment.get(
                    "owner_clerk_user_id"
                ),
            "amount_paise":
                int(
                    payment.get(
                        "amount_paise",
                        0,
                    )
                ),
            "amount":
                _money(
                    payment.get(
                        "amount_paise",
                        0,
                    )
                ),
            "provider_payment_id":
                payment.get(
                    "provider_payment_id"
                ),
            "razorpay_order_id":
                payment.get(
                    "razorpay_order_id"
                ),
            "created_at":
                payment.get(
                    "created_at"
                ),
            "updated_at":
                payment.get(
                    "updated_at"
                ),
        }
        for payment in payments
    ]

async def admin_list_users(
    *,
    query: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:

    db = get_db()

    mongo_query: dict[str, Any] = {}

    query = query.strip()

    if query:
        mongo_query["$or"] = [
            {
                "clerk_user_id": {
                    "$regex": query,
                    "$options": "i",
                }
            },
            {
                "email": {
                    "$regex": query,
                    "$options": "i",
                }
            },
        ]

    limit = max(
        1,
        min(int(limit), 500),
    )

    users = await (
        db.users
        .find(mongo_query)
        .sort(
            "created_at",
            -1,
        )
        .limit(limit)
        .to_list(
            length=limit,
        )
    )

    return [
        {
            # IMPORTANT:
            # MongoDB ObjectId must be converted to string
            # before FastAPI serializes the response.
            "id": str(user["_id"]),

            "clerk_user_id": user.get(
                "clerk_user_id"
            ),

            "email": user.get(
                "email"
            ),

            "status": user.get(
                "status",
                "ACTIVE",
            ),

            "created_at": user.get(
                "created_at"
            ),

            "updated_at": user.get(
                "updated_at"
            ),
        }
        for user in users
    ]


async def admin_list_agents(
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:

    db = get_db()

    query: dict[str, Any] = {
        "merchant_id":
            settings.merchant_id,
    }

    if status:
        query[
            "status"
        ] = status

    agents = await (
        db.agents
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            max(
                1,
                min(
                    int(limit),
                    500,
                ),
            )
        )
        .to_list(
            length=500
        )
    )

    return [
        public_agent(
            agent
        )
        for agent in agents
    ]


async def admin_audit(
    *,
    result: str | None = None,
    action: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:

    db = get_db()

    query: dict[str, Any] = {}

    if result:
        query[
            "result"
        ] = result

    if action:
        query[
            "action"
        ] = action

    events = await (
        db.audit_events
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            max(
                1,
                min(
                    int(limit),
                    500,
                ),
            )
        )
        .to_list(
            length=500
        )
    )

    return [
        {
            "id":
                event["_id"],
            "owner_clerk_user_id":
                event.get(
                    "owner_clerk_user_id"
                ),
            "agent_id":
                event.get(
                    "agent_id"
                ),
            "action":
                event.get(
                    "action"
                ),
            "result":
                event.get(
                    "result"
                ),
            "amount_paise":
                event.get(
                    "amount_paise"
                ),
            "amount":
                (
                    _money(
                        event[
                            "amount_paise"
                        ]
                    )
                    if event.get(
                        "amount_paise"
                    ) is not None
                    else None
                ),
            "reason":
                event.get(
                    "reason"
                ),
            "metadata":
                event.get(
                    "metadata",
                    {},
                ),
            "created_at":
                event.get(
                    "created_at"
                ),
        }
        for event in events
    ]
# ============================================================
# END OF SERVICES
# ============================================================