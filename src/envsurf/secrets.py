"""Detect leaked secrets and sensitive values in .env files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Patterns that indicate a real secret (not a placeholder)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Common secret key names
    ("secret_key", re.compile(r"(?i).*(?:secret|token|api.?key|private.?key|password|passwd|auth).*$")),
    # Looks like a real value: 20+ chars of base64/hex/alphanumeric
    ("high_entropy", re.compile(r"^[A-Za-z0-9+/=_-]{20,}$")),
    # Common credential formats
    ("aws_key", re.compile(r"^(?:AKIA|ASIA|AIDA)[0-9A-Z]{16,}$")),
    ("github_token", re.compile(r"^(?:gh[ps]_|github_pat_)[A-Za-z0-9_]{30,}$")),
    ("jwt", re.compile(r"^eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")),
    # URL with embedded credentials
    ("url_with_creds", re.compile(r"(?i)^[a-z][a-z0-9+.-]*://[^:\s]+:[^@\s]+@")),
]

# Values that look like placeholders (not secrets)
_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^$", re.IGNORECASE),                            # empty
    re.compile(r"^\s*$", re.IGNORECASE),                         # whitespace only
    re.compile(r"^(?:change_?me|your[_-].+|xxx+|placeholder|todo|fixme|example|default|fill[_-]?in|required|changeme|notset|none|null|n/a|tbd)$", re.IGNORECASE),
    re.compile(r"^<.+>$", re.IGNORECASE),                        # <value>
    re.compile(r"^\[.+\]$", re.IGNORECASE),                      # [value]
    re.compile(r"^\$\{.+\}$", re.IGNORECASE),                    # ${VAR}
    re.compile(r"^\$\w+$", re.IGNORECASE),                       # $VAR
    re.compile(r"^(?:true|false|yes|no|0|1|on|off)$", re.IGNORECASE),  # booleans
]


@dataclass
class SecretFinding:
    """A detected potential secret."""

    key: str
    value: str
    line_number: int
    rule: str
    severity: str = "warning"  # "critical" or "warning"


def is_placeholder(value: str) -> bool:
    """Check if a value looks like a placeholder rather than a real secret."""
    stripped = value.strip()
    if not stripped:
        return True
    return any(p.match(stripped) for p in _PLACEHOLDER_PATTERNS)


def detect_secrets(key: str, value: str, line_number: int) -> List[SecretFinding]:
    """Detect potential secrets in a key-value pair."""
    findings: List[SecretFinding] = []

    # Skip placeholder values
    if is_placeholder(value):
        return findings

    # Check key name patterns
    key_matches = [name for name, pat in _SECRET_PATTERNS if name == "secret_key" and pat.match(key)]
    if key_matches:
        # Key name suggests it's a secret — check if value looks real
        if len(value) >= 8 and not is_placeholder(value):
            # Determine severity
            severity = "critical" if any(
                p[0] in ("aws_key", "github_token", "jwt", "url_with_creds")
                and p[1].match(value)
                for p in _SECRET_PATTERNS
            ) else "warning"
            findings.append(SecretFinding(
                key=key,
                value=value,
                line_number=line_number,
                rule="secret_key_name",
                severity=severity,
            ))

    # Check value patterns (even if key name doesn't suggest secret)
    for name, pattern in _SECRET_PATTERNS:
        if name == "secret_key":
            continue  # already handled
        if pattern.match(value):
            findings.append(SecretFinding(
                key=key,
                value=value,
                line_number=line_number,
                rule=name,
                severity="critical" if name in ("aws_key", "github_token", "jwt", "url_with_creds") else "warning",
            ))

    return findings
