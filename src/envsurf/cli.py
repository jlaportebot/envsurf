"""CLI entry point for envsurf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare import compare_env_files
from .parser import parse_env
from .scanner import scan_source
from .secrets import detect_secrets
from . import __version__

# ANSI colors
_RED = "\033[91m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _find_env_files(start: Path) -> list[tuple[Path, Path]]:
    """Find pairs of (.env, .env.example) starting from a directory."""
    pairs: list[tuple[Path, Path]] = []
    for env_file in sorted(start.rglob(".env")):
        parts = env_file.parts
        if any(p in (".git", "node_modules", "__pycache__", ".venv", "venv", ".tox") for p in parts):
            continue
        parent = env_file.parent
        example = parent / ".env.example"
        if example.exists():
            pairs.append((env_file, example))
    return pairs


def _build_result_dict(pairs: list[tuple[Path, Path]], *, check_secrets: bool, ignore: set[str] | None = None) -> dict:
    """Build a JSON-serializable dict of scan results."""
    ignore = ignore or set()
    results = []
    total_issues = 0

    for env_path, example_path in pairs:
        result = compare_env_files(env_path, example_path, check_secrets=check_secrets)
        missing = [k for k in result.missing_in_env if k not in ignore]
        extra = [k for k in result.extra_in_env if k not in ignore]
        secrets = [s for s in result.secret_findings if s.key not in ignore]
        errors = result.parse_errors

        issues = len(missing) + len(extra) + len(secrets) + len(errors)
        total_issues += issues

        results.append({
            "env": str(env_path),
            "example": str(example_path),
            "missing": missing,
            "extra": extra,
            "secrets": [
                {"key": s.key, "line": s.line_number, "rule": s.rule, "severity": s.severity}
                for s in secrets
            ],
            "parse_errors": [
                {"file": str(p), "line": n, "raw": r}
                for p, n, r in errors
            ],
            "issues": issues,
        })

    return {"total_issues": total_issues, "pairs": results, "version": __version__}


def _print_results(pairs: list[tuple[Path, Path]], *, check_secrets: bool, strict: bool, ignore: set[str] | None = None) -> int:
    """Print comparison results and return exit code."""
    ignore = ignore or set()
    total_issues = 0

    if not pairs:
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
                    if entry.key not in ignore:
                        findings.extend(detect_secrets(entry.key, entry.raw_value, entry.line_number))
                if findings:
                    total_issues += len(findings)
                    print(f"{_BOLD}{env_path}{_RESET}")
                    for f in findings:
                        icon = "🔴" if f.severity == "critical" else "🟡"
                        print(f" {icon} L{f.line_number}: {f.key} ({f.rule})")
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

        missing = [k for k in result.missing_in_env if k not in ignore]
        extra = [k for k in result.extra_in_env if k not in ignore]
        secrets = [s for s in result.secret_findings if s.key not in ignore]

        if not missing and not extra and not secrets and not result.parse_errors:
            print(f"{_GREEN}✓ {header} — clean{_RESET}")
            continue

        print(f"{_BOLD}{header}{_RESET}")

        if missing:
            issues += len(missing)
            print(f" {_RED}Missing in .env:{_RESET}")
            for key in missing:
                example_entry = parse_env(example_path).get(key)
                example_val = example_entry.raw_value if example_entry else ""
                print(f" • {key} (example: {example_val!r})")

        if extra:
            issues += len(extra)
            print(f" {_YELLOW}Extra in .env (not in example):{_RESET}")
            for key in extra:
                print(f" • {key}")

        if secrets:
            issues += len(secrets)
            print(f" {_RED}Potential secrets:{_RESET}")
            for f in secrets:
                icon = "🔴" if f.severity == "critical" else "🟡"
                print(f" {icon} L{f.line_number}: {f.key} ({f.rule})")

        if result.parse_errors:
            issues += len(result.parse_errors)
            print(f" {_YELLOW}Parse errors:{_RESET}")
            for path, line_no, raw in result.parse_errors:
                print(f" • {path}:{line_no} — {raw!r}")

        print()
        total_issues += issues

    if total_issues == 0:
        print(f"{_GREEN}All clear — no issues found ✓{_RESET}")
    else:
        print(f"{_YELLOW}Found {total_issues} issue(s) across {len(pairs)} pair(s){_RESET}")

    return 1 if (strict and total_issues > 0) else 0


def _cmd_fix(args) -> None:
    """Generate or update .env from .env.example with placeholder values."""
    example_path = args.example if hasattr(args, "example") and args.example else Path(".env.example")
    env_path = args.env if hasattr(args, "env") and args.env else Path(".env")

    if not example_path.exists():
        print(f"{_RED}Error: {example_path} not found{_RESET}")
        sys.exit(1)

    example_file = parse_env(example_path)

    if env_path.exists():
        env_file = parse_env(env_path)
        existing = env_file.as_dict()
    else:
        existing = {}

    lines: list[str] = []
    added = 0

    for entry in example_file.entries:
        if entry.key in existing:
            val = existing[entry.key]
            if val:
                lines.append(f"{entry.key}={val}")
            else:
                lines.append(f"{entry.key}=")
        else:
            added += 1
            lines.append(f"{entry.key}=  # TODO: set this value")

    # Add extras from .env that aren't in example
    if env_path.exists():
        env_file = parse_env(env_path)
        extra_keys = env_file.keys - example_file.keys
        if extra_keys:
            lines.append("")
            lines.append("# Extra variables (not in .env.example)")
            for key in sorted(extra_keys):
                entry = env_file.get(key)
                val = entry.raw_value if entry else ""
                lines.append(f"{key}={val}")

    output = "\n".join(lines) + "\n"

    if args.dry_run:
        print(f"{_CYAN}{_BOLD}envsurf fix — dry run{_RESET}\n")
        print(output)
        if added:
            print(f"{_GREEN}Would add {added} missing variable(s){_RESET}")
        else:
            print(f"{_GREEN}No missing variables to add ✓{_RESET}")
    else:
        env_path.write_text(output, encoding="utf-8")
        if added:
            print(f"{_GREEN}✓ Added {added} missing variable(s) to {env_path}{_RESET}")
        else:
            print(f"{_GREEN}✓ {env_path} is up to date with {example_path}{_RESET}")


def _cmd_init(args) -> None:
    """Generate .env.example by scanning source code for env var references."""
    start = Path(args.path)
    output_path = Path(args.output) if args.output else start / ".env.example"

    if output_path.exists() and not args.force:
        print(f"{_YELLOW}Error: {output_path} already exists. Use --force to overwrite.{_RESET}")
        sys.exit(1)

    print(f"{_CYAN}{_BOLD}envsurf init — scanning source for env var references{_RESET}\n")

    found = scan_source(start)

    # If an existing .env file is found, merge its keys too
    env_path = start / ".env"
    if env_path.exists():
        env_file = parse_env(env_path)
        found |= env_file.keys
        print(f" {_DIM}Found {len(env_file.keys)} key(s) in {env_path}{_RESET}")

    if not found:
        print(f"{_YELLOW}No environment variable references found.{_RESET}")
        sys.exit(0)

    sorted_keys = sorted(found)
    lines = ["# Auto-generated by envsurf init\n"]
    for key in sorted_keys:
        lines.append(f"{key}=\n")

    content = "".join(lines)

    if args.dry_run:
        print(f"Would write {output_path} with {len(sorted_keys)} variable(s):\n")
        print(content)
    else:
        output_path.write_text(content, encoding="utf-8")
        print(f" {_GREEN}✓ Wrote {output_path} with {len(sorted_keys)} variable(s){_RESET}")

    print(f"\n {_DIM}Variables found:{_RESET}")
    for key in sorted_keys:
        print(f"   • {key}")


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="envsurf",
        description="Scan .env files against .env.example — detect missing vars, extras, and leaked secrets",
    )
    parser.add_argument("--version", action="version", version=f"envsurf {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── scan ──
    scan_parser = subparsers.add_parser("scan", help="Scan .env files for issues (default)")
    scan_parser.add_argument("path", nargs="?", default=".", help="Directory to scan (default: .)")
    scan_parser.add_argument("--no-secrets", action="store_true", help="Skip secret detection")
    scan_parser.add_argument("--strict", action="store_true", help="Exit code 1 if any issues found (CI)")
    scan_parser.add_argument("--env", type=Path, default=None, help="Explicit path to .env file")
    scan_parser.add_argument("--example", type=Path, default=None, help="Explicit path to .env.example file")
    scan_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    scan_parser.add_argument("--ignore", type=str, default="", help="Comma-separated list of keys to ignore")

    # ── fix ──
    fix_parser = subparsers.add_parser("fix", help="Generate/update .env from .env.example")
    fix_parser.add_argument("--env", type=Path, default=None, help="Path to .env file (default: .env)")
    fix_parser.add_argument("--example", type=Path, default=None, help="Path to .env.example (default: .env.example)")
    fix_parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")

    # ── init ──
    init_parser = subparsers.add_parser("init", help="Generate .env.example from source code scanning")
    init_parser.add_argument("path", nargs="?", default=".", help="Directory to scan (default: .)")
    init_parser.add_argument("-o", "--output", type=Path, default=None, help="Output path (default: .env.example)")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing .env.example")
    init_parser.add_argument("--dry-run", action="store_true", help="Show what would be generated without writing")

    return parser


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = _build_parser()

    # Pre-process argv: if no subcommand, insert "scan" and map top-level flags
    if argv is not None and len(argv) > 0:
        first = argv[0]
        if first not in ("scan", "fix", "init") and not first.startswith("-"):
            # Positional arg without subcommand → default to scan
            argv = ["scan"] + list(argv)
        elif first.startswith("-") and first != "--version":
            # Flags without subcommand → default to scan
            argv = ["scan"] + list(argv)

    args = parser.parse_args(argv)

    # Handle subcommands
    if args.command == "fix":
        _cmd_fix(args)
        return
    elif args.command == "init":
        _cmd_init(args)
        return
    elif args.command == "scan" or args.command is None:
        # Default to scan
        scan_path = getattr(args, "path", None) or "."
        check_secrets = not getattr(args, "no_secrets", False)
        strict = getattr(args, "strict", False)
        use_json = getattr(args, "json", False)
        ignore_str = getattr(args, "ignore", "")
        ignore = {k.strip() for k in ignore_str.split(",") if k.strip()} if ignore_str else set()

        env_arg = getattr(args, "env", None)
        example_arg = getattr(args, "example", None)

        if env_arg and example_arg:
            pairs = [(env_arg, example_arg)]
        else:
            start = Path(scan_path)
            pairs = _find_env_files(start)

        if use_json:
            data = _build_result_dict(pairs, check_secrets=check_secrets, ignore=ignore)
            print(json.dumps(data, indent=2))
            sys.exit(1 if (strict and data["total_issues"] > 0) else 0)
        else:
            exit_code = _print_results(pairs, check_secrets=check_secrets, strict=strict, ignore=ignore)
            sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
