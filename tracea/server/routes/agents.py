from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from tracea.server.db import get_db
from tracea.server.models import ApiKeyCreate
from typing import Optional
import secrets
import hashlib

router = APIRouter(prefix="/api/v1", tags=["agents"])


class UserCreate(BaseModel):
    user_id: str
    name: str = ""
    email: str = ""


@router.get("/agents")
async def list_agents(user_id: Optional[str] = None):
    db = await anext(get_db())
    where_clause = "WHERE agent_id IS NOT NULL AND agent_id != ''"
    params = []
    if user_id:
        where_clause += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            agent_id,
            COUNT(*)                                                     AS session_count,
            SUM(CASE WHEN issue_count > 0 THEN 1 ELSE 0 END)            AS error_session_count,
            ROUND(SUM(COALESCE(total_cost, 0)), 6)                       AS total_cost,
            MAX(last_event_at)                                           AS last_active,
            (SELECT platform FROM sessions s2
             WHERE s2.agent_id = sessions.agent_id
             ORDER BY s2.last_event_at DESC LIMIT 1)                    AS platform
        FROM sessions
        {where_clause}
        GROUP BY agent_id
        ORDER BY last_active DESC
    """, params)
    agents = await rows.fetchall()
    return {"agents": [dict(a) for a in agents]}


@router.get("/users")
async def list_users():
    """Return all team members from the users table."""
    db = await anext(get_db())
    rows = await db.execute("""
        SELECT user_id, name, email, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = [dict(r) for r in await rows.fetchall()]
    return {"users": users}


@router.post("/users")
async def create_user(body: UserCreate):
    """Add a new team member."""
    db = await anext(get_db())
    try:
        await db.execute(
            "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
            (body.user_id, body.name, body.email),
        )
        await db.commit()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"User already exists or invalid: {e}")
    return {"status": "ok", "user_id": body.user_id}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """Remove a team member."""
    db = await anext(get_db())
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

@router.get("/api-keys")
async def list_api_keys():
    """List all API keys (hashes redacted)."""
    db = await anext(get_db())
    rows = await db.execute("""
        SELECT key_hash, user_id, name, created_at, last_used
        FROM api_keys
        ORDER BY created_at DESC
    """)
    keys = []
    for r in await rows.fetchall():
        keys.append({
            "key_hash": r["key_hash"][:16] + "...",
            "user_id": r["user_id"],
            "name": r["name"],
            "created_at": r["created_at"],
            "last_used": r["last_used"],
        })
    return {"api_keys": keys}


@router.post("/api-keys")
async def create_api_key(body: ApiKeyCreate):
    """Create a new API key for a user. Returns the plaintext key once."""
    db = await anext(get_db())
    # Verify user exists
    row = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (body.user_id,))
    if not await row.fetchone():
        raise HTTPException(status_code=400, detail=f"User '{body.user_id}' does not exist")

    plaintext = "tr_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()

    await db.execute(
        "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?, ?, ?)",
        (key_hash, body.user_id, body.name),
    )
    await db.commit()
    return {"status": "ok", "api_key": plaintext, "user_id": body.user_id}


@router.delete("/api-keys/{key_hash}")
async def revoke_api_key(key_hash: str):
    """Revoke an API key by its full hash."""
    db = await anext(get_db())
    await db.execute("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
    await db.commit()
    return {"status": "ok"}
