from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import ReturnDocument

from .db import get_db, utc_now


# ============================================================
# DAILY SPENDING
# ============================================================

async def daily_spend_paise(
    agent_id: str,
    owner_clerk_user_id: str,
) -> int:
    db = get_db()

    start = datetime.now(
        timezone.utc
    ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    cursor = await db.ledger_entries.aggregate(
        [
            {
                "$match": {
                    "agent_id": agent_id,
                    "owner_clerk_user_id":
                        owner_clerk_user_id,
                    "type": "DEBIT",
                    "created_at": {
                        "$gte": start,
                    },
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

    result = await cursor.to_list(
        length=1
    )

    if not result:
        return 0

    return int(
        result[0].get(
            "total",
            0,
        )
    )


# ============================================================
# PURCHASE POLICY
# ============================================================

async def evaluate_purchase(
    *,
    agent: dict[str, Any],
    amount_paise: int,
    categories: list[str],
    merchant: dict[str, Any],
    confirmed: bool = False,
) -> dict[str, Any]:

    # --------------------------------------------------------
    # Amount
    # --------------------------------------------------------

    if amount_paise <= 0:
        return {
            "decision": "BLOCK",
            "code": "INVALID_AMOUNT",
            "reason":
                "Purchase amount must be greater than zero.",
        }

    # --------------------------------------------------------
    # Agent
    # --------------------------------------------------------

    if agent.get("status") != "ACTIVE":
        return {
            "decision": "BLOCK",
            "code": "AGENT_DISABLED",
            "reason":
                "This purchasing agent is not active.",
        }

    policy = agent.get(
        "policy",
        {},
    )

    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    auto_purchase = bool(
        policy.get(
            "auto_purchase",
            False,
        )
    )

    if (
        not auto_purchase
        and not confirmed
    ):
        return {
            "decision": "CONFIRM",
            "code":
                "USER_CONFIRMATION_REQUIRED",
            "reason":
                "This agent requires explicit confirmation before purchase.",
        }

    # --------------------------------------------------------
    # Transaction limit
    # --------------------------------------------------------

    max_transaction_paise = int(
        policy.get(
            "max_transaction_paise",
            0,
        )
    )

    if max_transaction_paise <= 0:
        return {
            "decision": "BLOCK",
            "code":
                "TRANSACTION_LIMIT_NOT_CONFIGURED",
            "reason":
                "The agent transaction limit is not configured.",
        }

    if (
        amount_paise
        > max_transaction_paise
    ):
        return {
            "decision": "BLOCK",
            "code":
                "TRANSACTION_LIMIT_EXCEEDED",
            "reason": (
                f"Order value is "
                f"₹{amount_paise / 100:.2f}, "
                f"above the agent transaction "
                f"limit of "
                f"₹{max_transaction_paise / 100:.2f}."
            ),
            "limit_paise":
                max_transaction_paise,
            "requested_paise":
                amount_paise,
        }

    # --------------------------------------------------------
    # Balance
    # --------------------------------------------------------

    available_paise = int(
        agent.get(
            "balance_available_paise",
            0,
        )
    )

    if (
        amount_paise
        > available_paise
    ):
        return {
            "decision": "BLOCK",
            "code":
                "INSUFFICIENT_AGENT_BALANCE",
            "reason": (
                f"Agent balance is "
                f"₹{available_paise / 100:.2f}; "
                f"the purchase requires "
                f"₹{amount_paise / 100:.2f}."
            ),
            "balance_paise":
                available_paise,
            "requested_paise":
                amount_paise,
        }

    # --------------------------------------------------------
    # Daily limit
    # --------------------------------------------------------

    daily_limit_paise = int(
        policy.get(
            "daily_limit_paise",
            0,
        )
    )

    if daily_limit_paise <= 0:
        return {
            "decision": "BLOCK",
            "code":
                "DAILY_LIMIT_NOT_CONFIGURED",
            "reason":
                "The agent daily spending limit is not configured.",
        }

    owner_clerk_user_id = agent.get(
        "owner_clerk_user_id"
    )

    if not owner_clerk_user_id:
        return {
            "decision": "BLOCK",
            "code":
                "AGENT_OWNER_MISSING",
            "reason":
                "The agent owner identity is missing.",
        }

    spent_today_paise = (
        await daily_spend_paise(
            agent["_id"],
            owner_clerk_user_id,
        )
    )

    remaining_paise = max(
        0,
        daily_limit_paise
        - spent_today_paise,
    )

    if (
        spent_today_paise
        + amount_paise
        > daily_limit_paise
    ):
        return {
            "decision": "BLOCK",
            "code":
                "DAILY_LIMIT_EXCEEDED",
            "reason": (
                "Daily spending limit would "
                "be exceeded. "
                f"Remaining today: "
                f"₹{remaining_paise / 100:.2f}."
            ),
            "daily_limit_paise":
                daily_limit_paise,
            "spent_today_paise":
                spent_today_paise,
            "remaining_paise":
                remaining_paise,
            "requested_paise":
                amount_paise,
        }

    # --------------------------------------------------------
    # CATEGORY POLICY
    # --------------------------------------------------------

    normalized_categories = {
        str(value)
        .strip()
        .lower()
        for value in categories
        if str(value).strip()
    }

    category_mode = str(
        policy.get(
            "category_mode",
            "ALL",
        )
    ).strip().upper()

    allowed_categories = {
        str(value)
        .strip()
        .lower()
        for value in policy.get(
            "allowed_categories",
            [],
        )
        if str(value).strip()
    }

    blocked_categories = {
        str(value)
        .strip()
        .lower()
        for value in policy.get(
            "blocked_categories",
            [],
        )
        if str(value).strip()
    }

    # Invalid policy should fail closed.
    if category_mode not in {
        "ALL",
        "SELECTED",
    }:
        return {
            "decision": "BLOCK",
            "code":
                "INVALID_CATEGORY_POLICY",
            "reason":
                "Agent category policy is invalid.",
        }

    # Blocked categories always win.
    blocked_hit = (
        normalized_categories
        & blocked_categories
    )

    if blocked_hit:
        blocked = sorted(
            blocked_hit
        )

        return {
            "decision": "BLOCK",
            "code":
                "CATEGORY_BLOCKED",
            "reason": (
                "Blocked categories: "
                + ", ".join(blocked)
                + "."
            ),
            "blocked_categories":
                blocked,
        }

    # SELECTED means only selected categories.
    if category_mode == "SELECTED":

        if not allowed_categories:
            return {
                "decision":
                    "BLOCK",
                "code":
                    "CATEGORY_POLICY_EMPTY",
                "reason":
                    "This agent is configured for selected categories but none are selected.",
            }

        not_allowed = sorted(
            normalized_categories
            - allowed_categories
        )

        if not_allowed:
            return {
                "decision":
                    "BLOCK",
                "code":
                    "CATEGORY_NOT_ALLOWED",
                "reason": (
                    "Categories not allowed: "
                    + ", ".join(
                        not_allowed
                    )
                    + "."
                ),
                "not_allowed":
                    not_allowed,
            }

    # ALL mode permits every category except explicit blocks.

    # --------------------------------------------------------
    # MERCHANT POLICY
    # --------------------------------------------------------

    if not merchant:
        return {
            "decision":
                "BLOCK",
            "code":
                "MERCHANT_UNAVAILABLE",
            "reason":
                "Merchant configuration is unavailable.",
        }

    if not merchant.get(
        "ai_purchasing",
        False,
    ):
        return {
            "decision":
                "BLOCK",
            "code":
                "MERCHANT_AI_PURCHASING_DISABLED",
            "reason":
                "The merchant has disabled AI purchasing.",
        }

    if not merchant.get(
        "ai_checkout",
        False,
    ):
        return {
            "decision":
                "BLOCK",
            "code":
                "MERCHANT_AI_CHECKOUT_DISABLED",
            "reason":
                "The merchant has disabled AI checkout.",
        }

    merchant_max_paise = int(
        merchant.get(
            "max_order_value",
            0,
        )
    )

    if (
        merchant_max_paise <= 0
        or amount_paise
        > merchant_max_paise
    ):
        return {
            "decision":
                "BLOCK",
            "code":
                "MERCHANT_ORDER_LIMIT_EXCEEDED",
            "reason": (
                "Order exceeds the merchant AI "
                "order limit."
            ),
            "merchant_limit_paise":
                merchant_max_paise,
            "requested_paise":
                amount_paise,
        }

    # --------------------------------------------------------
    # ALLOW
    # --------------------------------------------------------

    return {
        "decision":
            "ALLOW",

        "code":
            "POLICY_ALLOWED",

        "reason": [
            "Agent is active.",

            (
                "Purchase was explicitly confirmed."
                if confirmed
                else
                "Agent auto-purchase policy permits the purchase."
            ),

            "Transaction is within the agent limit.",

            "Agent has sufficient available balance.",

            "Daily spending limit is satisfied.",

            "Category policy is satisfied.",

            "Merchant permits AI purchasing.",

            "Merchant permits AI checkout.",

            "Merchant order limit is satisfied.",
        ],

        "spent_today_paise":
            spent_today_paise,

        "daily_remaining_paise":
            remaining_paise,
    }


# ============================================================
# RESERVE
# ============================================================

async def reserve_agent_balance(
    *,
    agent_id: str,
    owner_clerk_user_id: str,
    amount_paise: int,
) -> dict[str, Any]:

    if amount_paise <= 0:
        raise HTTPException(
            400,
            "Reservation amount must be greater than zero.",
        )

    db = get_db()

    agent = await db.agents.find_one_and_update(
        {
            "_id":
                agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "status":
                "ACTIVE",
            "balance_available_paise":
                {
                    "$gte":
                        amount_paise,
                },
        },
        {
            "$inc": {
                "balance_available_paise":
                    -amount_paise,
                "balance_reserved_paise":
                    amount_paise,
            },
            "$set": {
                "updated_at":
                    utc_now(),
            },
        },
        return_document=
            ReturnDocument.AFTER,
    )

    if not agent:
        raise HTTPException(
            409,
            "Agent balance became unavailable during reservation.",
        )

    return agent


# ============================================================
# RELEASE
# ============================================================

async def release_agent_balance(
    *,
    agent_id: str,
    owner_clerk_user_id: str,
    amount_paise: int,
) -> dict[str, Any]:

    if amount_paise <= 0:
        raise HTTPException(
            400,
            "Release amount must be greater than zero.",
        )

    db = get_db()

    agent = await db.agents.find_one_and_update(
        {
            "_id":
                agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "balance_reserved_paise":
                {
                    "$gte":
                        amount_paise,
                },
        },
        {
            "$inc": {
                "balance_available_paise":
                    amount_paise,
                "balance_reserved_paise":
                    -amount_paise,
            },
            "$set": {
                "updated_at":
                    utc_now(),
            },
        },
        return_document=
            ReturnDocument.AFTER,
    )

    if not agent:
        raise HTTPException(
            500,
            "Unable to release reserved agent balance.",
        )

    return agent


# ============================================================
# COMMIT
# ============================================================

async def commit_agent_balance(
    *,
    agent_id: str,
    owner_clerk_user_id: str,
    amount_paise: int,
) -> dict[str, Any]:

    if amount_paise <= 0:
        raise HTTPException(
            400,
            "Commit amount must be greater than zero.",
        )

    db = get_db()

    agent = await db.agents.find_one_and_update(
        {
            "_id":
                agent_id,
            "owner_clerk_user_id":
                owner_clerk_user_id,
            "balance_reserved_paise":
                {
                    "$gte":
                        amount_paise,
                },
        },
        {
            "$inc": {
                "balance_reserved_paise":
                    -amount_paise,
                "lifetime_spent_paise":
                    amount_paise,
            },
            "$set": {
                "updated_at":
                    utc_now(),
            },
        },
        return_document=
            ReturnDocument.AFTER,
    )

    if not agent:
        raise HTTPException(
            500,
            "Unable to commit reserved agent balance.",
        )

    return agent