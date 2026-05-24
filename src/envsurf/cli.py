"""CLI entry point for envsurf."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compare import compare_env_files
from .parser import parse_env
from .secrets import detect_secrets
from . import __version__

# ANSI colors
_RED = "\033[91m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _find_env_files(start: Path) -> list[tuple[Path, Path]]:
    """Find pairs of (.env, .env.example) starting from a directory."""
    pairs: list[tuple[Path, Path]] = []
    for env_file in sorted(start.rglob(".env")):
        # Skip node_modules, .git, __pycache__, etc.
        parts = env_file.parts
        if any(p in (".git", "node_modules", "__pycache__", ".venv", "venv", ".tox") for p in parts):
            continue
        parent = env_file.parent
        example = parent / ".env.example"
        if example.exists():
            pairs.append((env_file, example))
    return pairs


def _print_results(pairs: list[tuple[Path, Path]], *, check_secrets: bool, strict: bool) -> int:
    """Print comparison results and return exit code."""
    total_issues = 0

    if not pairs:
        # If no pairs found, check for standalone .env files
        standalone = [
            f for f in sorted(Path(".").rglob(".env"))
            if not any(p in (".git", "node_modules", "__pycache__", ".venv", "venv", ".tox") for p in f.parts)
        ]
        if standalone and check_secrets:
            print(f"{_CYAN}{_BOLD}envsurf — scanning standalone .env files for secrets{_RESET}\n")
            for env_path in standalone:
                env_file = parse_env(env_path)
                findings = []
                for entry in env_file.entries:
                    findings.extend(detect_secrets(entry.key, entry.raw_value, entry.line_number))
                if findings:
                    total_issues += len(findings)
                    print(f"{_BOLD}{env_path}{_RESET}")
                    for f in findings:
                        icon = "🔴" if f.severity == "critical" else "🟡"
                        print(f"  {icon} L{f.line_number}: {f.key} ({f.rule})")
                    print()
            if total_issues == 0:
                print(f"{_GREEN}No secrets detected in standalone .env files ✓{_RESET}")
            return 1 if (strict and total_issues > 0) else 0
        else:
            print(f"{_YELLOW}No .env / .env.example pairs found.{_RESET}")
            print("Create a .env.example alongside your .env file for best results.")
            return 0

    print(f"{_CYAN}{_BOLD}envsurf — .env file surface scanner{_RESET}\n")

    for env_path, example_path in pairs:
        result = compare_env_files(env_path, example_path, check_secrets=check_secrets)
        rel_env = env_path.relative_to(Path(".")) if env_path.is_relative_to(Path(".")) else env_path
        rel_ex = example_path.relative_to(Path(".")) if example_path.is_relative_to(Path(".")) else example_path
        header = f"{rel_env} vs {rel_ex}"
        issues = 0

        if result.is_clean and not result.extra_in_env:
            print(f"{_GREEN}✓ {header} — clean{_RESET}")
            continue

        print(f"{_BOLD}{header}{_RESET}")

        if result.missing_in_env:
            issues += len(result.missing_in_env)
            print(f"  {_RED}Missing in .env:{_RESET}")
            for key in result.missing_in_env:
                example_entry = parse_env(example_path).get(key)
                example_val = example_entry.raw_value if example_entry else ""
                print(f"    • {key}  (example: {example_val!r})")

        if result.extra_in_env:
            issues += len(result.extra_in_env)
            print(f"  {_YELLOW}Extra in .env (not in example):{_RESET}")
            for key in result.extra_in_env:
                print(f"    • {key}")

        if result.secret_findings:
            issues += len(result.secret_findings)
            print(f"  {_RED}Potential secrets:{_RESET}")
            for f in result.secret_findings:
                icon = "🔴" if f.severity == "critical" else "🟡"
                print(f"    {icon} L{f.line_number}: {f.key} ({f.rule})")

        if result.parse_errors:
            issues += len(result.parse_errors)
            print(f"  {_YELLOW}Parse errors:{_RESET}")
            for path, line_no, raw in result.parse_errors:
                print(f"    • {path}:{line_no} — {raw!r}")

        print()
        total_issues += issues

    # Summary
    if total_issues == 0:
        print(f"{_GREEN}All clear — no issues found ✓{_RESET}")
    else:
        print(f"{_YELLOW}Found {total_issues} issue(s) across {len(pairs)} pair(s){_RESET}")

    return 1 if (strict and total_issues > 0) else 0


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="envsurf",
        description="Scan .env files against .env.example — detect missing vars, extras, and leaked secrets",
    )
    parser.add_argument("--version", action="version", version=f"envsurf {__version__}")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--no-secrets",
        action="store_true",
        help="Skip secret detection",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 if any issues found (useful for CI)",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help="Explicit path to .env file",
    )
    parser.add_argument(
        "--example",
        type=Path,
        default=None,
        help="Explicit path to .env.example file",
    )

    args = parser.parse_args(argv)

    # If explicit paths given, compare just those
    if args.env and args.example:
        result = compare_env_files(args.env, args.example, check_secrets=not args.no_secrets)
        # Build a synthetic pair for printing
        exit_code = _print_results(
            [(args.env, args.example)],
            check_secrets=not args.no_secrets,
            strict=args.strict,
        )
    else:
        start = Path(args.path)
        pairs = _find_env_files(start)
        exit_code = _print_results(pairs, check_secrets=not args.no_secrets, strict=args.strict)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
