"""Tests for the diff command and diff_env_files."""

from pathlib import Path

from envsurf.compare import diff_env_files, EnvDiff


def test_diff_identical_files(tmp_path: Path) -> None:
    a = tmp_path / ".env.staging"
    b = tmp_path / ".env.production"
    a.write_text("DB_URL=postgres://staging\nAPI_KEY=abc\n")
    b.write_text("DB_URL=postgres://staging\nAPI_KEY=abc\n")

    diff = diff_env_files(a, b)
    assert diff.is_clean
    assert not diff.only_in_a
    assert not diff.only_in_b
    assert not diff.value_differences


def test_diff_only_in_a(tmp_path: Path) -> None:
    a = tmp_path / ".env.staging"
    b = tmp_path / ".env.production"
    a.write_text("DB_URL=postgres://staging\nREDIS_URL=redis://staging\n")
    b.write_text("DB_URL=postgres://production\n")

    diff = diff_env_files(a, b)
    assert "REDIS_URL" in diff.only_in_a
    assert "REDIS_URL" not in diff.only_in_b


def test_diff_only_in_b(tmp_path: Path) -> None:
    a = tmp_path / ".env.staging"
    b = tmp_path / ".env.production"
    a.write_text("DB_URL=postgres://staging\n")
    b.write_text("DB_URL=postgres://production\nCDN_URL=https://cdn\n")

    diff = diff_env_files(a, b)
    assert "CDN_URL" in diff.only_in_b


def test_diff_value_differences(tmp_path: Path) -> None:
    a = tmp_path / ".env.staging"
    b = tmp_path / ".env.production"
    a.write_text("DB_URL=postgres://staging\nDEBUG=true\n")
    b.write_text("DB_URL=postgres://production\nDEBUG=false\n")

    diff = diff_env_files(a, b)
    assert not diff.only_in_a
    assert not diff.only_in_b
    assert len(diff.value_differences) == 2
    keys = [v[0] for v in diff.value_differences]
    assert "DB_URL" in keys
    assert "DEBUG" in keys


def test_diff_mixed(tmp_path: Path) -> None:
    a = tmp_path / ".env.staging"
    b = tmp_path / ".env.production"
    a.write_text("DB_URL=postgres://staging\nREDIS_URL=redis://staging\nDEBUG=true\n")
    b.write_text("DB_URL=postgres://production\nCDN_URL=https://cdn\nDEBUG=false\n")

    diff = diff_env_files(a, b)
    assert "REDIS_URL" in diff.only_in_a
    assert "CDN_URL" in diff.only_in_b
    assert ("DEBUG", "true", "false") in diff.value_differences
