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
# Claude Code sets these env vars on every hook invocation:
#   CLAUDE_TOOL_NAME   — name of the tool being invoked
#   CLAUDE_TOOL_INPUT  — JSON string of tool arguments
#
set -euo pipefail

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

# Stable session ID for this Claude process (hostname + pid)
SESSION_ID="${TRACEA_SESSION_ID:-$(python3 -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, '\$(hostname)-\$$'))")}"

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
    --arg tn "${CLAUDE_TOOL_NAME:-}" \
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
    INPUT_JSON="${CLAUDE_TOOL_INPUT:-null}"
    TOOL_CALL_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
    # Persist tool_call_id for the post hook (Claude runs hooks sequentially)
    echo "$TOOL_CALL_ID" > "/tmp/tracea-last-tcid"
    tracea_post_event "tool_call" "$INPUT_JSON" "" 0 "$TOOL_CALL_ID"
    ;;

  post)
    INPUT_JSON="${CLAUDE_TOOL_INPUT:-null}"
    TOOL_CALL_ID=""
    if [[ -f "/tmp/tracea-last-tcid" ]]; then
      TOOL_CALL_ID=$(cat "/tmp/tracea-last-tcid")
      rm -f "/tmp/tracea-last-tcid"
    fi
    tracea_post_event "tool_result" "$INPUT_JSON" "" 0 "$TOOL_CALL_ID"
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
