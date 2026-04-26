"""App settings — key-value store in SQLite, with env-var fallback."""

import os
from tracea.server.db import get_db


async def get_setting(key: str, default: str | None = None) -> str | None:
    """Read a setting from the DB. Falls back to env var, then default."""
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row:
            return row["value"]
    except Exception:
        pass
    return os.getenv(key, default)


async def set_setting(key: str, value: str) -> None:
    """Write or update a setting in the DB."""
    db_gen = get_db()
    db = await db_gen.__anext__()
    await db.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value),
    )
    await db.commit()


async def get_rca_config() -> dict:
    """Load RCA config from DB settings, falling back to env vars."""
    keys = [
        "TRACEA_RCA_BACKEND",
        "TRACEA_RCA_MODEL",
        "TRACEA_RCA_BASE_URL",
        "TRACEA_RCA_PROMPT_PATH",
        "TRACEA_RCA_REDACT_CONTENT",
        "TRACEA_RCA_MAX_TOKENS",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]
    values = {}
    for key in keys:
        values[key] = await get_setting(key)

    backend = values.get("TRACEA_RCA_BACKEND") or "disabled"
    return {
        "backend": backend,
        "model": values.get("TRACEA_RCA_MODEL") or "",
        "base_url": values.get("TRACEA_RCA_BASE_URL") or "",
        "prompt_path": values.get("TRACEA_RCA_PROMPT_PATH") or "",
        "redact_content": (values.get("TRACEA_RCA_REDACT_CONTENT") or "true").lower() == "true",
        "max_tokens": int(values.get("TRACEA_RCA_MAX_TOKENS") or "2048"),
        "api_key": values.get("OPENAI_API_KEY") or values.get("ANTHROPIC_API_KEY") or "",
    }
