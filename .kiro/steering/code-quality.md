# Code Quality Standards

## Python Style

- **Python 3.13** — use modern syntax (`type` statements, `match`, `|` unions in type hints).
- **Type hints** on all function signatures. Do not use `from __future__ import annotations` — Python 3.13 handles forward references natively via PEP 649.
- **Docstrings** on all public functions — Google-style format.
- **No bare `except:`** — always catch specific exceptions.
- **Context managers** (`with`) for resource management (files, HTTP clients).
- **`pathlib.Path`** over `os.path` for file operations in new code.

---

## Ruff Rules (enforced)

The project enforces these rule sets via `ruff` (v0.15.12):

| Code | Category |
|------|----------|
| E | pycodestyle errors |
| F | pyflakes |
| I | isort (import sorting) |
| B | flake8-bugbear |
| UP | pyupgrade |
| SIM | flake8-simplify |
| RUF | ruff-specific |

Ignored: `E501` (line length handled by formatter), `B008` (function calls in defaults — needed for FastMCP).

Per-file ignores: `tests/**` ignores `B011` (assert False).

---

## Error Handling

- Validate inputs at tool boundaries. Raise descriptive errors early.
- Add context when re-raising: `raise ValueError("Failed to query layer: ...") from e`.
- Log errors with context (request IDs, layer URLs, operation names).
- Never silently swallow exceptions — at minimum log them.

---

## Security

- Never hardcode secrets. Use `os.getenv()` or `resolve_token()`.
- Validate and sanitize external input in tool parameters.
- Use parameterized queries for any database access (MongoDB, PostgreSQL routers).
- Don't log tokens, passwords, or PII.
- Respect `ARCGIS_VERIFY_SSL` but default to `True`.

---

## Logging Rules

```python
import logging
logger = logging.getLogger(__name__)

# CORRECT — lazy formatting
logger.info("Processing %d features for layer %s", count, layer_url)
logger.error("Request failed: %s", exc, exc_info=True)

# WRONG — f-string in log call (evaluated even if level is disabled)
logger.info(f"Processing {count} features")
```

Log levels:
- `ERROR` — operation failed, needs attention
- `WARNING` — recoverable issue, degraded behavior
- `INFO` — operational events (startup, requests served, config loaded)
- `DEBUG` — diagnostic detail (request/response bodies, intermediate state)

---

## Testing Expectations

- New public functions **must** have corresponding unit tests.
- Bug fixes **must** include a regression test.
- Use shared `pytest` fixtures from `conftest.py` (see `build-and-test.md` for the full list).
- Mock external HTTP calls with `httpx`-compatible mocking (e.g., `respx` or `pytest-httpx`).
- Test names describe behavior: `test_returns_empty_when_no_results_found`.
- Tests must be deterministic and isolated — no dependency on external services (unless marked `@pytest.mark.integration`).
- Property-based testing via `hypothesis` is available in dev dependencies.

---

## Documentation

- Update `CHANGELOG.md` under `[Unreleased]` for user-facing changes.
- Update router `README.md` when adding/changing env vars or tools.
- Keep docstrings current when modifying function behavior.
- MCP tool docstrings are shown to LLM clients — make them clear and actionable.
