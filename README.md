# 🏄 envsurf

**Scan `.env` files against `.env.example` — detect missing variables, extras, and leaked secrets.**

[![PyPI](https://img.shields.io/pypi/v/envsurf.svg)](https://pypi.org/project/envsurf/)
[![Python](https://img.shields.io/pypi/pyversions/envsurf.svg)](https://pypi.org/project/envsurf/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

### Example output

```
envsurf — .env file surface scanner

.env vs .env.example
  Missing in .env:
    • REDIS_URL  (example: 'redis://localhost:6379')
  Extra in .env (not in example):
    • DEBUG_MODE
  Potential secrets:
    🔴 L4: AWS_SECRET_ACCESS_KEY (aws_key)
    🟡 L7: API_TOKEN (secret_key_name)

Found 3 issue(s) across 1 pair(s)
```

## CI Integration

```yaml
# GitHub Actions
- name: Check .env drift and secrets
  run: |
    pip install envsurf
    envsurf --strict .
```

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

## License

[MIT](LICENSE)
