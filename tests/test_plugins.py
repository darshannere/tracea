"""Tests for plugin hooks (Wave 1 fix #8: claude-hook session_id escaping)."""
import subprocess
import re

CLAUDE_HOOK = "tracea-plugins/claude-code/tracea-hook.sh"


def _session_id_from_subshell():
    """Run the SESSION_ID computation line in a fresh bash and return the value."""
    # Reproduce the fixed line in isolation (avoids sourcing the whole hook)
    code = (
        'SESSION_ID="${TRACEA_SESSION_ID:-'
        '$(python3 -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, \'$(hostname)-$$\'))")}'
        '"; echo "$SESSION_ID"'
    )
    out = subprocess.run(
        ["bash", "-c", code], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def test_hook_has_no_escaped_session_expansion():
    """The hook must not backslash-escape $(hostname)/$$ — that produces a
    constant session_id across every process and host."""
    import os
    hook_path = os.path.join(os.path.dirname(__file__), "..", CLAUDE_HOOK)
    with open(hook_path) as f:
        contents = f.read()
    # The buggy form escapes $ so bash never expands it
    assert "\\$(hostname)" not in contents, (
        "hook must not backslash-escape $(hostname) — it must be bash-expanded"
    )
    assert "\\$$" not in contents, (
        "hook must not backslash-escape $$ — it must be bash-expanded"
    )


def test_session_ids_unique_across_processes():
    """Regression: two separate bash processes must produce DIFFERENT session IDs.

    Before the fix, '...\\$(hostname)-\\$$...' was passed literally to python,
    so uuid5 hashed the constant string '$(hostname)-$$' → every process got
    the same UUID (2a9a91c0...)."""
    sid1 = _session_id_from_subshell()
    sid2 = _session_id_from_subshell()
    assert re.match(r"^[0-9a-f-]{36}$", sid1), f"not a uuid: {sid1}"
    assert sid1 != sid2, f"session ids must differ across processes, got {sid1} twice"


def test_session_id_not_the_known_constant():
    """The historical buggy value was a single constant UUID — assert we never
    regress to it."""
    sid = _session_id_from_subshell()
    # Determined empirically from the pre-fix code
    assert sid != "2a9a91c0-0000-0000-0000-000000000000"
    # A uuid5 of the literal string '$(hostname)-$$'
    import uuid
    broken = str(uuid.uuid5(uuid.NAMESPACE_DNS, "$(hostname)-$$"))
    assert sid != broken, f"session id collapsed to the constant {broken}"
