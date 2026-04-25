import base64
import json
from fastapi import APIRouter, Query, HTTPException
from tracea.server.db import get_db
from typing import Optional

router = APIRouter(prefix="/api/v1", tags=["issues"])


def _decode_cursor(cursor: str) -> dict:
    try:
        return json.loads(base64.b64decode(cursor.encode()))
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "invalid_cursor"})


@router.get("/issues")
async def list_issues(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    db = await anext(get_db())
    if cursor:
        data = _decode_cursor(cursor)
        detected_before, issue_before = data["detected_at"], data["issue_id"]
    else:
        detected_before, issue_before = None, None

    # JOIN sessions to surface agent_id and platform on each issue
    select = """
        SELECT i.*, i.issue_type AS issue_category, s.agent_id, s.platform
        FROM issues i
        LEFT JOIN sessions s ON i.session_id = s.session_id
    """

    where_parts: list[str] = []
    params: list = []

    if session_id:
        where_parts.append("i.session_id = ?")
        params.append(session_id)
    if agent_id:
        where_parts.append("s.agent_id = ?")
        params.append(agent_id)
    if user_id:
        where_parts.append("s.user_id = ?")
        params.append(user_id)
    if cursor:
        where_parts.append("(i.detected_at, i.issue_id) < (?, ?)")
        params.extend([detected_before, issue_before])

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    q = f"{select} {where} ORDER BY i.detected_at DESC LIMIT ?"
    params.append(limit + 1)

    rows = await db.execute(q, params)
    issues = await rows.fetchall()
    has_more = len(issues) > limit
    issues = issues[:limit] if has_more else issues
    next_cursor = (
        base64.b64encode(
            json.dumps({"detected_at": issues[-1]["detected_at"], "issue_id": issues[-1]["issue_id"]}).encode()
        ).decode()
        if has_more and issues
        else None
    )
    return {"issues": [dict(i) for i in issues], "next_cursor": next_cursor}
