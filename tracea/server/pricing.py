from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional


_PRICING_CACHE: dict | None = None


def _pricing_path() -> Path:
    """Resolve pricing.json location.

    Lookup order:
    1. $TRACEA_PRICING_PATH (explicit override)
    2. $TRACEA_DATA_DIR/pricing.json (alongside rules/alerts)
    3. ./data/pricing.json (default dev location)
    4. Bundled default (tracea/server/detection/defaults/pricing.json or
       /app/defaults/pricing.json in Docker) — so costs work out-of-box.
    """
    explicit = os.environ.get("TRACEA_PRICING_PATH")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("TRACEA_DATA_DIR", "./data")
    return Path(data_dir) / "pricing.json"


_BUNDLED_DEFAULTS = [
    Path(__file__).parent / "detection" / "defaults",  # local dev
    Path("/app/defaults"),                              # Docker
]


def _bundled_pricing_path() -> Path | None:
    for d in _BUNDLED_DEFAULTS:
        p = d / "pricing.json"
        if p.exists():
            return p
    return None


def _load_pricing() -> dict:
    global _PRICING_CACHE
    if _PRICING_CACHE is not None:
        return _PRICING_CACHE
    path = _pricing_path()
    try:
        _PRICING_CACHE = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        # Fall back to bundled defaults so cost tracking works on a fresh clone.
        bundled = _bundled_pricing_path()
        if bundled is not None:
            try:
                _PRICING_CACHE = json.loads(bundled.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                _PRICING_CACHE = {"models": {}, "provider_avg": {}}
        else:
            _PRICING_CACHE = {"models": {}, "provider_avg": {}}
    return _PRICING_CACHE


def reload_pricing() -> None:
    """Force a reload on next access (called by a future file watcher)."""
    global _PRICING_CACHE
    _PRICING_CACHE = None


def estimate_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> Optional[float]:
    """Return estimated USD cost, or None if uncomputable.

    Per 1M-token pricing. Resolution order:
    1. Exact key: f"{provider}/{model}"
    2. Provider-prefixed model (e.g. claude-sonnet-5 → anthropic/claude-sonnet-5)
    3. Provider average
    4. None (let caller fall back to the old heuristic if it wants)
    """
    if not (input_tokens or output_tokens):
        return None

    pricing = _load_pricing()
    models = pricing.get("models", {})

    def _cost_for(rate: dict) -> float:
        return round(
            (input_tokens * rate.get("input", 0) + output_tokens * rate.get("output", 0))
            / 1_000_000,
            6,
        )

    # 1. Exact
    key = f"{provider}/{model}"
    if key in models:
        return _cost_for(models[key])

    # 2. Try mapping generic provider → canonical prefix
    prefix_map = {
        "claude-code": "anthropic",
        "gemini-cli": "gemini",
        "azure_openai": "openai",
    }
    canon_prefix = prefix_map.get(provider, provider)
    canon_key = f"{canon_prefix}/{model}"
    if canon_key in models:
        return _cost_for(models[canon_key])

    # 2b. Bare model name match (model only, any provider)
    for k, v in models.items():
        if "/" in k and k.split("/", 1)[1] == model:
            return _cost_for(v)

    # 3. Provider average
    avg = pricing.get("provider_avg", {}).get(canon_prefix)
    if avg:
        return _cost_for(avg)

    # 4. Unknown
    return None
