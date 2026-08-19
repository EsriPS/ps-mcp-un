# Changelog

All notable changes to PS-MCP are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Tag-driven releases: each released version is created by pushing a git tag of
the form `vX.Y.Z`. `hatch-vcs` derives the package version from that tag.

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

## [0.2.0] - 2026-05-19

### Added
- New `psmcp-router-dynamic-app` package — MCP Apps-based map viewer with
  app-side tools (`add_layer`, `remove_layer`, `change_basemap`,
  `update_symbology`, `get_current_view`) for incremental map updates.
- Three map tools in `psmcp-router-dynamic-app`: `open_sample_map`,
  `open_webmap`, `open_layers_map` using the MCP Apps standard
  (`_meta.ui.resourceUri` + structured Tool_Result_Data).
- Static Map Viewer App resource at `ui://dynamic-app/map-viewer.html` —
  a self-contained HTML/JS application that renders ArcGIS maps from tool
  result data via the MCP Apps SDK.
- Token verification caching in `ArcGISTokenVerifier`. Verified tokens are
  cached in memory for a configurable TTL (default 2 minutes) to avoid
  redundant portal round-trips on consecutive tool calls. Applies to both
  `USE_ARCGIS_AUTH` and `USE_ARCGIS_OAUTH` modes.
- `ARCGIS_TOKEN_CACHE_TTL` environment variable to control cache lifetime
  (in seconds). Set to `0` to disable caching.
- OAuth authentication plugin support via `psmcp-auth-oauth`.
- ArcGIS URL configuration for auth and server integration, including
  `ARCGIS_SERVER_URL`.

### Changed
- `open_webmap` tool: `portal_url` is now optional and defaults to the
  configured `ARCGIS_PORTAL_URL`. This prevents LLM clients from guessing
  the wrong portal (e.g., defaulting to `https://www.arcgis.com`).
- `search_portal` tool: response now includes a `portal_url` field so clients
  know which portal the results came from.
- Token registration behavior has been updated to align with the new ArcGIS
  auth/OAuth flow and URL configuration.

### Removed
- `open_sample_map`, `open_webmap`, `open_layers_map` tools from
  `psmcp-router-arcgis` (moved to `psmcp-router-dynamic-app`).
- `arcgis_llm.py` and `arcgis_resources.py` modules from
  `psmcp-router-arcgis`.
- `openai` dependency from `psmcp-router-arcgis`.
- Map-related resources (`get_error_page`, `get_sample_map`,
  `get_map_with_webmap_id`, `get_map_with_layer_urls`) from
  `psmcp-router-arcgis`.

## [0.1.0] - 2026-04-29

### Added
- Initial baseline release after the `psmcp-core` → `psmcp.core` consolidation.
- Single-package architecture: server, CLI, and shared core utilities all ship
  in the `ps-mcp` wheel. Routers depend on `ps-mcp>=0.1.0,<1.0`.
- `uv` workspace configuration so all monorepo packages share one lockfile and
  resolve cross-package deps locally.
- `hatch-vcs` tag-driven versioning across the server and all router packages.
  All packages share the same version derived from the repo's git tags.
- `ruff` lint/format configuration and `.pre-commit-config.yaml`.
- `pytest` integration marker; default runs exclude integration tests.
- Governance docs: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`.
- `Makefile` with common developer entry points.

### Changed
- All imports of `psmcp_core.*` are now `psmcp.core.*`.
- Routers import `from psmcp.core.auth import resolve_token`.
- `psmcp build` no longer builds a separate `psmcp-core` wheel.

### Removed
- The standalone `packages/psmcp-core/` package and the `psmcp_core` import
  namespace. There is **no backward-compatibility shim**.

## Versioning policy

This project uses [SemVer](https://semver.org). For PS-MCP specifically:

- **MAJOR** — breaking changes to the public Python API (`psmcp.core.*`),
  the CLI (`psmcp ...`), router entry-point contract, or `routers.json` schema.
- **MINOR** — new MCP tools/resources/prompts, new CLI flags, new env vars,
  or other backwards-compatible features.
- **PATCH** — bug fixes, doc updates, and internal refactors that do not
  affect the public surface area.

Routers in this repository pin `ps-mcp>=X.Y.Z,<X+1` so a major version bump
loudly breaks downstream installs that haven't been updated.

