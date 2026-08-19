# Documentation Guidance

Code without documentation is a liability. **Proactively write and suggest documentation** at every level — from inline comments to project-level READMEs.

---

## Core Principles

1. **Document as you go.** Writing docs after the fact is harder and less accurate. Include documentation in the same response as the code.
2. **Write for the next developer.** Assume the reader is competent but unfamiliar with this specific codebase. Explain *why*, not just *what*.
3. **Keep docs close to the code.** Documentation that lives far from the code it describes goes stale. Inline comments, docstrings, and co-located READMEs are better than a separate wiki.
4. **Update docs when code changes.** If you modify behavior, update the corresponding documentation in the same change. Outdated docs are worse than no docs.
5. **Don't over-document the obvious.** `x = x + 1  # increment x` adds noise. Focus on *why* something is done, business rules, non-obvious behavior, and known limitations.

---

## Documentation Layers

### 1. Inline Comments

Use sparingly and purposefully:

- **Why, not what** — Explain business rules, workarounds, non-obvious decisions.
- **TODO/FIXME** — Mark known technical debt with context: `# TODO(dhatcher): Replace with batch API when available — single-item calls are O(n) here`
- **Warnings** — Flag non-obvious gotchas: `// WARNING: This endpoint returns 200 even on partial failure — check the error array`

### 2. Docstrings / JSDoc / XML Docs

Every public function, class, and module should have a docstring explaining:

- **What it does** (one-line summary)
- **Parameters** (name, type, description, default values)
- **Return value** (type and meaning)
- **Exceptions/errors** raised (and when)
- **Example usage** (for non-trivial functions)

Follow the language's convention:

| Language | Convention | Example |
|---|---|---|
| Python | Google-style, NumPy-style, or reStructuredText docstrings | `"""Summary.\n\nArgs:\n    x: Description."""` |
| JavaScript/TypeScript | JSDoc | `/** @param {string} name - The user's name */` |
| Java | Javadoc | `/** @param name the user's name */` |
| C# | XML doc comments | `/// <param name="name">The user's name</param>` |
| Go | Godoc (comment above declaration) | `// FetchUser retrieves a user by ID.` |
| Rust | `///` doc comments with Markdown | `/// Fetches a user by ID.` |

### 3. README

Every project (and significant sub-module) should have a README covering:

- **What** the project does (1–3 sentences)
- **Quick start** — How to install dependencies and run locally
- **Prerequisites** — Required tools, runtimes, accounts, environment variables
- **Project structure** — Brief description of key directories and files
- **How to test** — The command to run tests
- **How to deploy** — Or a link to deployment docs
- **Contributing** — Or a link to CONTRIBUTING.md

When creating a new project, suggest a README skeleton. When modifying a project, check if the README needs updating.

### 4. API Documentation

For projects that expose APIs (REST, GraphQL, gRPC, library APIs):

- **REST APIs** — Suggest OpenAPI/Swagger specs. Document endpoints, methods, request/response schemas, auth requirements, and error responses.
- **Libraries** — Ensure public API surface is fully documented with docstrings. Suggest auto-generated docs (Sphinx, TypeDoc, Javadoc, Godoc).
- **GraphQL** — Use schema descriptions and deprecation annotations.

### 5. Architecture and Design Decisions

For significant design choices, suggest an **Architecture Decision Record (ADR)**:

```markdown
# ADR-001: Use PostgreSQL for primary data store

## Status
Accepted

## Context
We need a relational database that supports geospatial queries...

## Decision
We will use PostgreSQL 16 with PostGIS...

## Consequences
- Requires PostgreSQL expertise on the team
- Enables native spatial queries without a separate service
```

Store ADRs in `docs/adr/` or `docs/decisions/`. They're especially valuable for choices that aren't obvious from the code.

### 6. Changelog

For projects with releases or deployments, suggest maintaining a CHANGELOG.md following [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [Unreleased]
### Added
- User authentication via OAuth 2.0

### Fixed
- Pagination returning duplicate results on page boundaries
```

---

## When to Suggest Documentation

- **New project** → Suggest a README skeleton with quick start, prerequisites, and structure overview.
- **New public function/class/module** → Include a docstring.
- **New API endpoint** → Suggest documenting the endpoint (inline or in an OpenAPI spec).
- **Non-obvious code** → Add a comment explaining the *why*.
- **Configuration added** → Document the new config in README and `.env.example`.
- **Breaking change** → Suggest a changelog/migration note.
- **Complex algorithm or business logic** → Add a paragraph-level comment or link to the relevant specification/requirement.

---

## Anti-Patterns to Avoid

- **Stale comments** — A comment that contradicts the code is actively harmful. When changing code, update or remove adjacent comments.
- **Parroting the code** — `getUser()  // gets the user` adds nothing. Describe behavior, edge cases, or rationale instead.
- **Wall-of-text READMEs** — Keep project READMEs scannable. Use headers, bullet lists, and tables. Move deep dives to separate docs.
- **Generated docs with no curation** — Auto-generated API docs are a starting point, not a finished product. Add examples and clarify non-obvious behavior.
- **Documentation in a separate system only** — If docs live exclusively in Confluence/Notion/Wiki and not in the repo, they'll drift. Keep essential docs in-repo.

---

## Checklist

When you produce or modify code, verify:

- [ ] Public functions/classes have docstrings or equivalent
- [ ] Non-obvious logic has explanatory comments (why, not what)
- [ ] README exists and reflects the current state of the project
- [ ] New configuration or environment variables are documented
- [ ] API endpoints are documented (inline or in a spec file)
- [ ] Breaking changes are noted in a changelog or migration doc
- [ ] No stale comments — updated comments match updated code

