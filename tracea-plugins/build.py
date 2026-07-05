import os

def build():
    # Change CWD to tracea-plugins directory if needed
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    # 1. Build Python hooks
    with open("shared/tracea-hook.py.template") as f:
        py_template = f.read()

    # Gemini hook
    gemini_hook = py_template.replace("{{agent_title}}", "Gemini").replace("{{default_agent_id}}", "gemini-cli").replace("{{agent_slug}}", "gemini").replace("{{provider}}", "gemini-cli")
    os.makedirs("gemini", exist_ok=True)
    with open("gemini/tracea-hook.py", "w") as f:
        f.write(gemini_hook)
    os.chmod("gemini/tracea-hook.py", 0o755)

    # Kimi hook
    kimi_hook = py_template.replace("{{agent_title}}", "Kimi").replace("{{default_agent_id}}", "kimi").replace("{{agent_slug}}", "kimi").replace("{{provider}}", "kimi")
    os.makedirs("kimi", exist_ok=True)
    with open("kimi/tracea-hook.py", "w") as f:
        f.write(kimi_hook)
    os.chmod("kimi/tracea-hook.py", 0o755)

    # 2. Build TS plugins
    with open("shared/tracea-plugin.ts.template") as f:
        ts_template = f.read()

    # Openclaw hook implementation
    openclaw_impl = """
interface TurnState {
  turnId: string;
  agentId: string;
  sessionKey: string;
  startTime: number;
  toolCalls: Map<string, { startTime: number; toolName: string }>;
}

const turns = new Map<string, TurnState>();

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
"""

    openclaw_plugin = ts_template.replace("{{default_agent_id}}", "openclaw").replace("{{provider}}", "openclaw").replace("{{hook_implementation}}", openclaw_impl)
    os.makedirs("openclaw", exist_ok=True)
    with open("openclaw/tracea-plugin.ts", "w") as f:
        f.write(openclaw_plugin)

    # Opencode hook implementation
    opencode_impl = """import type { Plugin, HookContext } from "opencode";

let sessionId = newSessionId();

function newSessionId(): string {
  return `${CONFIG.agentId}-${Date.now()}-${genId()}`;
}

async function postOpencodeEvent(
  eventType: string,
  content?: string,
  error?: string,
  durationMs = 0,
  toolName?: string,
  toolCallId?: string
): Promise<void> {
  await postEvent({
    events: [
      {
        ...buildEvent(eventType, sessionId, CONFIG.agentId, {
          content: content ?? null,
          tool_call_id: toolCallId ?? null,
          tool_name: toolName ?? null,
          duration_ms: durationMs,
          error: error ?? null,
          metadata: {
            integration: "opencode",
            hook_type: eventType,
            opencode_tool_name: toolName,
          },
        }),
      },
    ],
  });
}

const traceaPlugin: Plugin = {
  name: "tracea",
  version: "0.1.0",

  async onLoad() {},

  hooks: {
    "session.start": async () => {
      sessionId = newSessionId();
      await postOpencodeEvent("session_start");
    },

    "tool.execute.before": async (ctx: HookContext) => {
      const toolName = ctx.tool?.name || "unknown";
      const toolCallId = ctx.toolCallId || genId();
      const args = ctx.args ? JSON.stringify(ctx.args) : undefined;

      ctx.state.traceaToolCallId = toolCallId;
      ctx.state.traceaToolStart = Date.now();

      await postOpencodeEvent("tool_call", args, undefined, 0, toolName, toolCallId);
    },

    "tool.execute.after": async (ctx: HookContext) => {
      const toolName = ctx.tool?.name || "unknown";
      const toolCallId = ctx.state.traceaToolCallId || genId();
      const durationMs = ctx.state.traceaToolStart
        ? Date.now() - ctx.state.traceaToolStart
        : 0;
      const result = ctx.result ? JSON.stringify(ctx.result) : undefined;
      const error = ctx.error?.message;

      await postOpencodeEvent("tool_result", result, error, durationMs, toolName, toolCallId);
    },

    "session.end": async () => {
      await postOpencodeEvent("session_end");
    },
  },
};

export default traceaPlugin;
"""

    opencode_plugin = ts_template.replace("{{default_agent_id}}", "opencode").replace("{{provider}}", "opencode").replace("{{hook_implementation}}", opencode_impl)
    os.makedirs("opencode", exist_ok=True)
    with open("opencode/tracea-plugin.ts", "w") as f:
        f.write(opencode_plugin)

    print("Successfully built all 4 plugins from shared templates!")

if __name__ == "__main__":
    build()
