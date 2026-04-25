/**
 * tracea-plugin.ts — OpenCode plugin for tracea observability.
 *
 * Install: Copy to ~/.opencode/plugins/tracea-plugin.ts
 *          or .opencode/plugins/tracea-plugin.ts in your repo.
 *
 * OpenCode will auto-discover and load the plugin.
 */

import type { Plugin, HookContext } from "opencode";

interface TraceaConfig {
  serverUrl: string;
  agentId: string;
  userId: string;
}

const DEFAULT_CONFIG: TraceaConfig = {
  serverUrl: process.env.TRACEA_SERVER_URL || "http://localhost:8080",
  agentId: process.env.TRACEA_AGENT_ID || "opencode",
  userId: process.env.TRACEA_USER_ID || "",
};

const sessionId = `${DEFAULT_CONFIG.agentId}-${Date.now()}-${crypto.randomUUID()}`;

async function postEvent(
  eventType: string,
  content?: string,
  error?: string,
  durationMs = 0,
  toolName?: string,
  toolCallId?: string,
): Promise<void> {
  const payload = {
    events: [
      {
        event_id: crypto.randomUUID(),
        session_id: sessionId,
        agent_id: DEFAULT_CONFIG.agentId,
        user_id: DEFAULT_CONFIG.userId,
        sequence: 0,
        timestamp: new Date().toISOString(),
        type: eventType,
        provider: "opencode",
        model: "",
        content: content ?? null,
        tool_call_id: toolCallId ?? null,
        tool_name: toolName ?? null,
        duration_ms: durationMs,
        error: error ?? null,
        metadata: {
          hook_type: eventType,
          opencode_tool_name: toolName,
        },
      },
    ],
  };

  try {
    const resp = await fetch(`${DEFAULT_CONFIG.serverUrl}/api/v1/events/mcp`, {
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

const traceaPlugin: Plugin = {
  name: "tracea",
  version: "0.1.0",

  async onLoad() {
    await postEvent("session_start");
  },

  hooks: {
    "tool.execute.before": async (ctx: HookContext) => {
      const toolName = ctx.tool?.name || "unknown";
      const toolCallId = ctx.toolCallId || crypto.randomUUID();
      const args = ctx.args ? JSON.stringify(ctx.args) : undefined;

      ctx.state.traceaToolCallId = toolCallId;
      ctx.state.traceaToolStart = Date.now();

      await postEvent("tool_call", args, undefined, 0, toolName, toolCallId);
    },

    "tool.execute.after": async (ctx: HookContext) => {
      const toolName = ctx.tool?.name || "unknown";
      const toolCallId = ctx.state.traceaToolCallId || crypto.randomUUID();
      const durationMs = ctx.state.traceaToolStart
        ? Date.now() - ctx.state.traceaToolStart
        : 0;
      const result = ctx.result ? JSON.stringify(ctx.result) : undefined;
      const error = ctx.error?.message;

      await postEvent("tool_result", result, error, durationMs, toolName, toolCallId);
    },

    "session.end": async () => {
      await postEvent("session_end");
    },
  },
};

export default traceaPlugin;
