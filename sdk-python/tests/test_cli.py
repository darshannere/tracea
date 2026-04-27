"""Tests for tracea CLI."""
import json
from pathlib import Path
import pytest
from tracea.cli import cmd_init
from tracea.config_loader import discover_config


class MockPrompt:
    """Stateful mock for _prompt that returns configured answers."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, question, default=""):
        self.calls.append((question, default))
        return self.answers.get(question, default)


class TestInitCommand:
    def test_init_creates_config(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("tracea.config_loader.DEFAULT_CONFIG_PATH", config_file)

        mock = MockPrompt({
            "Server URL": "http://localhost:9000",
            "API key": "my-key",
            "User ID (must match a user in the web UI)": "darshan",
            "Agent ID (optional)": "test-agent",
        })
        monkeypatch.setattr("tracea.cli._prompt", mock)

        assert cmd_init() == 0
        cfg = discover_config(config_file)
        assert cfg["server_url"] == "http://localhost:9000"
        assert cfg["api_key"] == "my-key"
        assert cfg["user_id"] == "darshan"
        assert cfg["agent_id"] == "test-agent"

    def test_init_skips_optional_agent_id(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("tracea.config_loader.DEFAULT_CONFIG_PATH", config_file)

        mock = MockPrompt({
            "Server URL": "http://localhost:8080",
            "API key": "dev-mode",
            "User ID (must match a user in the web UI)": "alice",
            "Agent ID (optional)": "",
        })
        monkeypatch.setattr("tracea.cli._prompt", mock)

        assert cmd_init() == 0
        cfg = discover_config(config_file)
        assert "agent_id" not in cfg
        assert cfg["user_id"] == "alice"
