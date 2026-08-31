from __future__ import annotations

"""
Umon LangGraph shopping orchestration.

This graph intentionally contains NO LLM and NO money-moving authority.
ChatGPT remains the reasoning/client layer. LangGraph provides a deterministic,
observable workflow for Umon's shopping assistance:

intent -> cart -> live catalog -> cross-sell -> budget/agent awareness -> plan

The final purchase decision remains in Umon's existing policy engine and
checkout service. The graph can recommend and prepare, but cannot manufacture
a price, bypass policy, reserve funds, or complete a payment.
"""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import settings
from .db import get_db
from .services import (
    agent_stats,
    get_cart,
    get_owned_agent,
    get_recommendations,
    search_products,
)


class ShoppingState(TypedDict, total=False):
    user_id: str
    intent: str
    budget_paise: int | None
    requested_category: str | None

    cart: dict[str, Any]
    cart_product_ids: set[str]

    candidate_products: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    suggestion_items: list[dict[str, Any]]
    suggestion_total_paise: int

    selected_agent_id: str | None
    agent: dict[str, Any] | None
    agent_spending: dict[str, Any] | None

    merchant: dict[str, Any] | None
    next_action: str
    explanation: str
    warnings: list[str]
    trace: list[str]


def _money(paise: int) -> float:
    return round(int(paise) / 100, 2)


def _text_product(product: dict[str, Any]) -> str:
    return " ".join(
        [
            str(product.get("name", "")),
            str(product.get("brand", "")),
            str(product.get("category", "")),
            str(product.get("description", "")),
            " ".join(
                str(tag)
                for tag in product.get("tags", [])
            ),
        ]
    ).lower()


def _infer_category(intent: str) -> str | None:
    text = intent.lower()

    aliases = {
        "grocery": (
            "grocery", "groceries", "atta", "salt",
        ),
        "dairy": (
            "dairy", "milk", "butter",
        ),
        "snacks": (
            "snack", "snacks", "chips", "maggi",
            "noodles",
        ),
        "beverages": (
            "drink", "drinks", "beverage",
            "beverages", "coke", "cola",
        ),
        "household": (
            "household", "detergent", "washing",
        ),
        "personal-care": (
            "personal care", "toothpaste",
            "toothbrush",
        ),
    }

    for category, words in aliases.items():
        if any(word in text for word in words):
            return category

    return None


def _score_product(
    product: dict[str, Any],
    intent_terms: list[str],
) -> int:
    searchable = _text_product(product)

    score = 0
    for term in intent_terms:
        if term and term in searchable:
            score += 2

    # Rating is useful as a tie breaker but is deliberately not
    # allowed to overwhelm intent relevance.
    try:
        score += min(
            int(float(product.get("rating", 0))),
            5,
        )
    except (TypeError, ValueError):
        pass

    return score


async def load_context(
    state: ShoppingState,
) -> dict[str, Any]:
    cart = await get_cart(state["user_id"])

    db = get_db()
    merchant = await db.merchants.find_one(
        {
            "_id": settings.merchant_id,
        }
    )

    return {
        "cart": cart,
        "cart_product_ids": {
            str(item.get("product_id"))
            for item in cart.get("items", [])
        },
        "merchant": merchant,
        "trace": state.get("trace", []) + [
            "Loaded current shared cart and merchant state."
        ],
    }


async def discover_products(
    state: ShoppingState,
) -> dict[str, Any]:
    intent = state.get("intent", "").strip()
    category = (
        state.get("requested_category")
        or _infer_category(intent)
    )

    # Keep query conservative. Umon's existing search service is
    # authoritative for active products and current prices.
    candidates = await search_products(
        query=intent,
        category=category,
        max_price_paise=state.get(
            "budget_paise"
        ),
        limit=20,
    )

    # If semantic-ish matching returns nothing, query category/all
    # and locally rank against the intent.
    if not candidates:
        candidates = await search_products(
            query="",
            category=category,
            max_price_paise=state.get(
                "budget_paise"
            ),
            limit=50,
        )

    terms = [
        part.strip().lower()
        for part in intent.split()
        if len(part.strip()) >= 2
    ]

    ranked = sorted(
        candidates,
        key=lambda product: -_score_product(
            product,
            terms,
        ),
    )

    return {
        "candidate_products": ranked[:12],
        "trace": state.get("trace", []) + [
            f"Discovered {len(ranked[:12])} relevant live offers."
        ],
    }


async def cross_sell(
    state: ShoppingState,
) -> dict[str, Any]:
    cart = state.get("cart", {})
    cart_ids = state.get(
        "cart_product_ids",
        set(),
    )

    recommendations: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Prefer the user's existing cart because cross-selling should
    # complete the user's current basket, not replace it.
    source_ids = [
        str(item.get("product_id"))
        for item in cart.get("items", [])
    ]

    if not source_ids:
        source_ids = [
            str(product.get("id"))
            for product in state.get(
                "candidate_products",
                [],
            )[:3]
        ]

    for product_id in source_ids:
        for product in await get_recommendations(
            product_id
        ):
            product_id_out = str(
                product.get("id")
            )

            if (
                product_id_out in cart_ids
                or product_id_out in seen
            ):
                continue

            recommendations.append(product)
            seen.add(product_id_out)

            if len(recommendations) >= 8:
                break

        if len(recommendations) >= 8:
            break

    return {
        "recommendations": recommendations,
        "trace": state.get("trace", []) + [
            f"Found {len(recommendations)} complementary offers."
        ],
    }


async def build_suggestion(
    state: ShoppingState,
) -> dict[str, Any]:
    """
    Build a small, explainable suggestion set.

    This is not an autonomous purchase. It is a recommendation plan.
    We favor products relevant to intent, then one or two complements.
    """
    budget = state.get("budget_paise")

    pool: list[dict[str, Any]] = []

    for product in state.get(
        "candidate_products",
        [],
    ):
        pool.append(product)

    for product in state.get(
        "recommendations",
        [],
    ):
        if product not in pool:
            pool.append(product)

    # Never recommend an item already in the cart.
    cart_ids = state.get(
        "cart_product_ids",
        set(),
    )

    pool = [
        product
        for product in pool
        if str(product.get("id"))
        not in cart_ids
    ]

    chosen: list[dict[str, Any]] = []
    total = 0

    # First choose the strongest directly relevant product.
    if pool:
        first = pool[0]
        first_price = int(
            first.get(
                "price_paise",
                0,
            )
        )

        if budget is None or first_price <= budget:
            chosen.append(first)
            total += first_price

    # Add at most two complementary items while respecting budget.
    for product in pool[1:]:
        if len(chosen) >= 3:
            break

        price = int(
            product.get(
                "price_paise",
                0,
            )
        )

        if (
            budget is not None
            and total + price > budget
        ):
            continue

        chosen.append(product)
        total += price

    warnings = list(
        state.get("warnings", [])
    )

    if not chosen:
        warnings.append(
            "No recommended basket fits the requested budget."
        )

    return {
        "suggestion_items": chosen,
        "suggestion_total_paise": total,
        "warnings": warnings,
        "next_action": (
            "present_recommendations"
            if chosen
            else "ask_for_more_context"
        ),
        "explanation": (
            "Recommendations prioritize the user's stated intent, "
            "current basket context and merchant-defined complementary products."
        ),
        "trace": state.get("trace", []) + [
            f"Built a {len(chosen)}-item recommendation plan."
        ],
    }


async def load_agent_context(
    state: ShoppingState,
) -> dict[str, Any]:
    agent_id = state.get(
        "selected_agent_id"
    )

    if not agent_id:
        return {
            "agent": None,
            "agent_spending": None,
            "trace": state.get("trace", []) + [
                "No purchasing agent selected; recommendation remains payment-agnostic."
            ],
        }

    agent = await get_owned_agent(
        state["user_id"],
        agent_id,
    )

    if not agent:
        return {
            "agent": None,
            "agent_spending": None,
            "warnings": state.get("warnings", []) + [
                "Selected purchasing agent was not found or is not owned by the user."
            ],
            "next_action": "choose_agent",
            "trace": state.get("trace", []) + [
                "Rejected unowned or missing purchasing agent."
            ],
        }

    try:
        spending = await agent_stats(
            state["user_id"],
            agent_id,
        )
    except ValueError:
        spending = None

    return {
        "agent": agent,
        "agent_spending": spending,
        "trace": state.get("trace", []) + [
            "Loaded the selected agent's current balance and limits."
        ],
    }


def agent_affordability(
    state: ShoppingState,
) -> dict[str, Any]:
    """
    Advisory only. This never authorizes a purchase.
    """
    agent = state.get("agent")
    spending = state.get("agent_spending")

    if not agent or not spending:
        return {}

    total = int(
        state.get(
            "suggestion_total_paise",
            0,
        )
    )

    if total <= 0:
        return {}

    warnings = list(
        state.get("warnings", [])
    )

    balance = int(
        spending.get(
            "balance",
            {},
        ).get(
            "available_paise",
            agent.get(
                "balance_available_paise",
                0,
            ),
        )
    )

    daily_remaining = int(
        spending.get(
            "spending",
            {},
        ).get(
            "daily_remaining_paise",
            0,
        )
    )

    tx_limit = int(
        spending.get(
            "limits",
            {},
        ).get(
            "transaction_paise",
            agent.get(
                "policy",
                {},
            ).get(
                "max_transaction_paise",
                0,
            ),
        )
    )

    if total > balance:
        warnings.append(
            "Suggested basket exceeds the selected agent's available balance."
        )

    if total > tx_limit:
        warnings.append(
            "Suggested basket exceeds the selected agent's per-transaction limit."
        )

    if total > daily_remaining:
        warnings.append(
            "Suggested basket would exceed the selected agent's remaining daily limit."
        )

    return {
        "warnings": warnings,
        "trace": state.get("trace", []) + [
            "Compared the suggestion against current agent constraints without moving money."
        ],
    }


def final_plan(
    state: ShoppingState,
) -> dict[str, Any]:
    if state.get("warnings"):
        explanation = (
            state.get(
                "explanation",
                "",
            )
            + " "
            + " ".join(
                state["warnings"]
            )
        ).strip()
    else:
        explanation = state.get(
            "explanation",
            "",
        )

    return {
        "explanation": explanation,
        "next_action": state.get(
            "next_action",
            "present_recommendations",
        ),
        "trace": state.get("trace", []) + [
            "Completed shopping-assistance graph."
        ],
    }


builder = StateGraph(ShoppingState)

builder.add_node(
    "load_context",
    load_context,
)
builder.add_node(
    "discover_products",
    discover_products,
)
builder.add_node(
    "cross_sell",
    cross_sell,
)
builder.add_node(
    "build_suggestion",
    build_suggestion,
)
builder.add_node(
    "load_agent_context",
    load_agent_context,
)
builder.add_node(
    "agent_affordability",
    agent_affordability,
)
builder.add_node(
    "final_plan",
    final_plan,
)

builder.add_edge(
    START,
    "load_context",
)
builder.add_edge(
    "load_context",
    "discover_products",
)
builder.add_edge(
    "discover_products",
    "cross_sell",
)
builder.add_edge(
    "cross_sell",
    "build_suggestion",
)
builder.add_edge(
    "build_suggestion",
    "load_agent_context",
)
builder.add_edge(
    "load_agent_context",
    "agent_affordability",
)
builder.add_edge(
    "agent_affordability",
    "final_plan",
)
builder.add_edge(
    "final_plan",
    END,
)

shopping_graph = builder.compile()


async def run_shopping_assistant(
    *,
    user_id: str,
    intent: str,
    budget_paise: int | None = None,
    category: str | None = None,
    selected_agent_id: str | None = None,
) -> dict[str, Any]:
    """
    Run the deterministic Umon shopping workflow.

    Returns recommendation state suitable for an MCP tool response/UI.
    """
    if not intent.strip():
        raise ValueError(
            "Shopping intent is required."
        )

    result = await shopping_graph.ainvoke(
        {
            "user_id": user_id,
            "intent": intent.strip(),
            "budget_paise": budget_paise,
            "requested_category": category,
            "selected_agent_id": selected_agent_id,
        }
    )

    return result


def graph_description() -> dict[str, Any]:
    return {
        "name": "Umon Shopping Graph",
        "nodes": [
            "load_context",
            "discover_products",
            "cross_sell",
            "build_suggestion",
            "load_agent_context",
            "agent_affordability",
            "final_plan",
        ],
        "money_movement": False,
        "authorization_authority": "Umon deterministic policy + checkout services",
    }