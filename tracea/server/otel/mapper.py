from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracea.server.models import TracedEvent


async def spans_to_events_and_persist(spans: list[dict], user_id: str) -> None:
    """Implemented in Task 6."""
    return None


def logs_to_events(logs: list[dict], user_id: str) -> "list[TracedEvent]":
    """Implemented in Tasks 4 and 5."""
    return []


async def persist_metrics(metrics: list[dict], user_id: str) -> None:
    """Implemented in Task 7."""
    return None
