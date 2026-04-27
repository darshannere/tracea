"""Auth module — supports disabled (no-op) and api_key modes."""
from __future__ import annotations
import hashlib
import os
from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from tracea.server.db import get_db

security = HTTPBearer(auto_error=False)


def _get_auth_mode() -> str:
    return os.environ.get("TRACEA_AUTH_MODE", "disabled")


async def bearer_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """Return authenticated user_id or empty string.

    Mode ``disabled``: always succeeds (backward compatible).
    Mode ``api_key``: validates bearer token against ``api_keys`` table.
    """
    auth_mode = _get_auth_mode()
    if auth_mode == "disabled":
        return ""

    if auth_mode != "api_key":
        raise HTTPException(status_code=500, detail=f"Unknown auth mode: {auth_mode}")

    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing API key")

    token = credentials.credentials.strip()
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    db = await anext(get_db())
    row = await db.execute(
        "SELECT user_id FROM api_keys WHERE key_hash = ?",
        (key_hash,)
    )
    result = await row.fetchone()
    if not result:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Update last_used
    await db.execute(
        "UPDATE api_keys SET last_used = datetime('now') WHERE key_hash = ?",
        (key_hash,)
    )
    await db.commit()

    return result["user_id"]


async def get_auth_user_id(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """FastAPI dependency that returns the authenticated user_id (or empty)."""
    return await bearer_auth(credentials)
