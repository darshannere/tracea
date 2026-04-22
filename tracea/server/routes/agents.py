from fastapi import APIRouter, Depends
from tracea.server.auth import bearer_auth
from tracea.server.db import get_db

router = APIRouter(prefix="/api/v1", tags=["agents"])


@router.get("/agents")
async def list_agents(_api_key: str = Depends(bearer_auth)):
    db = await anext(get_db())
    rows = await db.execute("""
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
        WHERE agent_id IS NOT NULL AND agent_id != ''
        GROUP BY agent_id
        ORDER BY last_active DESC
    """)
    agents = await rows.fetchall()
    return {"agents": [dict(a) for a in agents]}
