"""Tests for envsurf parser."""

import textwrap
from pathlib import Path

from envsurf.parser import parse_env


def test_parse_simple(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(textwrap.dedent("""\
        DB_HOST=localhost
        DB_PORT=5432
        API_KEY=abc123
    """))
    result = parse_env(env)
    assert len(result.entries) == 3
    assert result.entries[0].key == "DB_HOST"
    assert result.entries[0].raw_value == "localhost"
    assert result.entries[1].key == "DB_PORT"
    assert result.entries[1].raw_value == "5432"


def test_parse_quoted_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(textwrap.dedent("""\
        MESSAGE="hello world"
        SINGLE='it\\'s fine'
    """))
    result = parse_env(env)
    assert result.entries[0].raw_value == "hello world"
    assert result.entries[1].raw_value == "it\\'s fine"


def test_parse_comments_and_blanks(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(textwrap.dedent("""\
        # This is a comment
        KEY1=val1

        KEY2=val2  # inline comment
    """))
    result = parse_env(env)
    assert len(result.entries) == 2
    assert result.entries[0].key == "KEY1"
    assert result.entries[1].key == "KEY2"


def test_parse_export_prefix(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("export FOO=bar\n")
    result = parse_env(env)
    assert len(result.entries) == 1
    assert result.entries[0].key == "FOO"
    assert result.entries[0].raw_value == "bar"


def test_parse_errors(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VALID=yes\nthis is broken\n")
    result = parse_env(env)
    assert len(result.entries) == 1
    assert len(result.parse_errors) == 1
    assert result.parse_errors[0][0] == 2  # line number


def test_keys_set(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nB=2\n")
    result = parse_env(env)
    assert result.keys == {"A", "B"}


def test_as_dict(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nB=2\n")
    result = parse_env(env)
    assert result.as_dict() == {"A": "1", "B": "2"}


def test_nonexistent_file(tmp_path: Path) -> None:
    result = parse_env(tmp_path / ".env.does_not_exist")
    assert result.entries == []
    assert result.parse_errors == []
