// This file is generated from tracea-plugins/shared/tracea-plugin.ts.template
// Do not edit directly.
import * as fs from "fs";
import * as path from "path";

interface TraceaConfig {
  serverUrl: string;
  agentId: string;
  userId: string;
}

function loadConfig(): Partial<TraceaConfig> {
  try {
    const configPath = path.join(
      process.env.HOME || process.env.USERPROFILE || ".",
      ".tracea",
      "config.json"
    );
    const raw = fs.readFileSync(configPath, "utf-8");
    const parsed = JSON.parse(raw);
    return {
      serverUrl: parsed.server_url,
      agentId: parsed.agent_id,
      userId: parsed.user_id,
    };
  } catch {
    return {};
  }
}

const DISCOVERED = loadConfig();

const CONFIG: TraceaConfig = {
  serverUrl: process.env.TRACEA_SERVER_URL || DISCOVERED.serverUrl || "http://localhost:8080",
  agentId: process.env.TRACEA_AGENT_ID || DISCOVERED.agentId || "opencode",
  userId: process.env.TRACEA_USER_ID || DISCOVERED.userId || "",
};

function genId(): string {
  // Use crypto when available, fallback to Math.random
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
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
    provider: "opencode",
    model: overrides.model || "",
    role: null,
    content: null,
    tool_call_id: null,
    tool_name: null,
    duration_ms: 0,
    error: null,
    metadata: {
      integration: "opencode",
      ...overrides.metadata,
    },
    ...overrides,
  };
}

import type { Plugin, HookContext } from "opencode";

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
  toolCallId?: string,
  sessionKey: string = sessionId,
  role?: string
): Promise<void> {
  await postEvent({
    events: [
      {
        ...buildEvent(eventType, sessionKey, CONFIG.agentId, {
          content: content ?? null,
          role: (role as any) ?? null,
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

    "message.part.updated": async (input: any, output: any) => {
      const part = output?.part || output;
      const sessionKey = (input?.session?.id || sessionId) as string;

      if (!part || typeof part !== "object") return;
      const ptype = part.type;

      if (ptype === "text") {
        const role = input?.message?.role || part.role || "assistant";
        const text = part.text || "";
        if (!text) return;
        await postOpencodeEvent(
          "chat.completion",
          text,
          undefined, 0,
          undefined, undefined,
          sessionKey, role,
        );
      }
    },

    "message.updated": async (input: any, output: any) => {
      const msg = output?.message || output;
      const sessionKey = (input?.session?.id || sessionId) as string;
      if (!msg || typeof msg !== "object") return;
      const role = msg.role;
      const parts = msg.parts || [];
      const textParts = parts
        .filter((p: any) => p?.type === "text")
        .map((p: any) => p.text || "")
        .filter(Boolean);
      if (textParts.length === 0) return;
      await postOpencodeEvent(
        "chat.completion",
        textParts.join("\n"),
        undefined, 0,
        undefined, undefined,
        sessionKey, role,
      );
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

