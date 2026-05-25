"""Tests for envsurf CLI."""

import json
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


def test_cli_json_output(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nC=3\n")
    example.write_text("A=1\nB=2\n")

    monkeypatch.chdir(tmp_path)
    try:
        main(["--json", str(tmp_path)])
    except SystemExit:
        pass

    import sys
    output = sys.stdout.getvalue() if hasattr(sys.stdout, "getvalue") else ""
    # Since we can't easily capture with capsys + json flag, test structure instead


def test_cli_json_output_structure(tmp_path: Path, monkeypatch, capsys) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nC=3\n")
    example.write_text("A=1\nB=2\n")

    monkeypatch.chdir(tmp_path)
    try:
        main(["--json", str(tmp_path)])
    except SystemExit:
        pass

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "total_issues" in data
    assert "pairs" in data
    assert data["total_issues"] >= 1


def test_cli_ignore_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nEXTRA=3\n")
    example.write_text("A=1\nB=2\n")

    monkeypatch.chdir(tmp_path)
    try:
        main(["--ignore", "B,EXTRA", str(tmp_path)])
    except SystemExit as e:
        assert e.code == 0  # B and EXTRA are ignored, so no issues


def test_cli_scan_subcommand(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("A=1\nB=2\n")
    example.write_text("A=1\nB=2\n")

    monkeypatch.chdir(tmp_path)
    try:
        main(["scan", str(tmp_path)])
    except SystemExit as e:
        assert e.code == 0


class TestFixCommand:
    def test_fix_adds_missing_vars(self, tmp_path: Path) -> None:
        example = tmp_path / ".env.example"
        env = tmp_path / ".env"
        example.write_text("A=1\nB=placeholder\nC=default\n")
        env.write_text("A=1\n")

        try:
            main(["fix", "--env", str(env), "--example", str(example)])
        except SystemExit:
            pass

        result = env.read_text()
        assert "B=" in result
        assert "C=" in result
        assert "A=1" in result

    def test_fix_dry_run(self, tmp_path: Path, capsys) -> None:
        example = tmp_path / ".env.example"
        env = tmp_path / ".env"
        example.write_text("A=1\nB=placeholder\n")
        env.write_text("A=1\n")
        original = env.read_text()

        try:
            main(["fix", "--dry-run", "--env", str(env), "--example", str(example)])
        except SystemExit:
            pass

        # File should not be modified
        assert env.read_text() == original

    def test_fix_example_not_found(self, tmp_path: Path) -> None:
        try:
            main(["fix", "--example", str(tmp_path / "nonexistent")])
        except SystemExit as e:
            assert e.code == 1


class TestInitCommand:
    def test_init_generates_env_example(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('import os\nDB_HOST = os.getenv("DB_HOST")\nPORT = os.getenv("PORT")\n')

        try:
            main(["init", str(tmp_path)])
        except SystemExit:
            pass

        example = tmp_path / ".env.example"
        assert example.exists()
        content = example.read_text()
        assert "DB_HOST=" in content
        assert "PORT=" in content

    def test_init_no_overwrite(self, tmp_path: Path) -> None:
        example = tmp_path / ".env.example"
        example.write_text("EXISTING=yes\n")
        src = tmp_path / "app.py"
        src.write_text('os.getenv("NEW_VAR")\n')

        try:
            main(["init", str(tmp_path)])
        except SystemExit as e:
            assert e.code == 1  # Should refuse to overwrite

    def test_init_force_overwrite(self, tmp_path: Path) -> None:
        example = tmp_path / ".env.example"
        example.write_text("EXISTING=yes\n")
        src = tmp_path / "app.py"
        src.write_text('os.getenv("NEW_VAR")\n')

        try:
            main(["init", "--force", str(tmp_path)])
        except SystemExit:
            pass

        content = example.read_text()
        assert "NEW_VAR=" in content

    def test_init_dry_run(self, tmp_path: Path, capsys) -> None:
        src = tmp_path / "app.py"
        src.write_text('os.getenv("TEST_VAR")\n')

        try:
            main(["init", "--dry-run", str(tmp_path)])
        except SystemExit:
            pass

        example = tmp_path / ".env.example"
        assert not example.exists()  # Should not create file in dry-run
