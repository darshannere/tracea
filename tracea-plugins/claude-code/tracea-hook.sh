#!/usr/bin/env bash
# tracea-hook.sh — Claude Code lifecycle hook for tracea observability
#
# Install: Add to ~/.claude/settings.json (or project .claude/settings.json):
#
#   {
#     "hooks": {
#       "PreToolUse": "bash /path/to/tracea-hook.sh pre",
#       "PostToolUse": "bash /path/to/tracea-hook.sh post",
#       "Stop": "bash /path/to/tracea-hook.sh stop"
#     }
#   }
#
# Environment:
#   TRACEA_SERVER_URL  (default: http://localhost:8080)
#   TRACEA_API_KEY     (default: dev-mode)
#   TRACEA_AGENT_ID    (default: claude-code)
#
# Claude Code sends a JSON object on stdin for every hook invocation:
#   PreToolUse:  {session_id, hook_event_name, tool_name, tool_input, ...}
#   PostToolUse: {session_id, hook_event_name, tool_name, tool_input, tool_response, ...}
#   Stop:        {session_id, hook_event_name, stop_hook_active, ...}
#
set -uo pipefail

HOOK_TYPE="${1:-}"
SERVER_URL="${TRACEA_SERVER_URL:-}"
AGENT_ID="${TRACEA_AGENT_ID:-}"
USER_ID="${TRACEA_USER_ID:-}"

# Fallback to ~/.tracea/config.json
if [[ -z "$SERVER_URL" && -f "$HOME/.tracea/config.json" ]]; then
  SERVER_URL=$(jq -r '.server_url // empty' "$HOME/.tracea/config.json" 2>/dev/null)
fi
if [[ -z "$AGENT_ID" && -f "$HOME/.tracea/config.json" ]]; then
  AGENT_ID=$(jq -r '.agent_id // empty' "$HOME/.tracea/config.json" 2>/dev/null)
fi
if [[ -z "$USER_ID" && -f "$HOME/.tracea/config.json" ]]; then
  USER_ID=$(jq -r '.user_id // empty' "$HOME/.tracea/config.json" 2>/dev/null)
fi

SERVER_URL="${SERVER_URL:-http://localhost:8080}"
AGENT_ID="${AGENT_ID:-claude-code}"

# Stable session ID for this Claude process (hostname + pid).
# NOTE: $(hostname) and $$ must be expanded by bash here — do NOT backslash-escape
# them, or every process hashes the same literal string and gets one constant UUID.
SESSION_ID="${TRACEA_SESSION_ID:-$(python3 -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, '$(hostname)-$$'))")}"

# Claude Code passes hook context as JSON on stdin. Read it once and parse
# the fields we need. Fall back to env vars for older Claude Code versions
# that may have used CLAUDE_TOOL_NAME / CLAUDE_TOOL_INPUT.
STDIN_JSON=""
if [[ ! -t 0 ]]; then
  STDIN_JSON=$(cat)
fi

# Extract fields from stdin JSON (empty string if stdin was empty/invalid)
HOOK_TOOL_NAME=""
HOOK_TOOL_INPUT=""
HOOK_SESSION_ID=""
if [[ -n "$STDIN_JSON" ]]; then
  HOOK_TOOL_NAME=$(echo "$STDIN_JSON" | jq -r '.tool_name // empty' 2>/dev/null)
  HOOK_TOOL_INPUT=$(echo "$STDIN_JSON" | jq -c '.tool_input // .tool_response // empty' 2>/dev/null)
  HOOK_SESSION_ID=$(echo "$STDIN_JSON" | jq -r '.session_id // empty' 2>/dev/null)
fi

# Prefer Claude Code's session_id from stdin; fall back to hostname+pid derivation
if [[ -n "$HOOK_SESSION_ID" ]]; then
  SESSION_ID="$HOOK_SESSION_ID"
fi

# Resolve effective tool name + input: stdin JSON first, then env var fallback
EFFECTIVE_TOOL_NAME="${HOOK_TOOL_NAME:-${CLAUDE_TOOL_NAME:-}}"
EFFECTIVE_TOOL_INPUT="${HOOK_TOOL_INPUT:-${CLAUDE_TOOL_INPUT:-null}}"

tracea_post_event() {
  local event_type="$1"
  local content="${2:-}"
  local error="${3:-}"
  local duration_ms="${4:-0}"

  local event_id
  event_id=$(python3 -c "import uuid; print(uuid.uuid4())")

  local tool_call_id="${5:-}"
  if [[ -z "$tool_call_id" ]]; then
    tool_call_id=$(python3 -c "import uuid; print(uuid.uuid4())")
  fi

  local payload
  payload=$(jq -n \
    --arg eid "$event_id" \
    --arg sid "$SESSION_ID" \
    --arg aid "$AGENT_ID" \
    --arg uid "$USER_ID" \
    --arg tid "$tool_call_id" \
    --arg tn "${EFFECTIVE_TOOL_NAME:-}" \
    --arg content "$content" \
    --arg error "$error" \
    --argjson duration "$duration_ms" \
    --arg et "$event_type" \
    '{
      events: [{
        event_id: $eid,
        session_id: $sid,
        agent_id: $aid,
        user_id: $uid,
        sequence: 0,
        timestamp: now|strftime("%Y-%m-%dT%H:%M:%SZ"),
        type: $et,
        provider: "claude-code",
        model: "",
        content: (if $content == "" then null else $content end),
        tool_call_id: $tid,
        tool_name: (if $tn == "" then null else $tn end),
        duration_ms: $duration,
        error: (if $error == "" then null else $error end),
        metadata: {
          hook_type: $et,
          claude_tool_name: $tn
        }
      }]
    }')

  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${SERVER_URL}/api/v1/events/mcp" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>/dev/null || echo "000")

  if [[ "$http_code" != "200" ]]; then
    echo "[tracea] ERROR: server returned HTTP $http_code for $event_type" >&2
  fi
}

case "$HOOK_TYPE" in
  pre)
    TOOL_CALL_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
    tracea_post_event "tool_call" "$EFFECTIVE_TOOL_INPUT" "" 0 "$TOOL_CALL_ID"
    ;;

  post)
    TOOL_CALL_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
    tracea_post_event "tool_result" "$EFFECTIVE_TOOL_INPUT" "" 0 "$TOOL_CALL_ID"
    ;;

  stop)
    tracea_post_event "session_end" "Claude session stopped" "" 0
    ;;

  *)
    echo "Unknown hook type: $HOOK_TYPE" >&2
    echo "Usage: $0 {pre|post|stop}" >&2
    exit 1
    ;;
esac
