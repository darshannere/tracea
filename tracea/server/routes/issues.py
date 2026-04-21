import base64
import json
from fastapi import APIRouter, Depends, Query
from tracea.server.auth import bearer_auth
from tracea.server.db import get_db
from typing import Optional

router = APIRouter(prefix="/api/v1", tags=["issues"])


@router.get("/issues")
async def list_issues(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    session_id: Optional[str] = None,
    _api_key: str = Depends(bearer_auth)
):
    db = await anext(get_db())
    if cursor:
        data = json.loads(base64.b64decode(cursor.encode()))
        detected_before, issue_before = data["detected_at"], data["issue_id"]
    else:
        detected_before, issue_before = None, None

    # Alias issue_type → issue_category to match the frontend model
    select = "SELECT *, issue_type AS issue_category FROM issues"
    if session_id:
        q = f"{select} WHERE session_id = ? AND (detected_at, issue_id) < (?, ?) ORDER BY detected_at DESC LIMIT ?" if cursor else f"{select} WHERE session_id = ? ORDER BY detected_at DESC LIMIT ?"
        params = (session_id, detected_before, issue_before, limit + 1) if cursor else (session_id, limit + 1)
    else:
        q = f"{select} WHERE (detected_at, issue_id) < (?, ?) ORDER BY detected_at DESC LIMIT ?" if cursor else f"{select} ORDER BY detected_at DESC LIMIT ?"
        params = (detected_before, issue_before, limit + 1) if cursor else (limit + 1,)

    rows = await db.execute(q, params)
    issues = await rows.fetchall()
    has_more = len(issues) > limit
    issues = issues[:limit] if has_more else issues
    next_cursor = base64.b64encode(json.dumps({"detected_at": issues[-1]["detected_at"], "issue_id": issues[-1]["issue_id"]}).encode()).decode() if has_more and issues else None
    return {"issues": [dict(i) for i in issues], "next_cursor": next_cursor}
