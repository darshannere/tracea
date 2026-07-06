import os
import pytest
from tracea.server.pricing import estimate_cost

def test_pricing_estimation():
    # Exact key
    assert estimate_cost("anthropic", "claude-sonnet-5-20250929", 1_000_000, 0) == 3.0
    # Map claude-code provider → anthropic prefix
    assert estimate_cost("claude-code", "claude-sonnet-5", 1_000_000, 0) == 3.0
    # Bare model match
    assert estimate_cost("unknown-provider", "gpt-4o", 1_000_000, 0) == 2.5
    # Provider average fallback
    assert estimate_cost("gemini-cli", "some-new-gemini", 1_000_000, 0) == 1.25
    # Unknown provider → None
    assert estimate_cost("mystery", "x", 100, 100) is None
