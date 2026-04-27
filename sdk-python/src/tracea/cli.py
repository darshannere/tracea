"""tracea CLI — ``tracea init`` wizard and future commands."""
from __future__ import annotations
import sys
from tracea.config_loader import save_config, config_path


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


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: tracea <command>", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  init   — run the setup wizard", file=sys.stderr)
        return 1

    cmd = sys.argv[1]
    if cmd == "init":
        return cmd_init()

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
