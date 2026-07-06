# Kimi CLI Message Capture Research Findings

**Verdict:** Path D — Tool-calls-only (no message hook surface, no native OTel).

## Investigation Details

1. **Config File Review**:
   - The Moonshot AI Kimi CLI configuration file at `~/.kimi/config.toml` was inspected.
   - The `[[hooks]]` section supports events: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `SessionStart`, and `SessionEnd`.
   - There are no message-level, input/output, or prompt hooks available.

2. **Native Telemetry**:
   - Telemetry option in Kimi configuration is a basic toggle (`telemetry = true`) for Moonshot's internal analytics, not a configurable exporter (unlike Claude Code or Gemini CLI).
   - No native OTel/OTLP export controls are exposed in the CLI commands or settings.

3. **Conclusion & Recommendation**:
   - Document Kimi CLI as "tool calls only" for v2.
   - A reverse-proxy gateway approach (relaying the base URL configured in `[providers]`) remains a theoretical path for v3, but for v2 it remains out of scope.
