from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import lifespan
from .routes import router

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    router,
    prefix=settings.api_prefix,
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "status": "ok",
        "merchant": settings.merchant_name,
    }
