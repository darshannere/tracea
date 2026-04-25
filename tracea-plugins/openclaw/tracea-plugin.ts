/**
 * tracea-plugin.ts — OpenClaw plugin for tracea observability.
 *
 * This plugin captures the full OpenClaw agent lifecycle and sends events
 * to a tracea server. It handles persistent-agent concepts that go beyond
 * simple session-scoped CLI copilots:
 *
 *   - Agent turns (before_agent_start → agent_end)
 *   - Tool calls (before_tool_call → after_tool_call)
 *   - Heartbeats (heartbeat:before → heartbeat:after)
 *   - Memory compaction (before_compaction → after_compaction)
 *   - Gateway lifecycle (gateway_start → gateway_stop)
 *   - Messages (message_received)
 *   - Session boundaries (session_start → session_end)
 *
 * Install:
 *   1. Copy this file to your OpenClaw plugin directory
 *   2. Add to openclaw.json:
 *
 *      {
 *        "plugins": {
 *          "load": { "paths": ["/path/to/tracea-plugins/openclaw"] },
 *          "entries": { "tracea": { "enabled": true } }
 *        }
 *      }
 *
 *   3. Clear jiti cache and restart:
 *      rm -rf /tmp/jiti && systemctl --user restart openclaw-gateway
 */

interface TraceaConfig {
  serverUrl: string;
  agentId: string;
  userId: string;
}

const CONFIG: TraceaConfig = {
  serverUrl: process.env.TRACEA_SERVER_URL || "http://localhost:8080",
  agentId: process.env.TRACEA_AGENT_ID || "openclaw",
  userId: process.env.TRACEA_USER_ID || "",
};

// In-flight turn tracking: sessionKey → turn state
interface TurnState {
  turnId: string;
  agentId: string;
  sessionKey: string;
  startTime: number;
  toolCalls: Map<string, { startTime: number; toolName: string }>;
}

const turns = new Map<string, TurnState>();

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function genId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

async function postEvent(payload: {
  events: Array<Record<string, unknown>>;
}): Promise<void> {
  try {
    const resp = await fetch(`${CONFIG.serverUrl}/api/v1/events/mcp`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      console.error(`[tracea] ERROR: server returned HTTP ${resp.status}`);
    }
  } catch (err) {
    console.error(`[tracea] ERROR: ${err}`);
  }
}

function buildEvent(
  type: string,
  sessionKey: string,
  agentId: string,
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    event_id: genId(),
    session_id: sessionKey,
    agent_id: agentId || CONFIG.agentId,
    user_id: CONFIG.userId,
    sequence: 0,
    timestamp: nowIso(),
    type,
    provider: "openclaw",
    model: overrides.model || "",
    role: null,
    content: null,
    tool_call_id: null,
    tool_name: null,
    duration_ms: 0,
    error: null,
    metadata: {
      integration: "openclaw",
      ...overrides.metadata,
    },
    ...overrides,
  };
}

// ------------------------------------------------------------------
// OpenClaw Plugin API
// ------------------------------------------------------------------

export default function register(api: any): void {
  // --- Agent turn lifecycle ---

  api.on("before_agent_start", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const agentId = ctx?.agent?.id || event?.agentId || CONFIG.agentId;
    const turnId = genId();

    turns.set(sessionKey, {
      turnId,
      agentId,
      sessionKey,
      startTime: Date.now(),
      toolCalls: new Map(),
    });

    await postEvent({
      events: [
        buildEvent("session_start", sessionKey, agentId, {
          metadata: {
            integration: "openclaw",
            hook: "before_agent_start",
            turn_id: turnId,
            channel: event?.channel || ctx?.channel?.id || null,
          },
        }),
      ],
    });
  });

  api.on("agent_end", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const turn = turns.get(sessionKey);
    const agentId = turn?.agentId || ctx?.agent?.id || CONFIG.agentId;
    const durationMs = turn ? Date.now() - turn.startTime : 0;

    // Agent turn completion event
    await postEvent({
      events: [
        buildEvent("agent_turn", sessionKey, agentId, {
          duration_ms: durationMs,
          metadata: {
            integration: "openclaw",
            hook: "agent_end",
            turn_id: turn?.turnId || genId(),
            channel: event?.channel || ctx?.channel?.id || null,
            final_message_count: event?.messages?.length || null,
          },
        }),
      ],
    });

    turns.delete(sessionKey);
  });

  // --- Tool calls ---

  api.on("before_tool_call", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const turn = turns.get(sessionKey);
    const agentId = turn?.agentId || ctx?.agent?.id || CONFIG.agentId;
    const toolCallId = genId();
    const toolName = event?.tool || ctx?.tool?.name || "unknown";

    if (turn) {
      turn.toolCalls.set(toolCallId, {
        startTime: Date.now(),
        toolName,
      });
    }

    await postEvent({
      events: [
        buildEvent("tool_call", sessionKey, agentId, {
          tool_call_id: toolCallId,
          tool_name: toolName,
          content: event?.args ? JSON.stringify(event.args) : null,
          metadata: {
            integration: "openclaw",
            hook: "before_tool_call",
            turn_id: turn?.turnId || null,
          },
        }),
      ],
    });
  });

  api.on("after_tool_call", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const turn = turns.get(sessionKey);
    const agentId = turn?.agentId || ctx?.agent?.id || CONFIG.agentId;
    const toolName = event?.tool || ctx?.tool?.name || "unknown";
    // Try to find the matching tool call by name (best-effort)
    let toolCallId: string | null = null;
    let durationMs = 0;
    if (turn) {
      for (const [tcid, tc] of turn.toolCalls.entries()) {
        if (tc.toolName === toolName) {
          toolCallId = tcid;
          durationMs = Date.now() - tc.startTime;
          turn.toolCalls.delete(tcid);
          break;
        }
      }
    }

    await postEvent({
      events: [
        buildEvent("tool_result", sessionKey, agentId, {
          tool_call_id: toolCallId || genId(),
          tool_name: toolName,
          content: event?.result ? JSON.stringify(event.result) : null,
          error: event?.error || null,
          duration_ms: durationMs,
          metadata: {
            integration: "openclaw",
            hook: "after_tool_call",
            turn_id: turn?.turnId || null,
          },
        }),
      ],
    });
  });

  // --- Messages ---

  api.on("message_received", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const turn = turns.get(sessionKey);
    const agentId = turn?.agentId || ctx?.agent?.id || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("chat.completion", sessionKey, agentId, {
          role: "user",
          content: event?.text || event?.content || null,
          metadata: {
            integration: "openclaw",
            hook: "message_received",
            turn_id: turn?.turnId || null,
            channel: event?.channel || ctx?.channel?.id || null,
          },
        }),
      ],
    });
  });

  // --- Heartbeats ---

  api.on("heartbeat:before", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const agentId = ctx?.agent?.id || event?.agentId || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("heartbeat", sessionKey, agentId, {
          metadata: {
            integration: "openclaw",
            hook: "heartbeat:before",
            reason: event?.reason || null,
            channel: event?.channel || null,
          },
        }),
      ],
    });
  });

  api.on("heartbeat:after", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const agentId = ctx?.agent?.id || event?.agentId || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("heartbeat", sessionKey, agentId, {
          duration_ms: event?.durationMs || 0,
          error: event?.status === "failed" ? event?.reason || "heartbeat failed" : null,
          metadata: {
            integration: "openclaw",
            hook: "heartbeat:after",
            status: event?.status || "unknown",
            channel: event?.channel || null,
            has_media: event?.hasMedia || false,
          },
        }),
      ],
    });
  });

  // --- Memory compaction ---

  api.on("before_compaction", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const turn = turns.get(sessionKey);
    const agentId = turn?.agentId || ctx?.agent?.id || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("memory_compaction", sessionKey, agentId, {
          metadata: {
            integration: "openclaw",
            hook: "before_compaction",
            turn_id: turn?.turnId || null,
            message_count_before: event?.messageCount || null,
          },
        }),
      ],
    });
  });

  api.on("after_compaction", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const turn = turns.get(sessionKey);
    const agentId = turn?.agentId || ctx?.agent?.id || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("memory_compaction", sessionKey, agentId, {
          metadata: {
            integration: "openclaw",
            hook: "after_compaction",
            turn_id: turn?.turnId || null,
            message_count_after: event?.messageCount || null,
            tokens_saved: event?.tokensSaved || null,
          },
        }),
      ],
    });
  });

  // --- Gateway lifecycle ---

  api.on("gateway_start", async (event: any, ctx: any) => {
    await postEvent({
      events: [
        buildEvent("gateway_event", "gateway", CONFIG.agentId, {
          metadata: {
            integration: "openclaw",
            hook: "gateway_start",
            gateway_version: event?.version || null,
          },
        }),
      ],
    });
  });

  api.on("gateway_stop", async (event: any, ctx: any) => {
    await postEvent({
      events: [
        buildEvent("gateway_event", "gateway", CONFIG.agentId, {
          metadata: {
            integration: "openclaw",
            hook: "gateway_stop",
            reason: event?.reason || null,
          },
        }),
      ],
    });
  });

  // --- Session boundaries (explicit) ---

  api.on("session_start", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const agentId = ctx?.agent?.id || event?.agentId || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("session_start", sessionKey, agentId, {
          metadata: {
            integration: "openclaw",
            hook: "session_start",
            channel: event?.channel || ctx?.channel?.id || null,
          },
        }),
      ],
    });
  });

  api.on("session_end", async (event: any, ctx: any) => {
    const sessionKey = ctx?.session?.key || event?.sessionKey || "unknown";
    const agentId = ctx?.agent?.id || event?.agentId || CONFIG.agentId;

    await postEvent({
      events: [
        buildEvent("session_end", sessionKey, agentId, {
          metadata: {
            integration: "openclaw",
            hook: "session_end",
            reason: event?.reason || null,
          },
        }),
      ],
    });
  });

  console.log("[tracea] OpenClaw plugin registered — 15 hooks active");
}
