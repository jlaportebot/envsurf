"""Tests for envsurf comparison logic."""

import textwrap
from pathlib import Path

from envsurf.compare import compare_env_files


def test_missing_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\n")
    example.write_text("A=1\nB=2\n")

    result = compare_env_files(env, example, check_secrets=False)
    assert result.missing_in_env == ["B"]


def test_extra_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nB=2\nC=3\n")
    example.write_text("A=1\nC=3\n")

    result = compare_env_files(env, example, check_secrets=False)
    assert result.extra_in_env == ["B"]


def test_clean_comparison(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nB=2\n")
    example.write_text("A=1\nB=2\n")

    result = compare_env_files(env, example, check_secrets=False)
    assert result.is_clean is True
    assert result.missing_in_env == []
    assert result.extra_in_env == []


def test_secrets_detected(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("DATABASE_URL=postgres://admin:s3cret@db:5432/mydb\n")
    example.write_text("DATABASE_URL=postgres://user:pass@localhost/db\n")

    result = compare_env_files(env, example, check_secrets=True)
    assert len(result.secret_findings) > 0


def test_secrets_skipped_when_disabled(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("SECRET_KEY=abc123longvaluedef456ghi789jkl012\n")
    example.write_text("SECRET_KEY=changeme\n")

    result = compare_env_files(env, example, check_secrets=False)
    assert len(result.secret_findings) == 0


def test_parse_errors_reported(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("VALID=1\nbroken line\n")
    example.write_text("VALID=1\n")

    result = compare_env_files(env, example, check_secrets=False)
    assert len(result.parse_errors) == 1
