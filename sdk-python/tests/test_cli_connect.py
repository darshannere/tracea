import json
import sys
from pathlib import Path
import pytest
from tracea.cli import cmd_connect

# Add SDK path to sys.path if not present
sys.path.insert(0, str(Path(__file__).parent))
from test_cli import MockPrompt


def test_connect_print_claude_code(capsys, monkeypatch):
    mock = MockPrompt({
        "Server URL": "http://localhost:8080",
        "API key (leave blank for dev mode)": "",
    })
    monkeypatch.setattr("tracea.cli._prompt", mock)

    rc = cmd_connect(["claude-code", "--print"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "CLAUDE_CODE_ENABLE_TELEMETRY=1" in out or "CLAUDE_CODE_ENABLE_TELEMETRY='1'" in out
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8080" in out or "OTEL_EXPORTER_OTLP_ENDPOINT='http://localhost:8080'" in out


def test_connect_writes_shell_fragment(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHELL", "/bin/zsh")

    mock = MockPrompt({
        "Server URL": "http://server:8080",
        "API key (leave blank for dev mode)": "",
    })
    monkeypatch.setattr("tracea.cli._prompt", mock)

    rc = cmd_connect(["claude-code"])
    assert rc == 0
    frag = home / ".zshrc.tracea"
    assert frag.exists()
    content = frag.read_text()
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://server:8080" in content or "OTEL_EXPORTER_OTLP_ENDPOINT='http://server:8080'" in content


def test_connect_writes_gemini_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    mock = MockPrompt({
        "Server URL": "http://x:8080",
        "API key (leave blank for dev mode)": "",
    })
    monkeypatch.setattr("tracea.cli._prompt", mock)

    rc = cmd_connect(["gemini"])
    assert rc == 0
    s = json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    assert s["telemetry"]["enabled"] is True
    assert s["GEMINI_TELEMETRY_OTLP_ENDPOINT"] == "http://x:8080"


def test_connect_list(capsys):
    rc = cmd_connect(["--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "claude-code" in out and "gemini" in out
