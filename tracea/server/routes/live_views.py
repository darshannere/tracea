from fastapi import APIRouter, Query, HTTPException, Depends
from tracea.server.db import get_db
from tracea.server.auth import get_auth_user_id
from typing import Optional
import json
import time

router = APIRouter(prefix="/api/v1", tags=["live_views"])


def _ts_to_ms_expr(col: str = "timestamp") -> str:
    """SQLite expression to convert ISO timestamp to epoch milliseconds."""
    return f"CAST((julianday({col}) - 2440587.5) * 86400000 AS INTEGER)"


@router.get("/events")
async def list_events(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    auth_user_id: str = Depends(get_auth_user_id),
):
    """Return tool events in ObservAgent-compatible format.

    Returns merged tool_call + tool_result rows.  Unmatched tool_call rows
    appear as in-progress (duration_ms / exit_status are NULL).
    """
    db = get_db()

    session_filter = "AND tc.session_id = ?" if session_id else ""
    user_filter = "AND tc.user_id = ?" if user_id else ""
    params: list = [limit]
    if session_id:
        params.insert(0, session_id)
    if user_id:
        params.insert(0, user_id)

    # Fetch tool_call rows joined with their matching tool_result
    sql = f"""
    WITH tool_calls AS (
        SELECT
            event_id,
            tool_name,
            session_id,
            agent_id,
            tool_call_id,
            timestamp,
            input_tokens,
            output_tokens,
            content,
            tool_summary,
            metadata,
            type,
            role,
            model,
            cost_usd
        FROM events
        WHERE type = 'tool_call'
          AND tool_name IS NOT NULL
          {session_filter}
          {user_filter}
    ),
    tool_results AS (
        SELECT
            tool_call_id,
            session_id,
            duration_ms,
            status_code,
            timestamp AS result_ts
        FROM events
        WHERE type = 'tool_result'
    )
    SELECT
        tc.event_id          AS id,
        tc.tool_name,
        tc.session_id,
        tc.agent_id,
        tc.tool_call_id,
        {_ts_to_ms_expr('tc.timestamp')} AS timestamp,
        tr.duration_ms,
        tr.status_code       AS exit_status,
        COALESCE(tc.tool_summary, tc.content) AS tool_summary,
        tc.input_tokens      AS nearest_input_tokens,
        tc.output_tokens     AS nearest_output_tokens,
        CASE WHEN tr.tool_call_id IS NULL THEN 'PreToolUse' ELSE 'PostToolUse' END AS hook_type,
        tc.type,
        tc.role,
        tc.content,
        tc.model,
        tc.cost_usd
    FROM tool_calls tc
    LEFT JOIN tool_results tr
        ON tr.tool_call_id = tc.tool_call_id
        AND tc.tool_call_id != ''
        AND tr.session_id   = tc.session_id
    ORDER BY tc.timestamp DESC
    LIMIT ?
    """

    rows = await db.execute(sql, params)
    events = [dict(r) for r in await rows.fetchall()]

    # Also include standalone error events (no matching tool_call) for the same session
    error_user_filter = "AND user_id = ?" if user_id else ""
    error_sql = f"""
    SELECT
        event_id             AS id,
        COALESCE(tool_name, 'error') AS tool_name,
        session_id,
        agent_id,
        tool_call_id,
        {_ts_to_ms_expr()}   AS timestamp,
        duration_ms,
        status_code          AS exit_status,
        COALESCE(tool_summary, content, error) AS tool_summary,
        input_tokens         AS nearest_input_tokens,
        output_tokens        AS nearest_output_tokens,
        'PostToolUse'        AS hook_type,
        type,
        NULL                 AS role,
        content,
        model,
        cost_usd
    FROM events
    WHERE type = 'error'
      AND tool_name IS NOT NULL
      {session_filter}
      {error_user_filter}
    ORDER BY timestamp DESC
    LIMIT ?
    """
    error_params = []
    if session_id:
        error_params.append(session_id)
    if user_id:
        error_params.append(user_id)
    error_params.append(limit)

    error_rows = await db.execute(error_sql, error_params)
    errors = [dict(r) for r in await error_rows.fetchall()]

    # Include chat.completion events
    chat_user_filter = "AND user_id = ?" if user_id else ""
    chat_sql = f"""
    SELECT
        event_id             AS id,
        ''                   AS tool_name,
        session_id,
        agent_id,
        tool_call_id,
        {_ts_to_ms_expr()}   AS timestamp,
        duration_ms,
        NULL                 AS exit_status,
        content              AS tool_summary,
        input_tokens         AS nearest_input_tokens,
        output_tokens        AS nearest_output_tokens,
        'PostToolUse'        AS hook_type,
        type,
        role,
        content,
        model,
        cost_usd
    FROM events
    WHERE type = 'chat.completion'
      {session_filter}
      {chat_user_filter}
    ORDER BY timestamp DESC
    LIMIT ?
    """
    chat_params = []
    if session_id:
        chat_params.append(session_id)
    if user_id:
        chat_params.append(user_id)
    chat_params.append(limit)

    chat_rows = await db.execute(chat_sql, chat_params)
    chats = [dict(r) for r in await chat_rows.fetchall()]

    # Merge and re-sort by timestamp DESC, then take top limit
    all_events = events + errors + chats
    all_events.sort(key=lambda x: x["timestamp"], reverse=True)
    all_events = all_events[:limit]

    # Reverse so oldest is first (matches ObservAgent hydration order)
    all_events.reverse()

    return all_events


@router.get("/sessions")
async def list_sessions_for_tree(user_id: Optional[str] = None, auth_user_id: str = Depends(get_auth_user_id)):
    """Return sessions with agent info for the left-hand tree panel."""
    db = get_db()
    where = "WHERE 1=1"
    params = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            session_id,
            agent_id,
            platform,
            started_at,
            ended_at,
            last_event_at,
            duration_ms,
            event_count,
            total_cost,
            total_tokens
        FROM sessions
        {where}
        ORDER BY last_event_at DESC
        LIMIT 200
    """, params)
    sessions = [dict(r) for r in await rows.fetchall()]
    return {"sessions": sessions}


@router.get("/insights/totals")
async def insight_totals(
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    auth_user_id: str = Depends(get_auth_user_id),
):
    """Server-side aggregation across ALL sessions (not paginated).

    Returns totals that the dashboard KPI cards use directly, avoiding
    the undercount that happens when summing across a paginated session list.
    """
    db = get_db()
    where = "WHERE 1=1"
    params: list = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    if agent_id:
        where += " AND agent_id = ?"
        params.append(agent_id)
    rows = await db.execute(f"""
        SELECT
            COUNT(*)                                                   AS total_sessions,
            COALESCE(ROUND(SUM(total_cost), 6), 0)                     AS total_cost,
            COALESCE(SUM(total_tokens), 0)                             AS total_tokens,
            COALESCE(SUM(event_count), 0)                              AS total_events,
            COALESCE(SUM(CASE WHEN issue_count > 0 THEN 1 ELSE 0 END), 0) AS sessions_with_issues
        FROM sessions
        {where}
    """, params)
    row = await rows.fetchone()
    return dict(row)


@router.get("/insights/cost-daily")
async def cost_daily(
    user_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    where = f"WHERE started_at >= date('now', '-{days} days')"
    params: list = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            date(started_at) AS day,
            ROUND(SUM(COALESCE(total_cost, 0)), 6) AS cost_usd
        FROM sessions
        {where}
        GROUP BY date(started_at)
        ORDER BY day ASC
    """, params)
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/tokens-daily")
async def tokens_daily(
    user_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    where = f"WHERE started_at >= date('now', '-{days} days')"
    params: list = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            date(started_at) AS day,
            SUM(total_tokens) AS tokens
        FROM sessions
        {where}
        GROUP BY date(started_at)
        ORDER BY day ASC
    """, params)
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/events-daily")
async def events_daily(
    user_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    where = f"WHERE started_at >= date('now', '-{days} days')"
    params: list = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            date(started_at) AS day,
            SUM(event_count) AS events
        FROM sessions
        {where}
        GROUP BY date(started_at)
        ORDER BY day ASC
    """, params)
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/cost-by-agent")
async def cost_by_agent(user_id: Optional[str] = None, auth_user_id: str = Depends(get_auth_user_id)):
    db = get_db()
    where = "WHERE agent_id IS NOT NULL AND agent_id != ''"
    params = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            COALESCE(NULLIF(agent_id, ''), 'solo') AS agent_type,
            ROUND(SUM(COALESCE(total_cost, 0)), 6) AS cost_usd
        FROM sessions
        {where}
        GROUP BY agent_id
        ORDER BY cost_usd DESC
    """, params)
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/activity")
async def activity_by_session(
    session_id: str = Query(...),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    rows = await db.execute("""
        SELECT
            (CAST((julianday(timestamp) - 2440587.5) * 86400000 AS INTEGER) / 60000) * 60000 AS bucket_ms,
            COUNT(*) AS tool_calls
        FROM events
        WHERE session_id = ?
          AND type = 'tool_result'
        GROUP BY bucket_ms
        ORDER BY bucket_ms ASC
    """, (session_id,))
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/tokens-over-time")
async def tokens_over_time(
    session_id: str = Query(...),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    rows = await db.execute("""
        SELECT
            (CAST((julianday(timestamp) - 2440587.5) * 86400000 AS INTEGER) / 60000) * 60000 AS bucket_ms,
            SUM(input_tokens)  AS input_tokens,
            SUM(output_tokens) AS output_tokens
        FROM events
        WHERE session_id = ?
          AND type IN ('tool_call', 'tool_result', 'chat.completion')
        GROUP BY bucket_ms
        ORDER BY bucket_ms ASC
    """, (session_id,))
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/error-rate")
async def error_rate(
    session_id: str = Query(default=""),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    # 5-minute buckets
    params = [session_id, session_id]

    rows = await db.execute("""
        SELECT
            (CAST((julianday(timestamp) - 2440587.5) * 86400000 AS INTEGER) / 300000) * 300000 AS bucket_ms,
            SUM(CASE WHEN status_code IS NOT NULL AND status_code != 0 THEN 1 ELSE 0 END) AS errors,
            COUNT(*) AS total
        FROM events
        WHERE type IN ('tool_result', 'error')
          AND (? = '' OR session_id = ?)
        GROUP BY bucket_ms
        ORDER BY bucket_ms ASC
    """, params)
    return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/latency-by-tool")
async def latency_by_tool(
    session_id: str = Query(default=""),
    auth_user_id: str = Depends(get_auth_user_id),
):
    db = get_db()
    params = [session_id, session_id]

    # SQLite 3.25+ supports window functions (NTILE).
    # We fall back gracefully if the SQLite version is too old by catching.
    try:
        rows = await db.execute("""
            WITH ranked AS (
                SELECT
                    tool_name,
                    duration_ms,
                    NTILE(100) OVER (PARTITION BY tool_name ORDER BY duration_ms) AS pct
                FROM events
                WHERE type = 'tool_result'
                  AND duration_ms IS NOT NULL
                  AND (? = '' OR session_id = ?)
            )
            SELECT
                tool_name,
                MAX(CASE WHEN pct <= 50 THEN duration_ms END) AS p50_ms,
                MAX(CASE WHEN pct <= 95 THEN duration_ms END) AS p95_ms,
                COUNT(*) AS sample_count
            FROM ranked
            GROUP BY tool_name
            HAVING sample_count >= 2
            ORDER BY p95_ms DESC
        """, params)
        return [dict(r) for r in await rows.fetchall()]
    except Exception:
        # Fallback for older SQLite without window functions
        rows = await db.execute("""
            SELECT
                tool_name,
                AVG(duration_ms) AS p50_ms,
                MAX(duration_ms) AS p95_ms,
                COUNT(*) AS sample_count
            FROM events
            WHERE type = 'tool_result'
              AND duration_ms IS NOT NULL
              AND (? = '' OR session_id = ?)
            GROUP BY tool_name
            HAVING sample_count >= 2
            ORDER BY p95_ms DESC
        """, params)
        return [dict(r) for r in await rows.fetchall()]


@router.get("/insights/stalled-agents")
async def stalled_agents(user_id: Optional[str] = None, auth_user_id: str = Depends(get_auth_user_id)):
    """Return sessions (treated as agents) that have not had an event in > 10 minutes
    and have not ended yet."""
    db = get_db()
    where = "WHERE ended_at IS NULL AND last_event_at IS NOT NULL AND CAST((julianday('now') - julianday(last_event_at)) * 86400000 AS INTEGER) > 600000"
    params = []
    if user_id:
        where += " AND user_id = ?"
        params.append(user_id)
    rows = await db.execute(f"""
        SELECT
            session_id AS agent_id,
            COALESCE(NULLIF(agent_id, ''), 'solo') AS agent_type,
            CAST((julianday(last_event_at) - 2440587.5) * 86400000 AS INTEGER) AS last_activity_ts,
            CAST((julianday('now') - julianday(last_event_at)) * 86400 AS INTEGER) AS idle_seconds
        FROM sessions
        {where}
        ORDER BY last_event_at ASC
        LIMIT 50
    """, params)
    return [dict(r) for r in await rows.fetchall()]


@router.get("/health")
async def health_snapshot():
    db = get_db()

    last_ts_row = await db.execute(
        "SELECT MAX(timestamp) AS ts FROM events"
    )
    last_ts = (await last_ts_row.fetchone())["ts"]

    err_row = await db.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status_code IS NOT NULL AND status_code != 0 THEN 1 ELSE 0 END), 0) AS errors,
            COUNT(*) AS total
        FROM events
        WHERE type = 'tool_result'
          AND session_id = (SELECT session_id FROM events ORDER BY timestamp DESC LIMIT 1)
    """)
    err = await err_row.fetchone()

    return {
        "lastEventTs": last_ts,
        "errorRate": (err["errors"] / err["total"] * 100) if err and err["total"] else 0,
        "errorCount": err["errors"] if err else 0,
        "totalCalls": err["total"] if err else 0,
    }
