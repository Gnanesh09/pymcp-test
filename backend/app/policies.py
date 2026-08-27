from typing import Any

from fastapi import HTTPException

from .db import get_db, utc_now


async def evaluate_purchase(
    *,
    user_id: str,
    agent: dict[str, Any],
    amount_paise: int,
    categories: list[str],
    merchant: dict[str, Any],
    confirmed: bool = False,
) -> dict[str, Any]:
    if agent.get("status") != "ACTIVE":
        return {
            "decision": "BLOCK",
            "code": "AGENT_DISABLED",
            "reason": "This purchasing agent is not active.",
        }

    policy = agent.get("policy", {})

    if not policy.get("auto_purchase", False) and not confirmed:
        return {
            "decision": "CONFIRM",
            "code": "USER_CONFIRMATION_REQUIRED",
            "reason": "This agent requires explicit confirmation before purchase.",
        }

    max_txn = int(policy.get("max_transaction_paise", 0))
    if amount_paise > max_txn:
        return {
            "decision": "BLOCK",
            "code": "TRANSACTION_LIMIT_EXCEEDED",
            "reason": (
                f"Order value is ₹{amount_paise / 100:.2f}, "
                f"above the agent transaction limit of ₹{max_txn / 100:.2f}."
            ),
            "limit_paise": max_txn,
            "requested_paise": amount_paise,
        }

    available = int(agent.get("balance_available_paise", 0))
    if amount_paise > available:
        return {
            "decision": "BLOCK",
            "code": "INSUFFICIENT_AGENT_BALANCE",
            "reason": (
                f"Agent balance is ₹{available / 100:.2f}; "
                f"the purchase requires ₹{amount_paise / 100:.2f}."
            ),
            "balance_paise": available,
            "requested_paise": amount_paise,
        }

    daily_limit = int(policy.get("daily_limit_paise", 0))
    spent_today = int(agent.get("spent_today_paise", 0))
    if spent_today + amount_paise > daily_limit:
        remaining = max(0, daily_limit - spent_today)
        return {
            "decision": "BLOCK",
            "code": "DAILY_LIMIT_EXCEEDED",
            "reason": (
                f"Daily spending limit would be exceeded. "
                f"Remaining today: ₹{remaining / 100:.2f}."
            ),
            "daily_limit_paise": daily_limit,
            "spent_today_paise": spent_today,
            "remaining_paise": remaining,
        }

    allowed_categories = {
        str(x).lower()
        for x in policy.get("allowed_categories", [])
    }
    blocked_categories = {
        str(x).lower()
        for x in policy.get("blocked_categories", [])
    }

    normalized_categories = {
        str(x).lower()
        for x in categories
    }

    if blocked_categories & normalized_categories:
        blocked = sorted(blocked_categories & normalized_categories)
        return {
            "decision": "BLOCK",
            "code": "CATEGORY_BLOCKED",
            "reason": f"Blocked categories: {', '.join(blocked)}.",
        }

    if allowed_categories and not normalized_categories.issubset(
        allowed_categories
    ):
        missing = sorted(normalized_categories - allowed_categories)
        return {
            "decision": "BLOCK",
            "code": "CATEGORY_NOT_ALLOWED",
            "reason": f"Categories not allowed: {', '.join(missing)}.",
        }

    if not merchant.get("ai_purchasing", False):
        return {
            "decision": "BLOCK",
            "code": "MERCHANT_AI_PURCHASING_DISABLED",
            "reason": "The merchant has disabled AI purchasing.",
        }

    merchant_max = int(merchant.get("max_order_value", 0))
    if amount_paise > merchant_max:
        return {
            "decision": "BLOCK",
            "code": "MERCHANT_ORDER_LIMIT_EXCEEDED",
            "reason": (
                f"Order exceeds the merchant AI order limit of "
                f"₹{merchant_max / 100:.2f}."
            ),
        }

    return {
        "decision": "ALLOW",
        "code": "POLICY_ALLOWED",
        "reason": [
            "Agent is active.",
            "Auto-purchase is enabled.",
            "Transaction is within the agent limit.",
            "Agent has sufficient available balance.",
            "Daily spending limit is satisfied.",
            "Categories are allowed.",
            "Merchant permits AI purchasing.",
            "Merchant order limit is satisfied.",
        ],
    }


async def reserve_agent_balance(
    *,
    agent_id: str,
    owner_clerk_user_id: str,
    amount_paise: int,
    reservation_id: str,
) -> dict[str, Any]:
    db = get_db()

    agent = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
            "status": "ACTIVE",
            "balance_available_paise": {"$gte": amount_paise},
        },
        {
            "$inc": {
                "balance_available_paise": -amount_paise,
                "balance_reserved_paise": amount_paise,
            },
            "$set": {"updated_at": utc_now()},
        },
        return_document=True,
    )

    if not agent:
        raise HTTPException(
            status_code=409,
            detail="Agent balance became unavailable during reservation.",
        )

    return agent


async def release_agent_balance(
    *,
    agent_id: str,
    owner_clerk_user_id: str,
    amount_paise: int,
) -> dict[str, Any]:
    db = get_db()

    agent = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
            "balance_reserved_paise": {"$gte": amount_paise},
        },
        {
            "$inc": {
                "balance_available_paise": amount_paise,
                "balance_reserved_paise": -amount_paise,
            },
            "$set": {"updated_at": utc_now()},
        },
        return_document=True,
    )

    if not agent:
        raise HTTPException(
            status_code=500,
            detail="Unable to release reserved agent balance.",
        )

    return agent


async def commit_agent_balance(
    *,
    agent_id: str,
    owner_clerk_user_id: str,
    amount_paise: int,
) -> dict[str, Any]:
    db = get_db()

    agent = await db.agents.find_one_and_update(
        {
            "_id": agent_id,
            "owner_clerk_user_id": owner_clerk_user_id,
            "balance_reserved_paise": {"$gte": amount_paise},
        },
        {
            "$inc": {
                "balance_reserved_paise": -amount_paise,
                "spent_today_paise": amount_paise,
                "lifetime_spent_paise": amount_paise,
            },
            "$set": {"updated_at": utc_now()},
        },
        return_document=True,
    )

    if not agent:
        raise HTTPException(
            status_code=500,
            detail="Unable to commit reserved agent balance.",
        )

    return agent
