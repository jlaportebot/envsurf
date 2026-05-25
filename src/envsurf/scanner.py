"""Scan source code for environment variable references."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set

# Patterns for env var references in common languages
_ENV_PATTERNS: list[re.Pattern[str]] = [
    # Python: os.environ["KEY"], os.environ.get("KEY"), os.getenv("KEY")
    re.compile(r"""os\.environ(?:\[["'](\w+)["']\]|\.get\(["'](\w+)["'])"""),
    re.compile(r"""os\.getenv\(["'](\w+)["']"""),
    # Python-dotenv: load_dotenv references (not directly scannable, but env-var usage is)
    # JavaScript/TypeScript: process.env.KEY, process.env["KEY"]
    re.compile(r"""process\.env\.([A-Za-z_]\w*)"""),
    re.compile(r"""process\.env\[["']([A-Za-z_]\w*)["']\]"""),
    # Ruby: ENV["KEY"], ENV.fetch("KEY")
    re.compile(r"""ENV\[["'](\w+)["']\]"""),
    re.compile(r"""ENV\.fetch\(["'](\w+)["']"""),
    # Go: os.Getenv("KEY")
    re.compile(r"""os\.Getenv\(["'](\w+)["']\]"""),
    re.compile(r"""os\.Getenv\(["'](\w+)["']\)"""),
    # Rust: env!("KEY"), std::env::var("KEY")
    re.compile(r"""(?:env!|std::env::var)\(["'](\w+)["']\)"""),
    # Shell: $KEY, ${KEY}
    re.compile(r"""\$\{([A-Za-z_]\w*)\}"""),
    # Docker Compose / YAML: ${KEY:-default}, ${KEY:?error}
    re.compile(r"""\$\{([A-Za-z_]\w*)(?::-|:\?)"""),
    # Java: System.getenv("KEY")
    re.compile(r"""System\.getenv\(["'](\w+)["']\)"""),
    # PHP: getenv('KEY'), $_ENV['KEY']
    re.compile(r"""getenv\(["'](\w+)["']\)"""),
    re.compile(r"""\$_ENV\[['"](\w+)['"]\]"""),
    # C# / .NET: Environment.GetEnvironmentVariable("KEY")
    re.compile(r"""Environment\.GetEnvironmentVariable\(["'](\w+)["']\)"""),
]

# Directories and file extensions to skip
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "egg-info", ".next", ".nuxt", "target", "vendor", "Cargo",
}

_SCAN_EXTENSIONS: set[str] = {
    # Python
    ".py",
    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Ruby
    ".rb",
    # Go
    ".go",
    # Rust
    ".rs",
    # Shell
    ".sh", ".bash", ".zsh",
    # Config / infra
    ".yml", ".yaml", ".toml", ".ini", ".cfg",
    # Java
    ".java",
    # PHP
    ".php",
    # C#
    ".cs",
    # Web
    ".env", ".env.example", ".env.local",
}


def scan_source(start: Path, *, extra_extensions: set[str] | None = None) -> Set[str]:
    """Scan source files under a directory for environment variable references.

    Returns a set of variable names found.
    """
    extensions = _SCAN_EXTENSIONS | (extra_extensions or set())
    found: Set[str] = set()

    for path in sorted(start.rglob("*")):
        # Skip directories
        if path.is_dir():
            continue

        # Skip hidden and ignored directories
        if any(part in _SKIP_DIRS for part in path.parts):
            continue

        # Check extension
        if path.suffix not in extensions:
            # Also try scanning files without extensions (e.g., Dockerfile, Makefile)
            if path.name not in ("Dockerfile", "Makefile", "docker-compose.yml", "docker-compose.yaml"):
                continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError):
            continue

        for pattern in _ENV_PATTERNS:
            for match in pattern.finditer(text):
                # Each pattern may have multiple groups; take the first non-None
                for group in match.groups():
                    if group is not None:
                        found.add(group)
                        break

    return found
