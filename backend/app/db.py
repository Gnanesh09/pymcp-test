from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

from .config import settings


client: AsyncMongoClient | None = None
db: Any = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def init_indexes() -> None:
    assert db is not None

    await db.users.create_index(
        [("clerk_user_id", ASCENDING)],
        unique=True,
    )

    await db.agents.create_index(
        [
            ("owner_clerk_user_id", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    await db.agent_credentials.create_index(
        [("token_hash", ASCENDING)],
        unique=True,
    )

    await db.products.create_index(
        [
            ("merchant_id", ASCENDING),
            ("active", ASCENDING),
        ]
    )

    await db.carts.create_index(
        [
            ("owner_clerk_user_id", ASCENDING),
            ("agent_id", ASCENDING),
        ]
    )

    await db.orders.create_index(
        [
            ("owner_clerk_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    await db.payments.create_index(
        [("provider_payment_id", ASCENDING)],
        unique=True,
        sparse=True,
    )

    await db.ledger_entries.create_index(
        [("entry_id", ASCENDING)],
        unique=True,
    )

    await db.audit_events.create_index(
        [
            ("owner_clerk_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    await db.audit_events.create_index(
        [
            ("agent_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )


async def seed_demo_merchant_and_products() -> None:
    assert db is not None

    merchant = {
        "_id": settings.merchant_id,
        "name": settings.merchant_name,
        "status": "ACTIVE",
        "ai_discovery": True,
        "ai_purchasing": True,
        "ai_checkout": True,
        "max_order_value": 100000,
        "allowed_categories": [
            "grocery", "dairy", "snacks", "beverages", "household", "personal-care"
        ],
        "recommendations_enabled": True,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }

    await db.merchants.update_one(
        {"_id": merchant["_id"]},
        {"$setOnInsert": merchant},
        upsert=True,
    )

    products = [
        {
            "_id": "p001",
            "merchant_id": settings.merchant_id,
            "name": "Aashirvaad Atta 5kg",
            "brand": "Aashirvaad",
            "category": "grocery",
            "price_paise": 28900,
            "mrp_paise": 32000,
            "rating": 4.5,
            "stock": 50,
            "unit": "5 kg",
            "description": "Premium whole wheat flour.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQi8qXYSl439pmbK5h5T8GcGYJtQtRkxrnKDYbCRYy7aQ&s=10",
            "tags": ["atta", "flour", "wheat", "grocery"],
            "active": True,
            "cross_sell_ids": ["p005", "p006"],
        },
        {
            "_id": "p002",
            "merchant_id": settings.merchant_id,
            "name": "Tata Salt 1kg",
            "brand": "Tata",
            "category": "grocery",
            "price_paise": 2800,
            "mrp_paise": 3000,
            "rating": 4.7,
            "stock": 100,
            "unit": "1 kg",
            "description": "Iodised vacuum evaporated salt.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRa7lkQncRgI3d52YGb2MGmsofKoauTJoLvrJaBUWppVg&s=10",
            "tags": ["salt", "grocery"],
            "active": True,
        },
        {
            "_id": "p003",
            "merchant_id": settings.merchant_id,
            "name": "Amul Taaza Milk 1L",
            "brand": "Amul",
            "category": "dairy",
            "price_paise": 6200,
            "mrp_paise": 6600,
            "rating": 4.8,
            "stock": 40,
            "unit": "1 litre",
            "description": "Fresh toned milk.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSGaiqZ-X_6OZLVY0cbRoHSLv-u_YsbqtBAm_C6RggvLA&s=10",
            "tags": ["milk", "dairy", "breakfast"],
            "active": True,
            "cross_sell_ids": ["p005", "p007"],
        },
        {
            "_id": "p004",
            "merchant_id": settings.merchant_id,
            "name": "Amul Butter 500g",
            "brand": "Amul",
            "category": "dairy",
            "price_paise": 28500,
            "mrp_paise": 31000,
            "rating": 4.8,
            "stock": 25,
            "unit": "500 g",
            "description": "Pasteurised table butter.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTtZt3ju1kB5B4tsHu3KrQ-PRVe5xcSBXBf9NZbEPlF_A&s",
            "tags": ["butter", "dairy"],
            "active": True,
            "cross_sell_ids": ["p005"],
        },
        {
            "_id": "p005",
            "merchant_id": settings.merchant_id,
            "name": "Maggi 2-Minute Noodles",
            "brand": "Nestle",
            "category": "snacks",
            "price_paise": 1400,
            "mrp_paise": 1500,
            "rating": 4.6,
            "stock": 200,
            "unit": "70 g",
            "description": "Instant noodles.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT1YIdP9S9iKozp1c7D3XMZjK4riYeeLQD1kac9QMpV5Q&s=10",
            "tags": ["maggi", "noodles", "instant", "snacks"],
            "active": True,
            "cross_sell_ids": ["p006", "p007"],
        },
        {
            "_id": "p006",
            "merchant_id": settings.merchant_id,
            "name": "Lay's Magic Masala",
            "brand": "Lay's",
            "category": "snacks",
            "price_paise": 2000,
            "mrp_paise": 2000,
            "rating": 4.4,
            "stock": 120,
            "unit": "50 g",
            "description": "Spicy potato chips.",
            "image": "https://banerjeesupermarket.com/wp-content/uploads/2026/04/81rQQr3BvWL._SL1500_-600x723.jpg",
            "tags": ["chips", "snacks"],
            "active": True,
        },
        {
            "_id": "p007",
            "merchant_id": settings.merchant_id,
            "name": "Coca-Cola 750ml",
            "brand": "Coca-Cola",
            "category": "beverages",
            "price_paise": 4000,
            "mrp_paise": 4500,
            "rating": 4.3,
            "stock": 80,
            "unit": "750 ml",
            "description": "Carbonated soft drink.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTmgriAj9WTl8bqGCJRG7uQd5F19pEuYH4mn_1ryHIYKg&s=10",
            "tags": ["coke", "drink", "beverage", "soft drink"],
            "active": True,
        },
        {
            "_id": "p008",
            "merchant_id": settings.merchant_id,
            "name": "Red Bull Energy Drink",
            "brand": "Red Bull",
            "category": "beverages",
            "price_paise": 12500,
            "mrp_paise": 13500,
            "rating": 4.5,
            "stock": 35,
            "unit": "250 ml",
            "description": "Energy drink.",
            "image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTEHbTunV3BTGk2CFf6WaoWWYYPa1QyQQz8tSYKrmlXCA&s=10",
            "tags": ["energy", "drink", "beverage"],
            "active": True,
        },
        {
            "_id": "p009",
            "merchant_id": settings.merchant_id,
            "name": "Surf Excel Matic 2kg",
            "brand": "Surf Excel",
            "category": "household",
            "price_paise": 36500,
            "mrp_paise": 42000,
            "rating": 4.6,
            "stock": 20,
            "unit": "2 kg",
            "description": "Detergent powder for washing machines.",
            "image": "https://encrypted-tbn1.gstatic.com/shopping?q=tbn:ANd9GcS1xQGzDp2BZq8vjTvS7Wrp3vrWNSOUbNsEozv_8vS3ZqSv9XnD40lVVttATUuNMGT1SCy6FeRGQLPdvOtO5qs9dCyieobHF60qcedA9hNwG-7xpf2gvD0Wqz4567YIsm7wq2xlP8o&usqp=CAc",
            "tags": ["detergent", "washing", "household"],
            "active": True,
        },
        {
            "_id": "p010",
            "merchant_id": settings.merchant_id,
            "name": "Colgate MaxFresh",
            "brand": "Colgate",
            "category": "personal-care",
            "price_paise": 9900,
            "mrp_paise": 11500,
            "rating": 4.5,
            "stock": 60,
            "unit": "150 g",
            "description": "Fresh breath toothpaste.",
            "image": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:ANd9GcQcGOP1-iLFVa741jL0HGPQJ0gsGmOsrFrXmiEAL4dQ97K04aljr25r9RvaSFCgk76RD7ep9UwAxO3nZdpA2Ny1c6u_p2igD8Yf7oDjyr59NbmfcYcyJKrSpQ",
            "tags": ["toothpaste", "personal care"],
            "active": True,
        },
    ]

    for product in products:
        await db.products.update_one(
            {"_id": product["_id"]},
            {"$setOnInsert": product},
            upsert=True,
        )
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global client, db

    client = AsyncMongoClient(
        settings.mongodb_uri
    )

    db = client[settings.mongodb_db]

    # Verify MongoDB connection.
    await db.command("ping")

    await init_indexes()
    await seed_demo_merchant_and_products()

    try:
        yield
    finally:
        await client.close()

        client = None
        db = None


def get_db() -> Any:
    if db is None:
        raise RuntimeError(
            "Database is not initialized"
        )

    return db