# Best Practices Guidance

Write code that is **readable, maintainable, secure, and robust**. Proactively apply and suggest best practices appropriate to the language, framework, and project context.

---

## Core Principles

1. **Readability over cleverness.** Code is read far more often than it's written. Prefer clarity.
2. **Consistency within the project.** Follow the project's existing style, patterns, and conventions. When none exist, suggest establishing them.
3. **Fail early, fail clearly.** Validate inputs at boundaries. Throw descriptive errors. Don't silently swallow failures.
4. **Least privilege and least surprise.** Functions should do what their name says. Access should be as restricted as practical.
5. **Small, focused units.** Functions, classes, and modules should do one thing well. If a function needs a paragraph to describe, it's probably doing too much.

---

## Code Quality

### Linting and Formatting

Every project should have automated linting and formatting. If a project doesn't have these set up, suggest them:

| Language | Linter | Formatter |
|---|---|---|
| Python | `ruff` (or `flake8` + `pylint`) | `ruff format` (or `black`) |
| JavaScript/TypeScript | `eslint` | `prettier` |
| Java | Checkstyle, SpotBugs | `google-java-format` or IDE formatter |
| C# | .NET Analyzers, StyleCop | `dotnet format` |
| Go | `go vet`, `staticcheck` | `gofmt` (built-in) |
| Rust | `clippy` | `rustfmt` |
| SQL | `sqlfluff` | `sqlfluff fix` |

Suggest adding lint/format checks to CI (see `guidance-deployment` skill) and pre-commit hooks where appropriate.

### Naming Conventions

- Follow the language's idiomatic naming convention (e.g., `snake_case` in Python, `camelCase` in JavaScript, `PascalCase` for C# classes).
- Use descriptive names. `process_data()` is vague; `normalize_address_records()` is clear.
- Booleans should read as yes/no questions: `is_active`, `has_permission`, `should_retry`.
- Avoid abbreviations unless they're universally understood in the domain (`id`, `url`, `http` are fine; `proc_dat_recs` is not).

### Code Organization

- **Group related code.** Keep related functions, classes, and constants together.
- **Separate concerns.** Business logic should not be entangled with I/O, UI, or framework plumbing.
- **Limit file size.** If a file exceeds ~300–400 lines, consider splitting it by responsibility.
- **Use a consistent project structure.** Recommend established patterns for the framework (e.g., feature-based folders for React, app/domain/infrastructure layers for backend services).

---

## Error Handling

- **Don't swallow exceptions silently.** A bare `except: pass` or empty `catch {}` hides bugs. At minimum, log the error.
- **Use specific exception types.** Catch `FileNotFoundError`, not `Exception`. Throw `IllegalArgumentException`, not `RuntimeException`.
- **Add context to errors.** Wrap low-level exceptions with business-context messages: `"Failed to load user profile for user_id=123"` is more useful than `"Connection refused"`.
- **Handle errors at the right level.** Low-level code should throw; high-level code (controllers, CLI entry points) should catch and present errors appropriately.
- **Use error types/result types when available.** Go's `(value, error)` pattern, Rust's `Result<T, E>`, TypeScript union types — use the language's idiomatic error-handling mechanism.

---

## Security Basics

Apply these on every project — they're not optional:

1. **Never hardcode secrets** (API keys, passwords, tokens) in source code. Use environment variables or secret managers.
2. **Validate and sanitize all external input** — user input, API payloads, file uploads, URL parameters.
3. **Use parameterized queries** for database access. Never concatenate user input into SQL strings.
4. **Keep dependencies updated.** Known vulnerabilities in outdated packages are the #1 attack vector.
5. **Use HTTPS everywhere.** No exceptions for "internal" services in production.
6. **Apply least-privilege** to database accounts, API keys, IAM roles, and file permissions.
7. **Don't log sensitive data** — no passwords, tokens, PII, or full credit card numbers in logs.
8. **Set security headers** for web applications (Content-Security-Policy, X-Content-Type-Options, Strict-Transport-Security).

When writing code that touches authentication, authorization, or data validation, be especially thorough and point out potential risks.

---

## Dependency Management

- **Pin versions with a lockfile** (`package-lock.json`, `poetry.lock`, `go.sum`, `Cargo.lock`). Commit lockfiles to version control.
- **Minimize dependencies.** Before adding a package, check if the standard library already provides the functionality.
- **Evaluate before adopting.** Check maintenance status, download counts, license, and open issues before recommending a dependency.
- **Keep dependencies updated.** Suggest enabling Dependabot, Renovate, or equivalent automated update tools.
- **Audit for vulnerabilities.** Use `npm audit`, `pip-audit`, `cargo audit`, or platform-native scanning.

---

## Logging

- **Use structured logging** where possible (JSON logs for services, leveled text for CLI tools).
- **Use appropriate log levels.** `ERROR` for failures, `WARN` for recoverable issues, `INFO` for operational events, `DEBUG` for diagnostics.
- **Include context** — request IDs, user IDs (not PII), operation names, durations.
- **Don't log sensitive data.** Mask or omit tokens, passwords, and PII.
- **Use the language's standard logging library** or the project's existing logger — don't `print()` or `console.log()` for production logging.

---

## Performance Awareness

Don't prematurely optimize, but do avoid obvious pitfalls:

- **Avoid N+1 queries** — Use joins, eager loading, or batch fetches.
- **Don't fetch what you don't need** — Use field selection, pagination, and filtering at the data source.
- **Be aware of algorithmic complexity** — Nested loops over large collections, repeated full-list scans, and unbounded recursion are red flags.
- **Cache appropriately** — Cache expensive, stable computations. Invalidate correctly.
- **Profile before optimizing** — Suggest profiling tools when performance is a concern rather than guessing at bottlenecks.

---

## Language-Specific Reminders

### Python
- Use type hints for function signatures. Use `from __future__ import annotations` for modern syntax.
- Prefer `pathlib.Path` over `os.path` for file operations.
- Use context managers (`with` statements) for resource management.
- Use virtual environments (`venv`, `conda`, `poetry`) — never install to system Python.

### JavaScript / TypeScript
- Prefer TypeScript over plain JavaScript for any project beyond a quick script.
- Use `const` by default; `let` only when reassignment is needed; never `var`.
- Use `async/await` over `.then()` chains for readability.
- Handle Promise rejections — unhandled rejections crash Node.js processes.

### Java
- Use records for data carriers (Java 16+). Use sealed interfaces for restricted hierarchies (Java 17+).
- Prefer `Optional` over `null` returns for methods that may not produce a value.
- Use try-with-resources for `AutoCloseable` objects.

### C# / .NET
- Use `async/await` throughout — don't block on async code with `.Result` or `.Wait()`.
- Use nullable reference types (`#nullable enable`) to catch null issues at compile time.
- Prefer `ILogger<T>` from `Microsoft.Extensions.Logging` for structured logging.

### Go
- Always check errors — `_, err := something(); if err != nil { ... }`.
- Use `context.Context` for cancellation and timeouts.
- Run `go vet` and `staticcheck` in CI.

---

## Checklist

When you produce or modify code, verify:

- [ ] Code follows the language's idiomatic conventions and the project's existing style
- [ ] Linter and formatter are configured (or suggested)
- [ ] Error handling is explicit — no silently swallowed errors
- [ ] No hardcoded secrets or credentials
- [ ] External input is validated at the boundary
- [ ] Database queries are parameterized (if applicable)
- [ ] Dependencies are pinned and minimal
- [ ] Logging uses appropriate levels and includes context
- [ ] Function and variable names are descriptive and consistent
- [ ] Complex logic is broken into small, testable units

