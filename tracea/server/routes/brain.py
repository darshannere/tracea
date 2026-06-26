"""Brain (company knowledge) API routes."""

import base64
import json
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel

from tracea.server.db import get_db
from tracea.server.auth import get_auth_user_id, require_admin

router = APIRouter(prefix="/api/v1", tags=["brain"])


class BrainEntryOut(BaseModel):
    id: str
    user_id: str
    category: str
    title: str
    content: str
    confidence: float
    hit_count: int
    source_sessions: list[str]
    created_at: str
    updated_at: str


class BrainListResponse(BaseModel):
    entries: list[BrainEntryOut]
    next_cursor: Optional[str] = None
    total: int


class GraphNode(BaseModel):
    id: str
    category: str
    title: str
    confidence: float
    hit_count: int


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int  # number of shared sessions


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def _encode_cursor(hit_count: int, updated_at: str, entry_id: str) -> str:
    return base64.b64encode(
        json.dumps({"v": hit_count, "v2": updated_at, "id": entry_id}).encode()
    ).decode()


def _decode_cursor(cursor: str) -> dict:
    try:
        return json.loads(base64.b64decode(cursor.encode()))
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "invalid_cursor"})


@router.get("/brain/entries", response_model=BrainListResponse)
async def list_brain_entries(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
    q: Optional[str] = None,
    auth_user_id: str = Depends(get_auth_user_id),
):
    """List brain entries with cursor pagination and optional FTS5 search."""
    db = await anext(get_db())

    # FTS5 search: resolve matching rowids first
    fts_rowids: set[int] = set()
    if q:
        try:
            fts_rows = await db.execute(
                "SELECT rowid FROM brain_entries_fts WHERE brain_entries_fts MATCH ?",
                (q,),
            )
            fts_rowids = {row[0] for row in await fts_rows.fetchall()}
            if not fts_rowids:
                return {"entries": [], "next_cursor": None, "total": 0}
        except Exception:
            # FTS5 syntax error — return empty
            return {"entries": [], "next_cursor": None, "total": 0}

    where_parts: list[str] = []
    params: list = []

    if category:
        where_parts.append("category = ?")
        params.append(category)
    if user_id:
        where_parts.append("user_id = ?")
        params.append(user_id)
    if fts_rowids:
        placeholders = ",".join("?" * len(fts_rowids))
        where_parts.append(f"rowid IN ({placeholders})")
        params.extend(fts_rowids)

    if cursor:
        data = _decode_cursor(cursor)
        # Cursor is on (hit_count DESC, updated_at DESC, id)
        where_parts.append(
            "(hit_count, updated_at, id) < (?, ?, ?)"
        )
        params.extend([data["v"], data["v2"], data["id"]])

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    rows = await db.execute(
        f"""SELECT * FROM brain_entries {where}
            ORDER BY hit_count DESC, updated_at DESC, id DESC
            LIMIT ?""",
        params + [limit + 1],
    )
    entries = await rows.fetchall()
    has_more = len(entries) > limit
    entries = entries[:limit] if has_more else entries

    # Encode cursor using hit_count + updated_at composite
    next_cursor = None
    if has_more and entries:
        last = entries[-1]
        next_cursor = _encode_cursor(
            last["hit_count"], last["updated_at"], last["id"]
        )

    # Total count
    count_where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    total_result = await db.execute(
        f"SELECT COUNT(*) FROM brain_entries {count_where}", params
    )
    total = (await total_result.fetchone())[0]

    return {
        "entries": [
            BrainEntryOut(
                id=e["id"],
                user_id=e["user_id"],
                category=e["category"],
                title=e["title"],
                content=e["content"],
                confidence=e["confidence"],
                hit_count=e["hit_count"],
                source_sessions=json.loads(e["source_sessions"]),
                created_at=e["created_at"],
                updated_at=e["updated_at"],
            )
            for e in entries
        ],
        "next_cursor": next_cursor,
        "total": total,
    }


@router.get("/brain/entries/{entry_id}", response_model=BrainEntryOut)
async def get_brain_entry(entry_id: str, auth_user_id: str = Depends(get_auth_user_id)):
    """Get a single brain entry by ID."""
    db = await anext(get_db())
    row = await db.execute("SELECT * FROM brain_entries WHERE id = ?", (entry_id,))
    entry = await row.fetchone()
    if not entry:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return BrainEntryOut(
        id=entry["id"],
        user_id=entry["user_id"],
        category=entry["category"],
        title=entry["title"],
        content=entry["content"],
        confidence=entry["confidence"],
        hit_count=entry["hit_count"],
        source_sessions=json.loads(entry["source_sessions"]),
        created_at=entry["created_at"],
        updated_at=entry["updated_at"],
    )


@router.delete("/brain/entries/{entry_id}")
async def delete_brain_entry(entry_id: str, admin_user_id: str = Depends(require_admin)):
    """Delete a brain entry (and its FTS5 index via trigger)."""
    db = await anext(get_db())
    cursor = await db.execute("DELETE FROM brain_entries WHERE id = ?", (entry_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return {"deleted": True}


@router.get("/brain/graph", response_model=GraphResponse)
async def get_brain_graph(
    user_id: Optional[str] = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    auth_user_id: str = Depends(get_auth_user_id),
):
    """Return graph topology: nodes = entries, edges = shared sessions."""
    db = await anext(get_db())

    where_parts: list[str] = []
    params: list = []

    if user_id:
        where_parts.append("user_id = ?")
        params.append(user_id)
    if min_confidence > 0:
        where_parts.append("confidence >= ?")
        params.append(min_confidence)

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    # Fetch nodes
    rows = await db.execute(
        f"SELECT id, category, title, confidence, hit_count FROM brain_entries {where}",
        params,
    )
    nodes = [
        GraphNode(
            id=r["id"],
            category=r["category"],
            title=r["title"],
            confidence=r["confidence"],
            hit_count=r["hit_count"],
        )
        for r in await rows.fetchall()
    ]

    node_ids = {n.id for n in nodes}
    if not node_ids:
        return {"nodes": [], "edges": []}

    # Build edges: pairs of entries sharing at least one session
    # Efficient approach: explode source_sessions JSON, then self-join
    placeholders = ",".join("?" * len(node_ids))
    rows = await db.execute(
        f"""
        SELECT brain_entries.id, json_each.value AS session_id
        FROM brain_entries, json_each(source_sessions)
        WHERE brain_entries.id IN ({placeholders})
        """,
        list(node_ids),
    )
    entry_sessions: dict[str, set[str]] = {}
    for r in await rows.fetchall():
        entry_sessions.setdefault(r["id"], set()).add(r["session_id"])

    edges: list[GraphEdge] = []
    ids = list(node_ids)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            shared = entry_sessions.get(ids[i], set()) & entry_sessions.get(ids[j], set())
            if shared:
                edges.append(
                    GraphEdge(
                        source=ids[i],
                        target=ids[j],
                        weight=len(shared),
                    )
                )

    return {"nodes": nodes, "edges": edges}
