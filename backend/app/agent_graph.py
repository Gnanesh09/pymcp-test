from __future__ import annotations

import json, os
from typing import Any, TypedDict

from groq import AsyncGroq
from langgraph.graph import END, START, StateGraph

from .services import (
    agent_stats, get_cart, get_owned_agent, get_recommendations, search_products
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "").strip()
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))

_client = (
    AsyncGroq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT_SECONDS)
    if GROQ_API_KEY else None
)


class AgentState(TypedDict, total=False):
    user_id: str
    message: str
    intent: str
    intent_type: str
    search_terms: list[str]
    requested_categories: list[str]
    budget_paise: int | None
    party_size: int | None
    cart: dict[str, Any]
    agent: dict[str, Any] | None
    agent_stats: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    cross_sell: list[dict[str, Any]]
    selected_ids: list[str]
    reasons: list[str]
    final_recommendations: list[dict[str, Any]]
    affordability: dict[str, Any] | None
    basket_gaps: list[str]
    warnings: list[str]
    actions: list[dict[str, Any]]
    answer: str
    trace: list[str]


def _money(paise: int) -> float:
    return round(int(paise) / 100, 2)


async def _json_call(*, system: str, user: str, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    if _client is None or not GROQ_MODEL:
        raise RuntimeError("GROQ_API_KEY and GROQ_MODEL must be configured.")

    response = await _client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Groq returned invalid structured output.")
    return data


async def understand(state: AgentState) -> dict[str, Any]:
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "intent": {"type": "string"},
            "intent_type": {"type": "string", "enum": ["DISCOVERY", "RECIPE", "CART_HELP", "PURCHASE"]},
            "search_terms": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
            "requested_categories": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "budget_paise": {"type": ["integer", "null"]},
            "party_size": {"type": ["integer", "null"]},
        },
        "required": ["intent", "intent_type", "search_terms", "requested_categories", "budget_paise", "party_size"],
    }
    data = await _json_call(
        system=(
            "Extract the shopping intent. Never invent catalog facts. "
            "For recipe requests, create concise ingredient/search terms that "
            "are useful hypotheses only; the live Umon catalog must verify them. "
            "Do not invent prices, stock, discounts, balances or payment state."
        ),
        user=state["message"],
        schema_name="umon_intent",
        schema=schema,
    )
    return {
        "intent": str(data["intent"]),
        "intent_type": str(data["intent_type"]),
        "search_terms": [str(x).strip() for x in data["search_terms"] if str(x).strip()],
        "requested_categories": [str(x).strip().lower() for x in data["requested_categories"] if str(x).strip()],
        "budget_paise": data["budget_paise"],
        "party_size": data["party_size"],
        "trace": state.get("trace", []) + ["Parsed intent with Groq; model output is treated as hypotheses only."],
    }


async def context(state: AgentState) -> dict[str, Any]:
    cart = await get_cart(state["user_id"])
    agent = None
    stats = None
    agent_id = state.get("selected_agent_id")
    if agent_id:
        agent = await get_owned_agent(state["user_id"], agent_id)
        if agent:
            try:
                stats = await agent_stats(state["user_id"], agent_id)
            except ValueError:
                stats = None
    return {
        "cart": cart,
        "agent": agent,
        "agent_stats": stats,
        "trace": state.get("trace", []) + ["Loaded live shared cart and selected agent context."],
    }


async def discover(state: AgentState) -> dict[str, Any]:
    found: dict[str, dict[str, Any]] = {}
    terms = state.get("search_terms", [])
    categories = state.get("requested_categories", [])
    category = categories[0] if len(categories) == 1 else None

    for term in terms[:12]:
        products = await search_products(
            query=term,
            category=category,
            max_price_paise=None,
            limit=12,
        )
        for p in products:
            pid = str(p.get("id") or "")
            if pid:
                found[pid] = p

    if not found:
        products = await search_products(
            query=state.get("intent", ""),
            category=category,
            max_price_paise=None,
            limit=20,
        )
        for p in products:
            pid = str(p.get("id") or "")
            if pid:
                found[pid] = p

    return {
        "candidates": list(found.values())[:40],
        "trace": state.get("trace", []) + [f"Fetched {len(found)} live catalogue candidates."],
    }


async def cross_sell(state: AgentState) -> dict[str, Any]:
    cart = state.get("cart", {})
    existing = {str(x.get("product_id")) for x in cart.get("items", [])}
    source_ids = [str(x.get("product_id")) for x in cart.get("items", []) if x.get("product_id")]

    if not source_ids:
        source_ids = [str(x.get("id")) for x in state.get("candidates", [])[:4] if x.get("id")]

    results = []
    seen = set()

    for source_id in source_ids:
        for p in await get_recommendations(source_id):
            pid = str(p.get("id") or "")
            if not pid or pid in existing or pid in seen:
                continue
            results.append({**p, "recommendation_source": "MERCHANT_CROSS_SELL", "source_product_id": source_id})
            seen.add(pid)
            if len(results) >= 12:
                break
        if len(results) >= 12:
            break

    return {
        "cross_sell": results,
        "trace": state.get("trace", []) + [f"Found {len(results)} merchant-defined cross-sell candidates."],
    }


async def rank(state: AgentState) -> dict[str, Any]:
    cart_ids = {str(x.get("product_id")) for x in state.get("cart", {}).get("items", [])}
    pool: dict[str, dict[str, Any]] = {}
    for p in state.get("candidates", []) + state.get("cross_sell", []):
        pid = str(p.get("id") or "")
        if pid and pid not in cart_ids and int(p.get("stock", 0) or 0) > 0:
            pool[pid] = p

    if not pool:
        return {"selected_ids": [], "reasons": [], "trace": state.get("trace", []) + ["No in-stock recommendation candidates were available."]}

    facts = [
        {k: p.get(k) for k in ("id", "name", "brand", "category", "price_paise", "stock", "recommendation_source", "reason")}
        for p in pool.values()
    ]

    data = await _json_call(
        system=(
            "Rank Umon shopping recommendations. You may select ONLY IDs in candidates. "
            "Return at most 3. Prefer direct relevance, then merchant-defined cross-sell, "
            "then reasonable price/stock. Never invent facts. Do not optimize for spend alone. "
            "The backend will verify every selected ID again."
        ),
        user=json.dumps({
            "request": state.get("intent", state["message"]),
            "budget_paise": state.get("budget_paise"),
            "party_size": state.get("party_size"),
            "cart": state.get("cart", {}).get("items", []),
            "candidates": facts,
        }, ensure_ascii=False),
        schema_name="umon_sales_plan",
        schema={
            "type": "object", "additionalProperties": False,
            "properties": {
                "selected_product_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            },
            "required": ["selected_product_ids", "reasons"],
        },
    )

    valid = set(pool)
    ids = [str(x) for x in data["selected_product_ids"] if str(x) in valid][:3]
    reasons = [str(x).strip() for x in data["reasons"] if str(x).strip()][:3]
    return {
        "selected_ids": ids,
        "reasons": reasons,
        "trace": state.get("trace", []) + [f"Groq selected {len(ids)} IDs from verified candidates."],
    }


def verify(state: AgentState) -> dict[str, Any]:
    pool = {str(p.get("id")): p for p in state.get("candidates", []) + state.get("cross_sell", [])}
    cart_ids = {str(x.get("product_id")) for x in state.get("cart", {}).get("items", [])}
    recommendations = []

    for i, pid in enumerate(state.get("selected_ids", [])):
        p = pool.get(pid)
        if not p or pid in cart_ids or int(p.get("stock", 0) or 0) <= 0:
            continue
        item = dict(p)
        item["verified_by"] = "Umon live catalogue"
        item["recommendation_reason"] = (
            state.get("reasons", [])[i]
            if i < len(state.get("reasons", []))
            else "Relevant to your shopping request."
        )
        recommendations.append(item)

    warnings = list(dict.fromkeys(state.get("warnings", [])))
    gaps = []
    for term in state.get("search_terms", []):
        term_lower = term.lower()
        matched = any(
            term_lower in str(p.get("name", "")).lower()
            or term_lower in " ".join(str(t) for t in p.get("tags", [])).lower()
            for p in state.get("candidates", [])
        )
        if not matched:
            gaps.append(f'No confirmed active Umon offer matched "{term}".')

    recommendations_total = sum(int(p.get("price_paise", 0) or 0) for p in recommendations)

    affordability = None
    stats = state.get("agent_stats")
    agent = state.get("agent")
    if agent and stats:
        available = int(stats.get("balance", {}).get("available_paise", agent.get("balance_available_paise", 0)) or 0)
        tx = int(stats.get("limits", {}).get("transaction_paise", agent.get("policy", {}).get("max_transaction_paise", 0)) or 0)
        daily = int(stats.get("spending", {}).get("daily_remaining_paise", 0) or 0)
        affordability = {
            "recommendation_total_paise": recommendations_total,
            "recommendation_total": _money(recommendations_total),
            "available_paise": available,
            "available": _money(available),
            "transaction_limit_paise": tx,
            "transaction_limit": _money(tx),
            "daily_remaining_paise": daily,
            "daily_remaining": _money(daily),
            "fits_balance": recommendations_total <= available,
            "fits_transaction": recommendations_total <= tx,
            "fits_daily": recommendations_total <= daily,
            "money_movement": False,
        }

    actions = [{"type": "ADD_TO_CART", "product_id": p["id"], "label": "Add to cart"} for p in recommendations]

    answer = (
        f"I checked the current Umon catalogue and found {len(recommendations)} verified recommendation"
        f"{'' if len(recommendations) == 1 else 's'}."
    )
    if gaps:
        answer += " " + " ".join(gaps[:3])
    if affordability and not all([
        affordability["fits_balance"],
        affordability["fits_transaction"],
        affordability["fits_daily"],
    ]):
        answer += " The selected agent cannot cover the full suggested set under its current limits; no money was moved."

    return {
        "final_recommendations": recommendations,
        "basket_gaps": gaps,
        "affordability": affordability,
        "actions": actions,
        "answer": answer,
        "warnings": warnings,
        "trace": state.get("trace", []) + ["Revalidated selected products against live Umon data."],
    }


graph = StateGraph(AgentState)
graph.add_node("understand", understand)
graph.add_node("context", context)
graph.add_node("discover", discover)
graph.add_node("cross_sell", cross_sell)
graph.add_node("rank", rank)
graph.add_node("verify", verify)
graph.add_edge(START, "understand")
graph.add_edge("understand", "context")
graph.add_edge("context", "discover")
graph.add_edge("discover", "cross_sell")
graph.add_edge("cross_sell", "rank")
graph.add_edge("rank", "verify")
graph.add_edge("verify", END)
compiled_graph = graph.compile()


async def run_agent(
    *,
    user_id: str,
    message: str,
    selected_agent_id: str | None = None,
) -> dict[str, Any]:
    return await compiled_graph.ainvoke({
        "user_id": user_id,
        "message": message.strip(),
        "selected_agent_id": selected_agent_id,
    })
