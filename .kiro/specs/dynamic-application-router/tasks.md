# Implementation Plan: Dynamic Application Router

## Overview

This plan implements the `psmcp-router-dynamic-app` package — a new PS-MCP router that extracts map-opening tools from the ArcGIS router and reimplements them using the MCP Apps standard. The implementation follows a bottom-up approach: schemas and utilities first, then the service layer, then the viewer HTML, and finally cleanup of the old ArcGIS router code.

## Tasks

- [x] 1. Scaffold package structure and configuration
  - [x] 1.1 Create `packages/psmcp-router-dynamic-app/pyproject.toml` with hatch-vcs, entry point `dynamic_app = "psmcp_router_dynamic_app:dynamic_app_router"`, dependencies on `ps-mcp>=0.1.0,<1.0` and `openai>=2.6.1,<3`
    - Use `requires-python = ">=3.13,<3.14"`
    - Configure `[tool.hatch.version]` with `source = "vcs"` and `raw-options = { root = "../.." }`
    - Configure `[tool.hatch.build.hooks.vcs]` with `version-file = "src/psmcp_router_dynamic_app/_version.py"`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Create `packages/psmcp-router-dynamic-app/src/psmcp_router_dynamic_app/__init__.py` exporting `dynamic_app_router` and `__version__` with fallback to `"0.0.0+unknown"`
    - _Requirements: 1.5_

  - [x] 1.3 Create `packages/psmcp-router-dynamic-app/README.md` documenting the router's purpose, environment variables, and tools
    - _Requirements: 1.1_

- [x] 2. Implement schemas and validation (`schemas.py`)
  - [x] 2.1 Create `schemas.py` with `ToolResultData` TypedDict, `CspMetadata` TypedDict, and `build_tool_result_data()` function
    - Define `ToolResultData` with `type`, `webmap_id`, `portal_url`, `layer_urls`, `layer_where_clauses`, `token`, `token_servers`, `customization_script`, `additional_requirements` fields using `NotRequired`
    - Implement `build_tool_result_data()` that constructs and validates the data dict
    - Implement `validate_webmap_params()` and `validate_layers_params()` helpers
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 2.2 Write property test for schema validity invariants
    - **Property 5: Schema Validity Invariants**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.5**

  - [x] 2.3 Write property test for input parameter preservation
    - **Property 4: Tool Result Data Preserves Input Parameters**
    - **Validates: Requirements 5.4, 6.2, 11.7**

  - [x] 2.4 Write property test for invalid parameters producing errors
    - **Property 8: Invalid Parameters Produce Error Results**
    - **Validates: Requirements 5.7, 6.6, 12.1**

- [x] 3. Implement CSP builder (`csp.py`)
  - [x] 3.1 Create `csp.py` with `BASELINE_CSP` constant and `build_csp(portal_url, layer_urls)` function
    - Include all baseline ArcGIS CDN domains per design
    - Extract origin (scheme + host) from portal_url and layer_urls
    - Add unique origins to `connectDomains` and `resourceDomains`
    - Deduplicate entries
    - _Requirements: 2.3, 2.6, 9.1, 9.2, 9.3, 9.4_

  - [x] 3.2 Write property test for CSP baseline domains always present
    - **Property 2: CSP Baseline Domains Always Present**
    - **Validates: Requirements 2.3, 9.1, 9.2**

  - [x] 3.3 Write property test for CSP dynamic domain addition
    - **Property 3: CSP Dynamic Domain Addition**
    - **Validates: Requirements 2.6, 9.3, 9.4**

- [x] 4. Implement LLM customization script generation (`llm.py`)
  - [x] 4.1 Create `llm.py` with `generate_customization_script()` async function
    - Adapt from existing `arcgis_llm.py` but generate JS function body snippets (not full HTML)
    - Handle OpenAI / Azure OpenAI client creation based on `AZURE_OPENAI` env var
    - Implement `_clean_llm_response()` to strip markdown code block delimiters
    - Include system prompt with ArcGIS Maps SDK Web Components documentation
    - 60-second timeout, graceful degradation on failure (log WARNING, return None)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 4.2 Write property test for markdown code block stripping
    - **Property 7: Markdown Code Block Stripping**
    - **Validates: Requirements 7.7**

  - [x] 4.3 Write unit tests for LLM client creation and error handling
    - Mock AsyncOpenAI/AsyncAzureOpenAI, verify prompt construction
    - Test graceful degradation on network error, timeout, missing OPENAI_KEY
    - _Requirements: 7.4, 7.5_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement token server derivation and authentication helpers
  - [x] 6.1 Add `_derive_token_registration_server(url)` function to `schemas.py` and token-related helpers
    - Extract `scheme://host/first_path_segment` from URLs containing `/rest`
    - Return `None` for URLs without `/rest`
    - Implement `build_token_servers(portal_url, layer_urls)` that derives servers from all relevant URLs
    - _Requirements: 8.1, 8.2, 8.4_

  - [x] 6.2 Write property test for token server derivation
    - **Property 6: Token Server Derivation**
    - **Validates: Requirements 8.2**

- [x] 7. Implement the Map Viewer App HTML (`viewer.py`)
  - [x] 7.1 Create `viewer.py` with `get_viewer_html()` returning a self-contained HTML string
    - Include MCP Apps SDK import from CDN (`@modelcontextprotocol/ext-apps`)
    - Include ArcGIS Maps SDK for JavaScript (Web Components) from CDN
    - Implement `app.connect()`, `ontoolinput`, `ontoolresult` handlers
    - Implement type dispatch: `sample_map` (topo-vector basemap, US center), `webmap` (portal item), `layers_map` (layer URLs)
    - Implement `customization_script` execution after map init
    - Implement token registration with IdentityManager
    - Register app-side tools: `add_layer`, `remove_layer`, `change_basemap`, `update_symbology`, `get_current_view`
    - Implement `app.updateModelContext()` calls after each state change
    - Display error messages for malformed/unrecognized tool result data
    - Handle `layer_where_clauses` application by index position
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.4, 5.6, 6.4, 6.5, 8.3, 8.5, 12.4, 12.5, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 14.1, 14.2, 14.3, 14.4_

  - [x]* 7.2 Write property test for resource content idempotence
    - **Property 9: Resource Content Idempotence**
    - **Validates: Requirements 3.5**

  - [x] 7.3 Write unit tests for viewer HTML structure
    - Verify MCP Apps SDK import present
    - Verify ArcGIS Maps SDK import present
    - Verify `ontoolinput`/`ontoolresult` handlers present
    - Verify all 5 app-side tools registered (`add_layer`, `remove_layer`, `change_basemap`, `update_symbology`, `get_current_view`)
    - Verify `updateModelContext` calls present
    - Verify error handling for unrecognized type
    - _Requirements: 3.1, 3.2, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 14.1, 14.2_

- [x] 8. Implement the service layer (`service.py`)
  - [x] 8.1 Create `service.py` with `FastMCP` instance and resource registration
    - Create `dynamic_app_router = FastMCP(name="Dynamic App Router")`
    - Register resource at `ui://dynamic-app/map-viewer.html` with MIME type `text/html;profile=mcp-app`
    - Resource returns `get_viewer_html()` content
    - _Requirements: 2.4, 3.1, 3.5, 3.6_

  - [x] 8.2 Implement `open_sample_map` tool in `service.py`
    - Accept optional `additional_requirements` (max 2000 chars)
    - Return ToolResult with text content + JSON Tool_Result_Data + `_meta.ui.resourceUri` + CSP
    - Call LLM if `USE_ARCGIS_LLM=true` and `additional_requirements` provided
    - Include `additional_requirements` in data without script if LLM not enabled
    - _Requirements: 2.1, 2.2, 2.5, 4.1, 4.2, 4.3, 4.5_

  - [x] 8.3 Implement `open_webmap` tool in `service.py`
    - Accept required `webmap_id`, optional `portal_url`, optional `additional_requirements`
    - Validate `webmap_id` is non-empty (return `isError: true` if empty/whitespace)
    - Fall back to `ARCGIS_PORTAL_URL` env var for portal_url
    - Return `isError: true` if no portal URL available
    - Resolve token via `resolve_token(required=False)`, include in data if available
    - Build CSP with portal URL added to dynamic domains
    - _Requirements: 2.1, 2.2, 2.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 8.1, 8.2, 12.1_

  - [x] 8.4 Implement `open_layers_map` tool in `service.py`
    - Accept required `layer_urls` (1-50 URLs), optional `layer_where_clauses`, optional `additional_requirements`
    - Validate `layer_urls` non-empty and ≤50 items
    - Validate `layer_where_clauses` length matches `layer_urls` if provided
    - Resolve token, derive token servers from layer URLs
    - Build CSP with layer URL origins added
    - _Requirements: 2.1, 2.2, 2.6, 6.1, 6.2, 6.3, 6.6, 8.1, 8.2, 12.1_

  - [x] 8.5 Write property test for static resource URI invariant
    - **Property 1: Static Resource URI Invariant**
    - **Validates: Requirements 2.2, 2.4**

  - [x] 8.6 Write unit tests for tool happy paths and error paths
    - Test `open_sample_map` with and without `additional_requirements`
    - Test `open_webmap` with valid params, empty webmap_id, missing portal URL
    - Test `open_layers_map` with valid params, empty list, mismatched where clauses
    - Mock `resolve_token` and `generate_customization_script`
    - _Requirements: 4.1, 4.2, 5.1, 5.3, 5.7, 6.1, 6.6, 12.1, 12.2, 12.3_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Remove map tools from ArcGIS router
  - [x] 10.1 Remove `open_sample_map`, `open_webmap`, `open_layers_map` tools and related code from `arcgis_service.py`
    - Remove the `_pending_map_requests` dict
    - Remove `uuid` import and related imports (`arcgis_resources`, `arcgis_llm` references)
    - Remove the `ARCGIS_CSP` and `ARCGIS_MAP_META` constants
    - Retain `get_user_info`, `search_portal`, `list_user_groups`, `get_item_info`, `list_system_services`
    - _Requirements: 10.1, 10.5_

  - [x] 10.2 Delete `arcgis_llm.py` and `arcgis_resources.py` modules from the arcgis router package
    - _Requirements: 10.3_

  - [x] 10.3 Remove `openai` dependency from `psmcp-router-arcgis/pyproject.toml`
    - _Requirements: 10.4_

  - [x] 10.4 Remove map-related resources (`get_error_page`, `get_sample_map`, `get_map_with_webmap_id`, `get_map_with_layer_urls`) from `arcgis_service.py`
    - _Requirements: 10.2_

  - [x] 10.5 Update `arcgis_enterprise_prompt` to remove references to `open_sample_map`, `open_webmap`, `open_layers_map`
    - _Requirements: 10.6_

  - [x]* 10.6 Write unit tests verifying ArcGIS router cleanup
    - Verify `open_sample_map`, `open_webmap`, `open_layers_map` are not registered tools
    - Verify `arcgis_llm.py` and `arcgis_resources.py` do not exist
    - Verify `openai` not in dependencies
    - Verify retained tools still work (`get_user_info`, `search_portal`, etc.)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 11. Integration wiring and documentation
  - [x] 11.1 Wire the package into the uv workspace and verify discovery
    - Run `uv sync --all-packages --all-extras`
    - Verify `psmcp router list` shows `dynamic_app` as discovered
    - _Requirements: 1.1, 1.2_

  - [x] 11.2 Update `CHANGELOG.md` with the new router addition and ArcGIS router changes
    - Document new `psmcp-router-dynamic-app` package
    - Document removal of map tools from `psmcp-router-arcgis`
    - _Requirements: 1.1_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The viewer HTML (task 7.1) is the largest single task — it contains all client-side logic including app-side tools, MCP Apps SDK integration, and ArcGIS rendering
- All LLM calls are mocked in tests — no external network access required
- The `_derive_token_registration_server` logic is reused from the existing `arcgis_resources.py` before it is deleted

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.2", "3.3", "4.1", "6.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "6.2", "7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4"] },
    { "id": 6, "tasks": ["8.5", "8.6"] },
    { "id": 7, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5"] },
    { "id": 8, "tasks": ["10.6", "11.1", "11.2"] }
  ]
}
```
