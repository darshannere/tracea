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

    def test_file_permissions_are_owner_only(self, tmp_path):
        """Regression: config contains the plaintext API key, so the file must
        be 0o600 and the parent dir 0o700. Previously save_config used default
        modes (0o644 / world-readable), leaking the key to other users."""
        nested = tmp_path / ".tracea" / "config.json"
        save_config({"api_key": "secret"}, nested)

        file_mode = nested.stat().st_mode & 0o777
        dir_mode = nested.parent.stat().st_mode & 0o777
        assert file_mode == 0o600, f"config file must be 0o600, got {oct(file_mode)}"
        assert dir_mode == 0o700, f"config dir must be 0o700, got {oct(dir_mode)}"

    def test_existing_file_permissions_tightened_on_resave(self, tmp_path):
        """Re-saving an existing world-readable file must tighten it to 0o600."""
        cfg = tmp_path / "config.json"
        cfg.write_text('{"api_key": "old"}')
        os.chmod(cfg, 0o644)  # world-readable, the insecure state
        assert (cfg.stat().st_mode & 0o777) == 0o644

        save_config({"api_key": "new"}, cfg)
        assert (cfg.stat().st_mode & 0o777) == 0o600
