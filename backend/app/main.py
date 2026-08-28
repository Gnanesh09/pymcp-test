from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import lifespan as db_lifespan
from .routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_lifespan(app):
        yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.clerk_authorized_party
        or "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Mcp-Session-Id",
    ],
)


app.include_router(
    api_router,
    prefix=settings.api_prefix,
)


@app.get("/")
async def root():
    return {
        "name":
            settings.app_name,
        "status":
            "ok",
        "merchant":
            settings.merchant_name,
        "api":
            settings.api_prefix,
    }