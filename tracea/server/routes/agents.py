from fastapi import APIRouter, Query
from tracea.server.db import get_db
from typing import Optional

router = APIRouter(prefix="/api/v1", tags=["agents"])


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
    """Return distinct user_ids for the team picker."""
    db = await anext(get_db())
    rows = await db.execute("""
        SELECT DISTINCT user_id
        FROM sessions
        WHERE user_id IS NOT NULL AND user_id != ''
        ORDER BY user_id ASC
    """)
    users = [row["user_id"] for row in await rows.fetchall()]
    return {"users": users}
