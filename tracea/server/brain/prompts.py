"""Brain synthesis prompt construction."""

DEFAULT_BRAIN_PROMPT = """You are analyzing an AI agent session. Extract 0-5 items per category:
1. WORKFLOWS: sequences of tool calls that represent repeatable patterns
2. ERROR_FIXES: specific errors and how they were resolved
3. CODEBASE: which files were touched, what they do, why they matter

Format as JSON array: [{"category": "workflow"|"error_fix"|"codebase",
  "title": "short title", "content": "markdown body",
  "confidence": 0.0-1.0 (float)}]
Only extract patterns that would help a future agent. Omit one-off noise.

Events:
{event_summary}
"""


def build_brain_prompt(event_summary: str, custom_template: str | None = None) -> str:
    """Build the brain synthesis prompt from a pre-processed event summary."""
    template = custom_template or DEFAULT_BRAIN_PROMPT
    # Use replace() instead of format() to avoid interpreting JSON braces
    # inside event_summary as format placeholders.
    return template.replace("{event_summary}", event_summary)


def load_custom_prompt(path: str | None) -> str | None:
    """Load custom prompt from file path. Returns None if file not found."""
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None
