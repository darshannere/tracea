"""Pytest configuration and fixtures for tracea tests."""
import pytest
import sys
from pathlib import Path

# Ensure the package is importable from the source
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))