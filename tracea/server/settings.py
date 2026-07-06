"""App settings — key-value store in SQLite, with env-var fallback.

Sensitive values (API keys, tokens) are stored in the same table but are only
ever returned to callers through explicitly-masking endpoints (e.g.
``GET /api/v1/config/rca`` returns ``api_key_present: bool``). They are never
returned in plaintext by ``get_settings`` batch reads that surface to clients.
Env vars always take precedence over DB values for sensitive keys, so operators
can pin secrets via environment without DB writes.
"""

import os
from tracea.server.db import get_db


def _is_sensitive(key: str) -> bool:
    """A key is sensitive if it looks like a secret (API key, token, password)."""
    upper = key.upper()
    return "API_KEY" in upper or "TOKEN" in upper or "SECRET" in upper or "PASSWORD" in upper


async def get_setting(key: str, default: str | None = None) -> str | None:
    """Read a setting. Env var wins, then DB, then default.

    Sensitive keys are readable from the DB by internal callers (e.g. the RCA
    worker) so that dashboard-configured secrets actually take effect — they
    are simply never exposed in plaintext by config-GET endpoints.
    """
    env_val = os.getenv(key)
    if env_val:
        return env_val

    db = get_db()
    try:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row:
            return row["value"]
    except Exception:
        pass
    return default


async def set_setting(key: str, value: str) -> None:
    """Write or update a setting in the DB.

    Sensitive keys are persisted so the RCA/brain workers can read them, but
    callers must ensure they are masked before being returned to clients.
    """
    db = get_db()
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


async def get_settings(keys: list[str]) -> dict[str, str | None]:
    """Read a batch of settings. Env vars win; sensitive DB values are masked.

    For sensitive keys, returns ``"***"`` when a DB value exists (so callers
    can distinguish "unset" from "set but hidden") and the plaintext only when
    an env var provides it. Internal callers that need the raw secret should
    use :func:`get_setting` directly.
    """
    db = get_db()
    results: dict[str, str | None] = {}
    db_keys = []
    for key in keys:
        env_val = os.getenv(key)
        if env_val:
            results[key] = env_val
        else:
            results[key] = None
            db_keys.append(key)

    if db_keys:
        try:
            placeholders = ",".join("?" for _ in db_keys)
            cursor = await db.execute(
                f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
                tuple(db_keys)
            )
            rows = await cursor.fetchall()
            for row in rows:
                # Mask sensitive DB values in the batch response.
                results[row["key"]] = "***" if _is_sensitive(row["key"]) else row["value"]
        except Exception:
            pass
    return results


async def get_rca_config() -> dict:
    """Load RCA config from DB settings, falling back to env vars.

    Reads non-sensitive config via ``get_settings`` (batch) and the API key
    via ``get_setting`` (single, returns plaintext from env-or-DB).
    """
    non_secret = await get_settings([
        "TRACEA_RCA_BACKEND",
        "TRACEA_RCA_MODEL",
        "TRACEA_RCA_BASE_URL",
        "TRACEA_RCA_PROMPT_PATH",
        "TRACEA_RCA_REDACT_CONTENT",
        "TRACEA_RCA_MAX_TOKENS",
    ])
    backend = non_secret.get("TRACEA_RCA_BACKEND") or "disabled"

    # Read the matching API key for the active backend (env wins over DB).
    api_key = ""
    if backend == "openai":
        api_key = (await get_setting("OPENAI_API_KEY")) or ""
    elif backend == "anthropic":
        api_key = (await get_setting("ANTHROPIC_API_KEY")) or ""

    return {
        "backend": backend,
        "model": non_secret.get("TRACEA_RCA_MODEL") or "",
        "base_url": non_secret.get("TRACEA_RCA_BASE_URL") or "",
        "prompt_path": non_secret.get("TRACEA_RCA_PROMPT_PATH") or "",
        "redact_content": (non_secret.get("TRACEA_RCA_REDACT_CONTENT") or "true").lower() == "true",
        "max_tokens": int(non_secret.get("TRACEA_RCA_MAX_TOKENS") or "2048"),
        "api_key": api_key,
    }


async def get_brain_config() -> dict:
    """Load brain synthesis config from DB settings, falling back to env vars.

    Reuses RCA LLM backend settings by default. Brain-specific overrides
    use TRACEA_BRAIN_* prefix. Reads API key via ``get_setting`` (plaintext).
    """
    non_secret = await get_settings([
        "TRACEA_BRAIN_BACKEND",
        "TRACEA_BRAIN_MODEL",
        "TRACEA_BRAIN_BASE_URL",
        "TRACEA_BRAIN_PROMPT_PATH",
        "TRACEA_BRAIN_MAX_TOKENS",
        "TRACEA_BRAIN_ENABLED",
        "TRACEA_RCA_BACKEND",
        "TRACEA_RCA_MODEL",
        "TRACEA_RCA_BASE_URL",
        "TRACEA_RCA_MAX_TOKENS",
    ])

    # Brain defaults to RCA settings if not explicitly configured
    backend = non_secret.get("TRACEA_BRAIN_BACKEND") or non_secret.get("TRACEA_RCA_BACKEND") or "disabled"
    enabled = (non_secret.get("TRACEA_BRAIN_ENABLED") or "true").lower() == "true"

    # Read the matching API key (env wins over DB).
    api_key = ""
    if backend == "openai":
        api_key = (await get_setting("OPENAI_API_KEY")) or ""
    elif backend == "anthropic":
        api_key = (await get_setting("ANTHROPIC_API_KEY")) or ""

    return {
        "enabled": enabled,
        "backend": backend,
        "model": non_secret.get("TRACEA_BRAIN_MODEL") or non_secret.get("TRACEA_RCA_MODEL") or "",
        "base_url": non_secret.get("TRACEA_BRAIN_BASE_URL") or non_secret.get("TRACEA_RCA_BASE_URL") or "",
        "prompt_path": non_secret.get("TRACEA_BRAIN_PROMPT_PATH") or "",
        "max_tokens": int(non_secret.get("TRACEA_BRAIN_MAX_TOKENS") or non_secret.get("TRACEA_RCA_MAX_TOKENS") or "2048"),
        "api_key": api_key,
    }
