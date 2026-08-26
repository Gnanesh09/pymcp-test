import hashlib
import hmac
import secrets
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from pymongo import ReturnDocument
from jwt import PyJWKClient

from .config import settings
from .db import get_db, utc_now


_jwks_client = PyJWKClient(settings.clerk_jwks_url)


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return header[7:].strip()


async def get_current_claims(request: Request) -> dict[str, Any]:
    token = _bearer(request)

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)

        decode_options: dict[str, Any] = {
            "algorithms": ["RS256"],
            "issuer": settings.clerk_issuer,
            "leeway": 10,
        }

        if settings.clerk_authorized_party:
            decode_options["options"] = {"verify_aud": False}

        claims = jwt.decode(
            token,
            signing_key.key,
            **decode_options,
        )

        if settings.clerk_authorized_party:
            azp = claims.get("azp")
            if azp and azp != settings.clerk_authorized_party:
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized session issuer",
                )

        if not claims.get("sub"):
            raise HTTPException(
                status_code=401,
                detail="Clerk token missing subject",
            )

        return claims

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Clerk session token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    claims: dict[str, Any] = Depends(get_current_claims),
):
    db = get_db()

    clerk_user_id = str(claims["sub"])

    user = await db.users.find_one_and_update(
        {"clerk_user_id": clerk_user_id},
        {
            "$set": {
                "email": claims.get("email"),
                "updated_at": utc_now(),
            },
            "$setOnInsert": {
                "clerk_user_id": clerk_user_id,
                "created_at": utc_now(),
                "status": "ACTIVE",
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    if not user or user.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="User account is not active",
        )

    return user


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_secret(prefix: str) -> tuple[str, str]:
    raw = f"{prefix}_{secrets.token_urlsafe(32)}"
    return raw, hash_secret(raw)


def verify_hmac_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
