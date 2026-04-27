"""Tests for tracea config discovery."""
import json
import os
from pathlib import Path
import pytest
from tracea.config_loader import discover_config, save_config, config_path


@pytest.fixture
def temp_config(tmp_path):
    """Provide a temporary config path and clean up afterwards."""
    original = os.environ.get("TRACEA_CONFIG_PATH")
    custom_path = tmp_path / "config.json"
    yield custom_path
    if custom_path.exists():
        custom_path.unlink()


class TestDiscoverConfig:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        assert discover_config(missing) == {}

    def test_valid_file_loaded(self, temp_config):
        temp_config.write_text(json.dumps({"user_id": "alice", "server_url": "http://test"}))
        cfg = discover_config(temp_config)
        assert cfg["user_id"] == "alice"
        assert cfg["server_url"] == "http://test"

    def test_malformed_file_returns_empty_dict(self, temp_config):
        temp_config.write_text("not json")
        assert discover_config(temp_config) == {}


class TestSaveConfig:
    def test_creates_directories_and_file(self, tmp_path):
        nested = tmp_path / ".tracea" / "config.json"
        save_config({"user_id": "bob"}, nested)
        assert nested.exists()
        loaded = json.loads(nested.read_text())
        assert loaded["user_id"] == "bob"
