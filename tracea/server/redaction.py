"""Redaction utility — strips secrets from text before LLM ingestion.

Defense in depth:
1. Pre-LLM: redact event content before building the prompt
2. Post-LLM: validate LLM output before storage
"""

import re

# Default patterns that match common secret formats.
# Each tuple: (compiled regex, replacement string)
DEFAULT_PATTERNS = [
    # OpenAI / Anthropic API keys
    (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "***REDACTED_API_KEY***"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE), "Bearer ***REDACTED_TOKEN***"),
    # Basic auth
    (re.compile(r"Basic\s+[a-zA-Z0-9+/=]{10,}", re.IGNORECASE), "Basic ***REDACTED***"),
    # Generic API keys / tokens in JSON/XML
    (re.compile(r'"(api_?key|token|secret|password|passwd|auth)"\s*[:=]\s*"[^"]{4,}"', re.IGNORECASE), r'"\1": "***REDACTED***"'),
    # Generic API keys / tokens in Python dicts
    (re.compile(r"'(api_?key|token|secret|password|passwd|auth)'\s*[:=]\s*'[^']{4,}'", re.IGNORECASE), r"'\1': '***REDACTED***'"),
    # Env var assignments
    (re.compile(r"([A-Z_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD))\s*=\s*[^\s'\"]+", re.IGNORECASE), r"\1=***REDACTED***"),
    # Connection strings with embedded passwords
    (re.compile(r"(postgresql|mysql|mongodb|redis|amqp)://[^:]+:[^@]+@", re.IGNORECASE), r"\1://***REDACTED***@"),
    # AWS keys
    (re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE), "***REDACTED_AWS_KEY***"),
    # GitHub tokens
    (re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE), "***REDACTED_GH_TOKEN***"),
    # Private keys (begin block)
    (re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE), "-----BEGIN REDACTED PRIVATE KEY-----"),
]


def redact(text: str, patterns: list[tuple[re.Pattern, str]] | None = None) -> str:
    """Return a copy of *text* with secrets replaced.

    Args:
        text: The input string to redact.
        patterns: Optional list of (compiled_regex, replacement) tuples.
                  Defaults to DEFAULT_PATTERNS.

    Returns:
        The redacted string.
    """
    if not text:
        return text

    patterns = patterns or DEFAULT_PATTERNS
    result = text
    for regex, repl in patterns:
        result = regex.sub(repl, result)
    return result


def redact_dict(data: dict, patterns: list[tuple[re.Pattern, str]] | None = None) -> dict:
    """Recursively redact string values in a dictionary.

    Useful for redacting event metadata or content fields.
    """
    if not isinstance(data, dict):
        return data

    patterns = patterns or DEFAULT_PATTERNS
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact(value, patterns)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, patterns)
        elif isinstance(value, list):
            result[key] = [
                redact(item, patterns) if isinstance(item, str) else
                redact_dict(item, patterns) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result
