from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from tracea.server.db import get_db
from typing import Optional

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
