# Testing Guidance

When working on any codebase, **proactively suggest and implement tests**. Testing is not an afterthought — it is a core part of delivering working software.

---

## Core Principles

1. **Test alongside implementation.** When creating a new function, class, or module, write or suggest corresponding tests in the same response — don't defer testing to a later step.
2. **Prefer the project's existing test framework.** If the project already uses pytest, Jest, xUnit, etc., follow that convention. If no framework exists yet, recommend one appropriate for the language and project type.
3. **Start with unit tests.** Cover individual functions and methods first. Add integration tests when the code involves external systems, APIs, or databases.
4. **Test behavior, not implementation.** Tests should verify what the code does, not how it does it. This makes tests resilient to refactoring.
5. **Cover edge cases.** Include tests for empty inputs, null/undefined values, boundary conditions, error paths, and invalid arguments — not just the happy path.

---

## When to Suggest Tests

- **New function or method** → Suggest unit tests covering expected output, edge cases, and error handling.
- **Bug fix** → Suggest a regression test that reproduces the bug before the fix and passes after.
- **Refactoring** → Confirm existing tests still pass; suggest new tests if coverage gaps are found.
- **New API endpoint** → Suggest request/response tests covering success, validation errors, auth failures, and not-found cases.
- **Data processing logic** → Suggest tests with known input/output pairs, including malformed data.
- **Configuration or environment-dependent code** → Suggest tests that mock or stub external config.

---

## What Good Tests Look Like

- **Descriptive names**: Test names should read as plain-English descriptions of the expected behavior (e.g., `test_returns_empty_list_when_no_results_found`, `should throw when input is null`).
- **Arrange–Act–Assert**: Structure every test into setup, execution, and verification phases.
- **Isolated**: Tests should not depend on each other or on external state (network, filesystem, database) unless explicitly testing integration.
- **Fast**: Unit tests should run in milliseconds. If a test requires slow dependencies, mock them.
- **Deterministic**: Tests must produce the same result every run. Avoid reliance on system time, random values, or external services without mocking.

---

## Test File Placement

Follow the project's existing convention. If none exists, recommend one of these common patterns:

| Pattern | Example | Common in |
|---|---|---|
| Mirror `src/` structure in `tests/` | `src/utils.py` → `tests/test_utils.py` | Python, Java, C# |
| Co-locate with source | `src/utils.ts` + `src/utils.test.ts` | JavaScript/TypeScript (Jest, Vitest) |
| Top-level `__tests__/` directory | `__tests__/utils.test.js` | React / Node.js |
| `spec/` directory | `spec/utils_spec.rb` | Ruby (RSpec) |

---

## Framework Quick Reference

When recommending a test framework for a new project, suggest:

| Language | Recommended Framework | Runner |
|---|---|---|
| Python | `pytest` | `pytest` CLI |
| JavaScript/TypeScript | `vitest` or `jest` | `npx vitest` / `npx jest` |
| Java | JUnit 5 | Maven Surefire / Gradle |
| C# / .NET | xUnit or NUnit | `dotnet test` |
| Go | built-in `testing` | `go test ./...` |
| Rust | built-in `#[cfg(test)]` | `cargo test` |
| Swift | XCTest | `swift test` |

---

## Mocking and Test Doubles

- **Mock external dependencies** (HTTP calls, databases, file I/O) so tests are fast and isolated.
- Use the language's standard mocking library (`unittest.mock` for Python, `jest.mock` for JS, Mockito for Java, Moq for C#).
- **Don't mock everything** — if a function is pure computation, test it directly without mocks.
- When mocking, verify that the mock is called with expected arguments, not just that no error occurred.

---

## Test Coverage Expectations

- **New code**: Aim for meaningful coverage of all public functions and critical paths. 100% line coverage is not the goal — meaningful behavioral coverage is.
- **Existing code without tests**: When modifying untested code, add tests for the code you're touching. Don't try to backfill the entire file in one pass.
- **Critical paths**: Authentication, payment processing, data validation, and security-sensitive code should always have thorough test coverage.

---

## CI Integration Reminder

When suggesting tests, also mention how to run them. If the project has a CI pipeline, remind the user to ensure tests run in CI. If there's no CI pipeline, see the `guidance-deployment` skill for recommendations.

---

## Checklist

When you produce or modify code, verify:

- [ ] Tests exist (or are suggested) for new/changed public functions
- [ ] Edge cases and error paths are covered
- [ ] Test names clearly describe expected behavior
- [ ] Mocks are used appropriately for external dependencies
- [ ] Tests can run independently and in any order
- [ ] The test command is documented or obvious from the project setup

