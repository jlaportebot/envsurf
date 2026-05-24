"""Tests for envsurf CLI."""

import textwrap
from pathlib import Path

from envsurf.cli import main


def test_cli_version(capsys) -> None:
    try:
        main(["--version"])
    except SystemExit as e:
        assert e.code == 0
    captured = capsys.readouterr()
    assert "envsurf" in captured.out


def test_cli_clean_pair(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nB=2\n")
    example.write_text("A=1\nB=2\n")

    monkeypatch.chdir(tmp_path)
    try:
        main([str(tmp_path)])
    except SystemExit as e:
        assert e.code == 0


def test_cli_strict_exits_1_on_issues(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nEXTRA=3\n")
    example.write_text("A=1\nB=2\n")

    monkeypatch.chdir(tmp_path)
    try:
        main(["--strict", str(tmp_path)])
        assert False, "Should have exited with code 1"
    except SystemExit as e:
        assert e.code == 1


def test_cli_no_secrets_flag(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("SECRET_KEY=abc123longvaluedef456ghi789jkl012\n")
    example.write_text("SECRET_KEY=changeme\n")

    monkeypatch.chdir(tmp_path)
    try:
        main(["--no-secrets", str(tmp_path)])
    except SystemExit as e:
        # Should succeed because secrets are skipped and no missing/extra
        assert e.code == 0
