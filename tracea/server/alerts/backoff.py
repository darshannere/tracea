"""Exponential backoff with jitter for webhook retry."""

import random


def sync_exponential_backoff_with_jitter(
    attempt: int,
    base: float = 2.0,
    max_delay: float = 30.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Synchronous version for non-async contexts."""
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * jitter_ratio)
    return delay + jitter


async def exponential_backoff_with_jitter(
    attempt: int,
    base: float = 2.0,
    max_delay: float = 30.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Calculate sleep time for exponential backoff with jitter."""
    return sync_exponential_backoff_with_jitter(attempt, base, max_delay, jitter_ratio)