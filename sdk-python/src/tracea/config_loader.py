"""Shared config discovery for tracea CLI tools and SDK.

Reads ``~/.tracea/config.json`` as a fallback when env vars / explicit params
are not provided.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".tracea" / "config.json"


def config_path() -> Path:
    """Return the platform-appropriate path to the tracea config file."""
    return DEFAULT_CONFIG_PATH


def discover_config(path: Path | None = None) -> dict[str, Any]:
    """Load ``~/.tracea/config.json`` if it exists.

    Returns an empty dict when the file is missing or unreadable so that
    callers can safely merge without handling exceptions.
    """
    target = path or DEFAULT_CONFIG_PATH
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    """Write config to ``~/.tracea/config.json``, creating parent dirs if needed."""
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
