"""Centralised redaction for sensitive data.

All secrets, tokens, passwords, cookies, and emails are replaced with [REDACTED].
This is applied before:

- Writing log lines
- Returning data through API responses
- Storing in runtime reports
"""

import re

REDACTION = "[REDACTED]"

_PREFIX_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(passwd\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(token\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(refresh_token\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(access_token\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(client_secret\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(cookie\s*[:=]\s*)[^\r\n]+"),
]

_FULL_PATTERNS = [
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
    re.compile(r"(https?://[^\s?]+\?[^\s]*(?:token|secret|auth|key)=[^\s]+)", re.IGNORECASE),
]


def redact_text(value: str) -> str:
    """Return *value* with all known sensitive patterns replaced."""
    redacted = value
    for pattern in _PREFIX_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}{REDACTION}", redacted)
    for pattern in _FULL_PATTERNS:
        redacted = pattern.sub(REDACTION, redacted)
    return redacted


def redact_lines(lines: list[str]) -> list[str]:
    """Redact each line in a list."""
    return [redact_text(line) for line in lines]


def redact_dict(data: dict, keys_to_mask: frozenset | None = None) -> dict:
    """Return a shallow copy of *data* with specified key values redacted.

    If *keys_to_mask* is None, common secret keys are guessed.
    """
    if keys_to_mask is None:
        keys_to_mask = frozenset(k.lower() for k in data)
    redacted: dict = {}
    for k, v in data.items():
        if isinstance(v, str) and k.lower() in keys_to_mask:
            # Check if it looks like a secret (non-empty, not already redacted)
            if v.strip() and v != REDACTION:
                redacted[k] = REDACTION
            else:
                redacted[k] = v
        else:
            redacted[k] = v
    return redacted
