"""Exponential backoff with jitter for webhook retry."""

import asyncio
import random


async def exponential_backoff_with_jitter(
    attempt: int,
    base: float = 2.0,
    max_delay: float = 30.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Calculate sleep time for exponential backoff with jitter.

    Args:
        attempt: Zero-based attempt number (0 = first retry)
        base: Base delay in seconds (default 2.0)
        max_delay: Maximum delay cap in seconds
        jitter_ratio: Jitter as a ratio of the base delay (0.5 = 50% jitter)

    Returns:
        Sleep time in seconds

    Examples:
        attempt=0 -> ~2.0-3.0s (2 + jitter)
        attempt=1 -> ~4.0-6.0s (4 + jitter)
        attempt=2 -> ~8.0-12.0s (8 + jitter, capped at 30)
    """
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * jitter_ratio)
    return delay + jitter


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