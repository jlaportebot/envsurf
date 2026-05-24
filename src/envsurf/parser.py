"""Parse .env files into structured data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Pattern: KEY=VALUE, with optional export and inline comments
_ENV_LINE = re.compile(
    r"""^\s*
    (?:export\s+)?          # optional 'export'
    (?P<key>[A-Za-z_][A-Za-z0-9_]*)  # variable name
    \s*=\s*                 # assignment
    (?P<value>              # value group
        "(?:[^"\\]|\\.)*"   # double-quoted
        |'(?:[^'\\]|\\.)*'  # single-quoted
        |[^\s#]*            # unquoted
    )
    \s*(?:\#.*)?$           # optional inline comment
    """,
    re.VERBOSE,
)

# Comment or blank line
_COMMENT_OR_BLANK = re.compile(r"^\s*(?:#.*)?$")


@dataclass
class EnvEntry:
    """A single parsed env variable."""

    key: str
    value: str
    line_number: int
    is_quoted: bool = False

    @property
    def raw_value(self) -> str:
        """Return the value without surrounding quotes."""
        v = self.value
        if self.is_quoted and len(v) >= 2:
            if (v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'"):
                return v[1:-1]
        return v


@dataclass
class EnvFile:
    """Parsed result of an .env file."""

    path: Path
    entries: List[EnvEntry] = field(default_factory=list)
    parse_errors: List[Tuple[int, str]] = field(default_factory=list)

    @property
    def keys(self) -> set[str]:
        return {e.key for e in self.entries}

    def get(self, key: str) -> Optional[EnvEntry]:
        for e in self.entries:
            if e.key == key:
                return e
        return None

    def as_dict(self) -> Dict[str, str]:
        return {e.key: e.raw_value for e in self.entries}


def parse_env(path: Path) -> EnvFile:
    """Parse an .env file into an EnvFile object."""
    result = EnvFile(path=path)

    if not path.exists():
        return result

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()

        if _COMMENT_OR_BLANK.match(line):
            continue

        m = _ENV_LINE.match(line)
        if m:
            key = m.group("key")
            value = m.group("value")
            is_quoted = bool(value and value[0] in ('"', "'"))
            result.entries.append(EnvEntry(key=key, value=value, line_number=line_no, is_quoted=is_quoted))
        else:
            result.parse_errors.append((line_no, raw_line))

    return result
