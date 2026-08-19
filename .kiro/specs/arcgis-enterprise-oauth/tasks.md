# Implementation Plan: ArcGIS Enterprise OAuth Proxy

## Overview

Implement the ArcGIS Enterprise OAuth proxy as a pluggable auth package (`psmcp-auth-oauth`) discovered via a new `psmcp.auth` entry point group. The core server gains a `_discover_auth_plugin()` function that loads auth plugins before falling back to the existing `USE_ARCGIS_AUTH` logic. The plugin configures FastMCP's `OAuthProxy` with ArcGIS Enterprise endpoints and the existing `ArcGISTokenVerifier`.

## Tasks

- [x] 1. Create the `psmcp-auth-oauth` package structure
  - [x] 1.1 Create `packages/psmcp-auth-oauth/pyproject.toml` with entry point, dependencies, and hatch-vcs config
    - Declare `psmcp.auth` entry point: `arcgis_oauth = "psmcp_auth_oauth:create_auth_provider"`
    - Depend on `ps-mcp>=0.1.0,<1.0`
    - Use `hatch-vcs` with `raw-options = { root = "../.." }`
    - _Requirements: 1.1, 1.2, 6.1_

  - [x] 1.2 Create `packages/psmcp-auth-oauth/src/psmcp_auth_oauth/__init__.py`
    - Export `create_auth_provider`, `ArcGISOAuthConfigError`, and `__version__`
    - _Requirements: 1.1_

  - [x] 1.3 Create `packages/psmcp-auth-oauth/src/psmcp_auth_oauth/provider.py` with the factory function
    - Implement `create_auth_provider()` that returns `None` when `USE_ARCGIS_OAUTH != "true"` (case-insensitive)
    - Raise `ArcGISOAuthConfigError` when activated but missing required env vars (`ARCGIS_PORTAL_URL`, `ARCGIS_OAUTH_CLIENT_ID`, `ARCGIS_OAUTH_CLIENT_SECRET`)
    - Configure `OAuthProxy` with derived endpoints, `forward_pkce=True`, `token_endpoint_auth_method="client_secret_post"`
    - Use `ArcGISTokenVerifier` as the token verifier
    - Read `MCP_SERVER_BASE_URL` with default `http://localhost:8888`, strip trailing slash
    - Read `ARCGIS_VERIFY_SSL` for TLS verification setting
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 4.4, 4.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.1, 8.2, 9.1_

  - [x] 1.4 Create `packages/psmcp-auth-oauth/README.md` documenting env vars and usage
    - Document all OAuth-related environment variables
    - Include installation and activation instructions
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 2. Integrate auth plugin discovery into the core server
  - [x] 2.1 Add `_discover_auth_plugin()` function to `src/psmcp/server.py`
    - Discover `psmcp.auth` entry points via `importlib.metadata.entry_points(group="psmcp.auth")`
    - Call each factory; first non-None provider wins
    - Re-raise exceptions from plugin activation (fail-fast on misconfiguration)
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 2.2 Modify `_init_server()` in `src/psmcp/server.py` to use plugin discovery
    - Call `_discover_auth_plugin()` before the existing `USE_ARCGIS_AUTH` check
    - If plugin activates and `USE_ARCGIS_AUTH=True` is also set, log WARNING and use plugin
    - Fall back to `ArcGISAuthProvider` if no plugin activates and `USE_ARCGIS_AUTH=True`
    - No auth provider if neither condition is met
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 3. Workspace and configuration integration
  - [x] 3.1 Update root `pyproject.toml` to add `psmcp-auth-oauth` to `[tool.uv.sources]`
    - Add `psmcp-auth-oauth = { workspace = true }` entry
    - _Requirements: 1.1_

  - [x] 3.2 Update `.env.sample` with new OAuth environment variables section
    - Add `USE_ARCGIS_OAUTH`, `ARCGIS_OAUTH_CLIENT_ID`, `ARCGIS_OAUTH_CLIENT_SECRET`, `MCP_SERVER_BASE_URL` with comments
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 4. Checkpoint - Verify package installs and discovery works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Write tests for the OAuth plugin package
  - [x] 5.1 Create `packages/psmcp-auth-oauth/tests/conftest.py` with shared fixtures
    - Fixture to set/clear OAuth-related env vars
    - _Requirements: 1.1_

  - [x] 5.2 Create `packages/psmcp-auth-oauth/tests/test_provider.py` with unit tests
    - `test_factory_returns_none_when_not_enabled` — unset, empty, "false", "0" all return None
    - `test_factory_returns_none_case_insensitive` — "False", "FALSE", "no" return None
    - `test_factory_raises_missing_portal_url` — raises ArcGISOAuthConfigError naming ARCGIS_PORTAL_URL
    - `test_factory_raises_missing_client_id` — raises naming ARCGIS_OAUTH_CLIENT_ID
    - `test_factory_raises_missing_client_secret` — raises naming ARCGIS_OAUTH_CLIENT_SECRET
    - `test_factory_raises_multiple_missing` — error message names all missing vars
    - `test_factory_returns_proxy_when_configured` — returns OAuthProxy with correct endpoints
    - `test_endpoint_derivation_strips_trailing_slash` — portal URL with trailing slashes handled
    - `test_base_url_default` — defaults to http://localhost:8888 when MCP_SERVER_BASE_URL unset
    - `test_verify_ssl_default_true` — TLS verification enabled by default
    - `test_verify_ssl_false` — TLS verification disabled when ARCGIS_VERIFY_SSL=false
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 4.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 5.3 Write property test for configuration validation (Property 1)
    - **Property 1: Configuration validation rejects incomplete environments**
    - Generate random subsets of {portal_url, client_id, client_secret} as present/empty/absent
    - Assert: raises ArcGISOAuthConfigError iff any var missing; error names all missing vars
    - Assert: returns non-None OAuthProxy when all three present and non-empty
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 6.2, 6.3, 6.6**

  - [ ]* 5.4 Write property test for endpoint derivation (Property 2)
    - **Property 2: Endpoint derivation normalizes URLs correctly**
    - Generate random URL strings with 0-3 trailing slashes
    - Assert: no double slashes in derived endpoints; correct path appended after stripping
    - **Validates: Requirements 1.6, 1.7, 6.4, 6.5**

  - [ ]* 5.5 Write property test for plugin activation semantics (Property 3)
    - **Property 3: Plugin activation follows opt-in semantics**
    - Generate random strings for USE_ARCGIS_OAUTH
    - Assert: returns None iff lowercase value != "true"
    - **Validates: Requirements 1.8, 5.2, 6.1**

- [x] 6. Write tests for core auth plugin discovery
  - [x] 6.1 Create `tests/test_auth_discovery.py` with discovery unit tests
    - `test_discover_auth_plugin_activates_first_provider` — monkeypatch entry points, verify first non-None wins
    - `test_discover_auth_plugin_returns_none_when_no_plugins` — empty entry points returns None
    - `test_discover_auth_plugin_raises_on_plugin_error` — plugin exception propagates
    - `test_plugin_precedence_over_use_arcgis_auth` — plugin wins, WARNING logged
    - `test_fallback_to_use_arcgis_auth` — no plugin → USE_ARCGIS_AUTH=True → ArcGISAuthProvider
    - `test_no_plugin_no_auth` — no plugin, no USE_ARCGIS_AUTH → auth_provider is None
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 6.2 Write property test for auth mode selection (Property 4)
    - **Property 4: Auth mode selection follows precedence rules**
    - Generate combinations of plugin activation state and USE_ARCGIS_AUTH values
    - Assert: plugin wins when active; fallback works when inactive; warning logged when both set
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 6.3 Write property test for token resolution precedence (Property 5)
    - **Property 5: Token resolution follows three-tier precedence**
    - Generate random Optional[str] for each tier (explicit, auth context, env var)
    - Assert: returns first non-None in precedence order
    - **Validates: Requirements 3.3, 5.4, 5.5**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `OAuthProxy` from FastMCP handles OAuth flow mechanics (DCR, PKCE, JWT issuance, token encryption) — our code only configures it
- No changes needed to `resolve_token()` or any router code
- The `hypothesis` library is used for property-based tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.4"] },
    { "id": 1, "tasks": ["1.2", "1.3", "3.1", "3.2"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["5.1", "6.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "5.5", "6.2", "6.3"] }
  ]
}
```
