"""tracea CLI — ``tracea init`` wizard and future commands."""
from __future__ import annotations
import os
import shlex
import sys
from pathlib import Path
from tracea.config_loader import save_config, config_path


_AGENT_CONFIGS = {
    "claude-code": {
        "display": "Claude Code",
        "method": "shell_env",
        "env": [
            ("CLAUDE_CODE_ENABLE_TELEMETRY", "1"),
            ("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
            ("OTEL_EXPORTER_OTLP_ENDPOINT", "{server_url}"),
            ("OTEL_LOG_RAW_API_BODIES", "1"),
        ],
        "auth_env": [("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20{api_key}")],
        "docs": "https://docs.claude.com/en/docs/claude-code/monitoring-usage",
    },
    "gemini": {
        "display": "Gemini CLI",
        "method": "gemini_settings",
        "settings_key": "GEMINI_TELEMETRY_OTLP_ENDPOINT",
        "docs": "https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/telemetry.md",
    },
}


def _prompt(question: str, default: str = "") -> str:
    """Read a line from stdin with an optional default."""
    if default:
        full = f"{question} [{default}]: "
    else:
        full = f"{question}: "
    try:
        answer = input(full).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
    return answer if answer else default


def cmd_init() -> int:
    """Interactive wizard that writes ``~/.tracea/config.json``."""
    print("tracea init — configure your local tracea client")
    print("-" * 50)

    server_url = _prompt("Server URL", "http://localhost:8080")
    api_key = _prompt("API key", "dev-mode")
    user_id = _prompt("User ID (must match a user in the web UI)")
    agent_id = _prompt("Agent ID (optional)", "")

    cfg: dict[str, str] = {
        "server_url": server_url,
        "api_key": api_key,
    }
    if user_id:
        cfg["user_id"] = user_id
    if agent_id:
        cfg["agent_id"] = agent_id

    save_config(cfg)
    print(f"\nConfig saved to {config_path()}")
    print("You can override any value later with environment variables:")
    print("  TRACEA_SERVER_URL, TRACEA_API_KEY, TRACEA_USER_ID, TRACEA_AGENT_ID")
    return 0


def cmd_connect(argv: list[str]) -> int:
    """`tracea connect <agent>` — write OTLP config for an agent."""
    if len(argv) < 1 or argv[0] in ("-h", "--help"):
        _print_connect_help()
        return 0
    if argv[0] in ("--list", "-l"):
        print("Available agents:")
        for slug, cfg in _AGENT_CONFIGS.items():
            print(f"  {slug:14} via {cfg['method']}")
        return 0

    agent = argv[0]
    print_only = "--print" in argv

    if agent not in _AGENT_CONFIGS:
        print(f"Unknown agent: {agent}", file=sys.stderr)
        print(f"Available: {', '.join(_AGENT_CONFIGS.keys())}", file=sys.stderr)
        return 1

    cfg = _AGENT_CONFIGS[agent]
    print(f"tracea connect — configure {cfg['display']} to export to tracea")
    print("-" * 50)

    server_url = _prompt("Server URL", "http://localhost:8080")
    api_key = _prompt("API key (leave blank for dev mode)", "")

    if cfg["method"] == "shell_env":
        return _write_shell_env(cfg, server_url, api_key, print_only)
    elif cfg["method"] == "gemini_settings":
        return _write_gemini_settings(cfg, server_url, api_key, print_only)
    else:
        print(f"Unknown method: {cfg['method']}", file=sys.stderr)
        return 1


def _write_shell_env(cfg, server_url, api_key, print_only) -> int:
    lines = [f"# tracea OTLP export for {cfg['display']}"]
    for k, v in cfg["env"]:
        lines.append(f"export {k}={shlex.quote(v.format(server_url=server_url, api_key=api_key))}")
    if api_key:
        for k, v in cfg.get("auth_env", []):
            lines.append(f"export {k}={shlex.quote(v.format(server_url=server_url, api_key=api_key))}")
    block = "\n".join(lines) + "\n"

    if print_only:
        print(block)
        return 0

    # Pick shell profile fragment path
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        frag_path = Path.home() / ".zshrc.tracea"
        source_line = '[ -f ~/.zshrc.tracea ] && source ~/.zshrc.tracea'
        profile = Path.home() / ".zshrc"
    elif "bash" in shell:
        frag_path = Path.home() / ".bashrc.tracea"
        source_line = '[ -f ~/.bashrc.tracea ] && source ~/.bashrc.tracea'
        profile = Path.home() / ".bashrc"
    else:
        frag_path = Path.home() / ".tracea_env.sh"
        source_line = f'[ -f {frag_path} ] && source {frag_path}'
        profile = None

    frag_path.write_text(block)
    print(f"Wrote: {frag_path}")
    print("\nAdd this line to your shell profile to load it:")
    print(f"  {source_line}")
    if profile:
        print(f"\nOr run:  echo '{source_line}' >> {profile}")
    print(f"\nThen restart your shell or: source {frag_path}")
    return 0


def _write_gemini_settings(cfg, server_url, api_key, print_only) -> int:
    import json
    settings_path = Path.cwd() / ".gemini" / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            pass

    settings.setdefault("telemetry", {})
    settings["telemetry"]["enabled"] = True
    settings["telemetry"]["target"] = "local"
    settings[cfg["settings_key"]] = server_url
    if api_key:
        # Gemini supports the standard OTEL_EXPORTER_OTLP_HEADERS env; we
        # document it but the settings.json doesn't carry env vars — print
        # an extra export line instead.
        pass

    if print_only:
        print(json.dumps(settings, indent=2))
        return 0

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Wrote: {settings_path}")
    print(f"Docs: {cfg['docs']}")
    return 0


def _print_connect_help() -> None:
    print("Usage: tracea connect <agent> [--print] [--list]")
    print("")
    print("Configures an agent to export OTLP telemetry to tracea.")
    print("")
    print("Agents:")
    for slug, cfg in _AGENT_CONFIGS.items():
        print(f"  {slug:14} {cfg['display']}")
    print("")
    print("Options:")
    print("  --print   Print config to stdout; don't write any file")
    print("  --list    Show available agents")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: tracea <command>", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  init      — run the setup wizard", file=sys.stderr)
        print("  connect   — configure an agent to export OTLP to tracea", file=sys.stderr)
        return 1

    cmd = sys.argv[1]
    if cmd == "init":
        return cmd_init()
    if cmd == "connect":
        return cmd_connect(sys.argv[2:])

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
