"""Compare .env against .env.example to find drift and issues."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .parser import EnvFile, parse_env
from .secrets import SecretFinding, detect_secrets


@dataclass
class DiffResult:
    """Result of comparing two .env files."""

    missing_in_env: List[str] = field(default_factory=list)          # keys in example but not in env
    extra_in_env: List[str] = field(default_factory=list)            # keys in env but not in example
    value_mismatches: List[tuple[str, str, str]] = field(default_factory=list)  # (key, example_val, env_val)
    secret_findings: List[SecretFinding] = field(default_factory=list)
    parse_errors: List[tuple[Path, int, str]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            not self.missing_in_env
            and not self.extra_in_env
            and not self.secret_findings
            and not self.parse_errors
        )


def compare_env_files(env_path: Path, example_path: Path, *, check_secrets: bool = True) -> DiffResult:
    """Compare an .env file against its .env.example counterpart."""
    result = DiffResult()

    env_file = parse_env(env_path)
    example_file = parse_env(example_path)

    # Collect parse errors
    for line_no, raw_line in env_file.parse_errors:
        result.parse_errors.append((env_path, line_no, raw_line))
    for line_no, raw_line in example_file.parse_errors:
        result.parse_errors.append((example_path, line_no, raw_line))

    env_keys = env_file.keys
    example_keys = example_file.keys

    # Missing in env (present in example)
    result.missing_in_env = sorted(example_keys - env_keys)

    # Extra in env (not in example)
    result.extra_in_env = sorted(env_keys - example_keys)

    # Check for secrets
    if check_secrets:
        for entry in env_file.entries:
            findings = detect_secrets(entry.key, entry.raw_value, entry.line_number)
            result.secret_findings.extend(findings)

    return result
