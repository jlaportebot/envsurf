# 🏄 envsurf

**Scan `.env` files against `.env.example` — detect missing variables, extras, and leaked secrets.**

[![PyPI](https://img.shields.io/pypi/v/envsurf.svg)](https://pypi.org/project/envsurf/)
[![Python](https://img.shields.io/pypi/pyversions/envsurf.svg)](https://pypi.org/project/envsurf/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-62%20passing-brightgreen.svg)]()

## Why?

Every project uses `.env` files. But `.env` drifts from `.env.example`, secrets leak into version control, and new team members waste hours figuring out which variables they need. **envsurf** catches all of that in one pass.

## Install

```bash
pip install envsurf
```

## Usage

### Scan a project

```bash
# From your project root — finds all .env/.env.example pairs recursively
envsurf .

# Explicit paths
envsurf --env .env --example .env.example

# CI mode — exit code 1 if any issues found
envsurf --strict .

# Skip secret scanning
envsurf --no-secrets .

# JSON output for tooling integration
envsurf --json .

# Ignore specific keys
envsurf --ignore DEBUG_MODE,LOCAL_TEST .
```

### Fix missing variables

```bash
# Auto-generate .env from .env.example, adding missing keys with TODO comments
envsurf fix

# Dry run — show what would change without writing
envsurf fix --dry-run

# Custom paths
envsurf fix --env .env.local --example .env.example
```

### Initialize .env.example from source code

```bash
# Scan your source code for env var references and generate .env.example
envsurf init

# Custom output path
envsurf init -o .env.template

# Force overwrite existing file
envsurf init --force

# Dry run
envsurf init --dry-run
```

### What it checks

| Check | Description |
|-------|-------------|
| **Missing vars** | Keys in `.env.example` but not in `.env` — you forgot to set them |
| **Extra vars** | Keys in `.env` but not in `.env.example` — undocumented config |
| **Leaked secrets** | Values that look like real API keys, AWS keys, GitHub tokens, JWTs, URLs with embedded credentials |
| **Parse errors** | Malformed lines that can't be parsed |

### Secret detection

envsurf uses heuristics to detect **real** secrets while ignoring placeholders:

- ✅ Catches: AWS keys (`AKIA...`), GitHub tokens (`ghp_...`), JWTs, URLs with embedded credentials, high-entropy strings
- ❌ Skips: `changeme`, `<your-key>`, `[insert-here]`, `${VAR}`, `$VAR`, empty values, booleans

### Source code scanning

`envsurf init` scans your codebase for environment variable references across **11 languages**:

Python · JavaScript/TypeScript · Ruby · Go · Rust · Shell · Java · PHP · C# · Docker Compose · YAML

### Example output

```
envsurf — .env file surface scanner

.env vs .env.example
 Missing in .env:
 • REDIS_URL (example: 'redis://localhost:6379')
 Extra in .env (not in example):
 • DEBUG_MODE
 Potential secrets:
 🔴 L4: AWS_SECRET_ACCESS_KEY (aws_key)
 🟡 L7: API_TOKEN (secret_key_name)

Found 3 issue(s) across 1 pair(s)
```

### JSON output

```bash
envsurf --json .
```

Returns structured JSON with all findings — perfect for CI pipelines, editors, and tooling integration.

## CI Integration

```yaml
# GitHub Actions
- name: Check .env drift and secrets
  run: |
    pip install envsurf
    envsurf --strict .
```

## Commands

| Command | Description |
|---------|-------------|
| `envsurf` (or `envsurf scan`) | Scan .env files for drift, extras, and secrets |
| `envsurf fix` | Generate/update .env from .env.example |
| `envsurf diff` | Compare two .env files (staging vs production) |
| `envsurf init` | Generate .env.example from source code |

### Compare environments

```bash
# Compare staging vs production .env files
envsurf diff .env.staging .env.production

# JSON output
envsurf diff .env.staging .env.production --json
```

Shows variables that are:
- **Only in A** — defined in first file but not second
- **Only in B** — defined in second file but not first
- **Value differences** — same key, different values

## Configuration

envsurf works with zero configuration. Just:

1. Keep `.env.example` alongside your `.env` files
2. Run `envsurf .`

## Development

```bash
git clone https://github.com/jlaportebot/envsurf.git
cd envsurf
pip install -e ".[dev]"
pytest
```

## Changelog

### v0.3.0
- **`envsurf diff`** — compare two arbitrary .env files (staging vs production, etc.)
- **Dockerfile ENV scanning** — detects `ENV KEY=value` in Dockerfiles
- **Bug fix**: removed duplicate Go `os.Getenv` regex with wrong closing bracket
- 62 tests passing

### v0.2.0
- **`envsurf fix`** — auto-generate .env from .env.example with TODO placeholders
- **`envsurf init`** — scan source code to generate .env.example (11 languages)
- **JSON output** — `--json` flag for CI/tooling integration
- **`--ignore`** flag — suppress known extras/secrets by key name
- Backward-compatible: `envsurf .` still works as before

### v0.1.0
- Initial release: scan, secret detection, strict mode

## License

[MIT](LICENSE)
