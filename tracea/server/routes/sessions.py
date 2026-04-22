import base64
import json
from fastapi import APIRouter, Depends, Query
from tracea.server.auth import bearer_auth
from tracea.server.db import get_db
from typing import Optional

router = APIRouter(prefix="/api/v1", tags=["sessions"])


def encode_cursor(created_at: str, session_id: str) -> str:
    return base64.b64encode(json.dumps({"created_at": created_at, "session_id": session_id}).encode()).decode()


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    agent_id: Optional[str] = None,
    _api_key: str = Depends(bearer_auth)
):
    db = await anext(get_db())

    where_parts: list[str] = []
    params: list = []

    if agent_id:
        where_parts.append("agent_id = ?")
        params.append(agent_id)

    if cursor:
        data = json.loads(base64.b64decode(cursor.encode()))
        where_parts.append("(started_at, session_id) < (?, ?)")
        params.extend([data["created_at"], data["session_id"]])

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    rows = await db.execute(
        f"SELECT * FROM sessions {where} ORDER BY started_at DESC LIMIT ?",
        params + [limit + 1]
    )
    sessions = await rows.fetchall()
    has_more = len(sessions) > limit
    sessions = sessions[:limit] if has_more else sessions
    next_cursor = encode_cursor(sessions[-1]["started_at"], sessions[-1]["session_id"]) if has_more and sessions else None

    count_where = "WHERE agent_id = ?" if agent_id else ""
    count_params = [agent_id] if agent_id else []
    total_result = await db.execute(f"SELECT COUNT(*) FROM sessions {count_where}", count_params)
    total = (await total_result.fetchone())[0]

    return {"sessions": [dict(s) for s in sessions], "next_cursor": next_cursor, "total": total}


@router.get("/sessions/{session_id}/events")
async def get_session_events(
    session_id: str,
    limit: int = Query(500, ge=1, le=5000),
    _api_key: str = Depends(bearer_auth)
):
    db = await anext(get_db())
    rows = await db.execute(
        """SELECT *,
               type           AS event_type,
               total_tokens   AS tokens_used,
               error          AS error_message
           FROM events WHERE session_id = ? ORDER BY sequence ASC LIMIT ?""",
        (session_id, limit)
    )
    return {"events": [dict(e) for e in await rows.fetchall()]}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, _api_key: str = Depends(bearer_auth)):
    db = await anext(get_db())
    await db.execute("DELETE FROM alerts WHERE issue_id IN (SELECT issue_id FROM issues WHERE session_id = ?)", (session_id,))
    await db.execute("DELETE FROM issues WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    await db.commit()
    return None
