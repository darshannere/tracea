"""Pytest configuration and fixtures for tracea tests."""
import pytest
import sys
import asyncio
from pathlib import Path

# Ensure the package is importable from the source
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
