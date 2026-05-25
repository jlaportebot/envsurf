"""Tests for envsurf scanner."""

import textwrap
from pathlib import Path

from envsurf.scanner import scan_source


class TestScanSource:
    def test_python_os_environ(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text(textwrap.dedent("""\
            import os
            DB_HOST = os.environ.get("DB_HOST", "localhost")
            API_KEY = os.getenv("API_KEY")
        """))
        found = scan_source(tmp_path)
        assert "DB_HOST" in found
        assert "API_KEY" in found

    def test_python_os_environ_bracket(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text('val = os.environ["SECRET_KEY"]\n')
        found = scan_source(tmp_path)
        assert "SECRET_KEY" in found

    def test_javascript_process_env(self, tmp_path: Path) -> None:
        src = tmp_path / "index.js"
        src.write_text('const port = process.env.PORT;\n')
        found = scan_source(tmp_path)
        assert "PORT" in found

    def test_javascript_bracket_access(self, tmp_path: Path) -> None:
        src = tmp_path / "index.ts"
        src.write_text('const key = process.env["API_KEY"];\n')
        found = scan_source(tmp_path)
        assert "API_KEY" in found

    def test_ruby_env(self, tmp_path: Path) -> None:
        src = tmp_path / "app.rb"
        src.write_text('db = ENV["DATABASE_URL"]\n')
        found = scan_source(tmp_path)
        assert "DATABASE_URL" in found

    def test_go_os_getenv(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text('port := os.Getenv("PORT")\n')
        found = scan_source(tmp_path)
        assert "PORT" in found

    def test_shell_variable(self, tmp_path: Path) -> None:
        src = tmp_path / "setup.sh"
        src.write_text('echo "${HOME_DIR}"\n')
        found = scan_source(tmp_path)
        assert "HOME_DIR" in found

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text('process.env.SHOULD_NOT_FIND_THIS\n')
        src = tmp_path / "app.js"
        src.write_text('process.env.SHOULD_FIND_THIS\n')
        found = scan_source(tmp_path)
        assert "SHOULD_FIND_THIS" in found
        assert "SHOULD_NOT_FIND_THIS" not in found

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text('${GIT_SECRET}\n')
        found = scan_source(tmp_path)
        assert "GIT_SECRET" not in found

    def test_no_env_vars_found(self, tmp_path: Path) -> None:
        src = tmp_path / "README.md"
        src.write_text("No env vars here.\n")
        found = scan_source(tmp_path)
        assert len(found) == 0

    def test_docker_compose_variable(self, tmp_path: Path) -> None:
        dc = tmp_path / "docker-compose.yml"
        dc.write_text("image: app\nenvironment:\n  - DATABASE_URL=${DATABASE_URL:-postgres://localhost/db}\n")
        found = scan_source(tmp_path)
        assert "DATABASE_URL" in found

    def test_merges_with_env_file(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("FROM_ENV_FILE=yes\n")
        src = tmp_path / "app.py"
        src.write_text('os.getenv("FROM_SOURCE")\n')
        found = scan_source(tmp_path)
        # The scanner itself doesn't merge .env — that's done in the init command
        assert "FROM_SOURCE" in found
