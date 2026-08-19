# Tasks: Utility Network Connector

## Task 1: Metadata discovery tools

**Objective:** Expose the utility network data element as focused, LLM-friendly metadata via a single `network_get_metadata(section)` tool and a `network_refresh_metadata` cache invalidation tool.

**Requirements:** FR-1.1–FR-1.9, FR-5.8, AC-4, AC-5

**Location:** `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/metadata.py`

**Implementation guidance:**
- Import `utilitynetwork_router` from `utility_network_service` and register tools on it
- Implement a module-level cache (`_cached_data_element`) keyed by service URL
- Reuse existing `_connect_gis(token)` and `_un_data_element(flc)` helpers
- Wrap blocking calls in `asyncio.to_thread()`
- Create a `_SECTION_PARSERS` dispatch dict mapping section names to parser functions
- Each parser extracts a focused subset from the cached data element
- Invalid section values return an error dict listing valid options
- Follow existing tool pattern: optional `network_service_url` + `token` params, fall back to `UTILITY_NETWORK_URL`

**Subtasks:**
- [x] Create `metadata.py` with module-level data element cache and `_get_data_element(service_url, token)` helper
- [x] Implement `_parse_domain_networks(data_element)` — returns domain networks with tiers, topology type, tier groups
- [x] Implement `_parse_asset_types(data_element, domain_network?, source_name?)` — returns asset groups/types with codes, categories, terminal config IDs
- [x] Implement `_parse_network_attributes(data_element)` — returns network attributes with data type, domain, usage
- [x] Implement `_parse_terminal_configurations(data_element)` — returns terminal configs with names, paths, direction
- [x] Implement `_parse_categories(data_element)` — returns categories with member asset types
- [x] Implement `_parse_topology_rules(data_element)` — returns connectivity rules, edge-junction rules, containment rules
- [x] Implement `_parse_propagators(data_element)` — returns network attribute propagators
- [x] Refactor: consolidate individual tools into single `network_get_metadata(section, ...)` tool with `_SECTION_PARSERS` dispatch
- [x] Implement invalid section error handling (return error dict with valid section list)
- [x] Implement `network_refresh_metadata` — invalidates cache, confirms re-fetch
- [x] Import `metadata` module in `__init__.py` to ensure tools are registered at import time
- [x] Unit tests with mocked `_un_data_element` response; verify parsing, caching, and cache invalidation
- [x] Update unit tests: verify section dispatch, invalid section error, new topology_rules and propagators parsers

**Test:** `uv run pytest tests/ -k metadata` — verify each section parser returns correct subsets, cache works, and invalid sections return errors.

---

## Task 2: Association query tool

**Objective:** Add a tool to query utility network associations (connectivity, containment, structural attachment) for a feature.

**Requirements:** FR-2.1–FR-2.4, FR-5.8

**Location:** `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/associations.py`

**Implementation guidance:**
- Use `UtilityNetworkManager` or `GIS._con.post()` to call `{UN_URL}/associations/query`
- Accept `global_id` and optional `association_types` filter list
- Return structured results: from/to feature identity, association type, direction
- Follow existing tool pattern; register on `utilitynetwork_router`

**Subtasks:**
- [x] Create `associations.py` with `network_query_associations` tool
- [x] POST to associations endpoint with `globalIds` and optional `associationTypes` filter
- [x] Resolve all numeric codes to names using cached data element: `associationType` → name, `networkSourceId` → source name, `terminalId` → terminal name, `assetGroupCode`/`assetTypeCode` → group/type names
- [x] Import module in `__init__.py`
- [x] Unit tests with mocked associations response
- [x] Unit test: verify no raw numeric codes remain in output when data element provides a mapping (assert all IDs have corresponding resolved name fields)
- [x] Integration test: call `network_query_associations` against the configured `UTILITY_NETWORK_URL` service with a known GlobalID, verify response structure and that all associations have resolved names (mark `@pytest.mark.integration`)

**Test:** `uv run pytest tests/ -k associations` (unit), `uv run pytest tests/ -k associations -m integration` (integration)

---

## Task 3: Generic trace tool

**Objective:** Add a single generic trace tool that accepts any trace type string, covering isolation, connected, subnetwork, loops, shortestPath, and any future types. Individual trace type tools (isolation, connected, subnetwork) are NOT needed — the existing `network_downstream_trace` and `network_upstream_trace` remain, and this generic tool handles everything else.

**Requirements:** FR-3.1–FR-3.7, FR-5.8, AC-2

**Location:** `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/traces.py`

**Implementation guidance:**
- Follow the same pattern as existing `network_downstream_trace` / `network_upstream_trace` in `utility_network_service.py`
- The tool calls `run_trace()` with the caller-supplied `trace_type` string
- Same parameters as downstream/upstream: `starting_global_id`, `network_service_url?`, `domain_network_name?`, `tier_name?`, `terminal_id?`, `percent_along?`, `token?`
- Add optional `subnetwork_name` param (used when trace_type is "subnetwork")
- Docstring should list accepted trace_type values and note terminal conventions per type
- Register on `utilitynetwork_router`
- Trace-type-specific guidance (which type for which scenario, terminal conventions) goes in the steering file (Task 7), not in separate tools

**Subtasks:**
- [x] Create `traces.py` importing `utilitynetwork_router`, `run_trace`, `_connect_gis`, `_trace_response`
- [x] Implement `network_trace(starting_global_id, trace_type, network_service_url?, domain_network_name?, tier_name?, terminal_id?, percent_along?, subnetwork_name?, token?)` — generic tool accepting any trace_type string
- [x] Docstring: list accepted trace_type values (isolation, connected, subnetwork, subnetworkController, loops, shortestPath), terminal conventions per type, when to use subnetwork_name
- [x] Enrich trace result elements with resolved `sourceName`, `assetGroupName`, `assetTypeName` from cached data element before returning
- [x] Import module in `__init__.py`
- [x] Unit tests with mocked `run_trace` verifying correct trace_type is passed, subnetwork_name is used when provided, and output contains resolved names

**Test:** `uv run pytest tests/ -k "trace and not named"`

---

## Task 4: Result formatting layer

**Objective:** Add internal formatting helpers that produce concise, LLM-friendly summaries of trace and query results.

**Requirements:** FR-5.1–FR-5.8, AC-6

**Location:** `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/formatting.py`

**Implementation guidance:**
- Internal helper functions (not MCP tools themselves) — called by workflow tools and `network_configured_trace`
- `summarize_trace_results(raw, source_mapping?, limit?)` — groups elements by source/asset group, counts, highlights controllers
- `format_customer_impact(customers, phases?)` — customer count, total load, phase breakdown
- `truncate_results(items, limit, label)` — returns first N with "showing X of Y" note
- Summary output should be < 2000 tokens for typical traces

**Subtasks:**
- [x] Create `formatting.py` with:
  - [x] `summarize_trace_results(raw_results, source_mapping?, limit=50)` — group + count + highlight controllers/barriers
  - [x] `format_customer_impact(customers, phases?)` — customer count, total load, phase breakdown table
  - [x] `truncate_results(items, limit=100, label="elements")` — truncation with count note
  - [x] All grouping/display logic MUST use resolved names (e.g., "Medium Voltage Transformer (3)" not "assetGroup 4, assetType 12 (3)")
- [x] Unit tests with sample trace result payloads; verify grouping, counting, truncation logic
- [x] Unit test: verify formatted output contains no unresolved numeric codes when data element mappings are provided

**Test:** `uv run pytest tests/ -k formatting`

---

## Task 5: Subtype domain resolution

**Objective:** Add a shared helper and standalone tool that resolves coded attribute values to human-readable labels using the layer's subtype-specific domain assignments. Workflow tools (Task 6) will call this automatically.

**Requirements:** FR-9.1–FR-9.9, AC-12

**Location:** `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/domain_resolver.py`

**Implementation guidance:**
- Fetch layer metadata via `get_service_or_layer_details` pattern (GET {layer_url}?f=json) — cache per layer URL
- Parse the `subtypeField`, `types` array (subtype → domain mappings), and `fields`
- For each feature: read subtype value → look up that subtype's domains → resolve coded fields
- Output format: replace coded value with `{"code": N, "label": "Human Name"}` — preserves both for filtering and display
- Fields without a domain for the feature's subtype are left unchanged
- Register standalone tool on `utilitynetwork_router`
- The internal helper is imported by workflow tools (Task 6)

**Subtasks:**
- [x] Create `domain_resolver.py` with layer metadata cache (`_cached_layer_metadata` dict keyed by layer URL)
- [x] Implement `_get_layer_metadata(layer_url, token)` — fetches and caches layer JSON (using httpx or GIS connection)
- [x] Implement `resolve_subtype_domains(features, layer_metadata)` — the core resolution logic
- [x] Implement `network_resolve_coded_values(features, layer_url, token?)` tool — fetches metadata + calls resolver
- [x] Handle edge cases: missing subtypeField (no subtypes → use default field domains), null feature values, unknown subtype codes
- [x] Import module in `__init__.py`
- [x] Unit tests: resolution with subtype domains, fields without domains unchanged, cache behavior, standalone tool
- [x] Unit test: verify output contains {code, label} structure for resolved fields

**Test:** `uv run pytest tests/ -k domain_resolver`

---

## Task 6: Workflow orchestration tools

**Objective:** Build high-level tools that orchestrate terminal resolution, trace execution, element enrichment, and optionally customer data resolution in a single call. Customer data resolution only occurs when the LLM has already discovered and verified the data source and passes explicit configuration.

**Requirements:** FR-6.1.1–FR-6.1.7, FR-6.2.1–FR-6.2.2, FR-6.3.1–FR-6.3.13, AC-1, AC-7

**Location:** `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/workflows.py`

**Implementation guidance:**
- Import and reuse: `get_device_terminals`, `run_trace`, `_get_data_element`, formatting helpers, `resolve_subtype_domains`
- Each workflow tool does multi-step orchestration internally
- Use `asyncio.to_thread()` for blocking arcgis API calls
- Customer data resolution is CONDITIONAL — only when explicit `customer_layer_url` + `customer_join_field` are provided
- NEVER hard-code layer names, table names, or field names for customer data
- For `network_spatial_impact`: implement `_minimize_start_points` helper using category-based protective device identification from the data element
- Register all on `utilitynetwork_router`
- Implement `_enrich_trace_elements(elements, data_element)` shared helper for name resolution on raw trace output

**Subtasks:**
- [x] Create `workflows.py` importing existing helpers (`get_device_terminals`, `run_trace`, `_connect_gis`, `_get_data_element`, formatting helpers, `resolve_subtype_domains`, `_get_layer_metadata`)
- [x] Implement `_enrich_trace_elements(elements, data_element)` — resolves networkSourceId → sourceName, assetGroupCode → assetGroupName, assetTypeCode → assetTypeName using the cached data element (shared with traces.py or imported from there)
- [x] Implement `network_downstream_customer_impact(global_id, terminal_id?, domain_network_name?, tier_name?, customer_layer_url?, customer_join_field?, service_point_layer_url?, network_service_url?, token?)`:
  - Resolve terminal (if not provided) via `get_device_terminals`
  - Run downstream trace via `run_trace`
  - Enrich trace elements via `_enrich_trace_elements`
  - Filter results for service point elements (by category membership or asset group/type from data element)
  - If `customer_layer_url` AND `customer_join_field` provided: query customer layer, apply `resolve_subtype_domains`, apply `format_customer_impact`, return full results
  - If customer config NOT provided: return trace summary with service point GlobalIDs + guidance note for LLM to discover customer data source
- [x] Implement `network_isolation_analysis(global_id, terminal_id?, domain_network_name?, tier_name?, network_service_url?, token?)`:
  - Resolve upstream terminal via `get_device_terminals`
  - Run isolation trace via `run_trace`
  - Enrich trace elements via `_enrich_trace_elements`
  - Filter for isolation device elements (by category membership from data element)
  - Apply `resolve_subtype_domains` on device features against device layer metadata
  - Format with device type, status, location
- [x] Implement `_identify_protective_devices(elements, data_element)` internal helper:
  - Use categories from the data element to identify elements that are protective devices
  - Search for categories containing "Protective", "Protection", or similar terms
  - Return filtered list of elements matching protective device categories
  - Do NOT hard-code asset group/type codes
- [x] Implement `_minimize_start_points(gis, service_url, elements, data_element)` internal helper:
  - Group elements by subnetwork name
  - For subnetworks whose controller is in the selection: use controller downstream terminal as sole start point
  - For others: run upstream trace; use `_identify_protective_devices` to find protective devices in results; if trace reaches controller → use controller; else downstream trace from protective device to eliminate covered elements
  - Return pruned list of start points
- [x] Implement `network_spatial_impact(geometry, geometry_type, spatial_ref?, domain_network_name?, tier_name?, customer_layer_url?, customer_join_field?, service_point_layer_url?, network_service_url?, token?)`:
  - Spatial query for network elements in area (via feature layer query)
  - Call `_minimize_start_points` to reduce to minimum start points per subnetwork
  - Single downstream trace with all pruned start points as `traceLocations`
  - Enrich and filter service points
  - If customer config provided: resolve customers, distinguish inside vs. downstream-outside, format
  - If customer config NOT provided: return trace summary with service point GlobalIDs (inside vs. outside) + guidance note
- [x] Implement graceful fallback: when customer config is provided but the layer/field doesn't exist or query fails, return trace results with an error note (don't fail the entire workflow)
- [x] Import module in `__init__.py`
- [x] Unit tests with mocked arcgis calls verifying:
  - Orchestration step order
  - Service-point filtering logic
  - `_minimize_start_points` pruning with category-based protective device identification
  - Customer resolution occurs ONLY when explicit config is provided
  - Graceful fallback when customer layer is inaccessible
  - No hard-coded layer names or field names in any code path

**Test:** `uv run pytest tests/ -k workflows`

---

## Task 7: Steering files for LLM guidance

**Objective:** Create guidance documents served as MCP resources (accessible to any MCP client) and mirrored as Kiro steering files. These teach the LLM how to reason about utility network workflows, choose tools, disambiguate data model terms, and interpret results.

**Requirements:** FR-7.0–FR-7.4.7, FR-8.1–FR-8.5, AC-8

**Location:**
- MCP resources: `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/` (`.md` files + `@router.resource` registrations)
- Kiro steering: `.kiro/steering/` (mirrors of the same content with `inclusion: manual` front-matter)

**Implementation guidance:**
- Use `inclusion: manual` front-matter so they only load when explicitly included
- Reference available tools by their exact MCP tool names
- Keep guidance focused on reasoning and decision-making — not raw JSON construction
- Include the "named traces first" strategy in workflow guidance

**Subtasks:**
- [x] Create `.kiro/steering/utility-network-workflows.md`:
  - [x] Front-matter with `inclusion: manual`
  - [x] Decision tree: which tool for which question type
  - [x] Named traces first strategy: discover → match → offer → execute (or fallback)
  - [x] Terminal selection logic (downstream → low terminal, upstream → high terminal)
  - [x] Tier-terminal directional coupling for multi-tier devices
  - [x] Explain `network_device_terminals` resolves BOTH terminal and tier
  - [x] How to get starting GlobalID (from user, query, spatial selection)
  - [x] Trace configuration strategy: named traces for complex workflows (barriers, functions, propagators); `network_trace` for simple traces; recommend GIS admin publish named traces when gap exists
  - [x] Customer data resolution as a conditional workflow step — explain that workflow tools only resolve customers when explicit config is provided
  - [x] Discovery-first pattern: the LLM discovers customer data before calling workflow tools, not after
- [x] Create `.kiro/steering/utility-network-data-model.md`:
  - [x] Front-matter with `inclusion: manual`
  - [x] Core rule: NEVER assume asset group/type — always verify via `network_get_asset_types()`
  - [x] Disambiguation strategy: common name → metadata → present options
  - [x] Common term hints (transformer, switch, fuse, pole, conductor)
  - [x] Use CODES in filters, not descriptions
  - [x] Session initialization: call `network_get_domain_networks()` to orient
  - [x] Three levels: layer → asset group → asset type
  - [x] Address → service point resolution strategy (discovery-based, no standard method)
  - [x] Data quality warnings (billing ≠ service address, geocode uncertainty)
  - [x] Subtype domain resolution: UN workflow tools auto-resolve coded values; when using `query_feature_layer` directly on UN layers, call `network_resolve_coded_values` or inspect layer metadata via `get_service_or_layer_details` to interpret codes
  - [x] Customer data discovery pattern: probe service layers/tables for customer-like sources (CIS, customer, account, subscriber, consumer, ratepayer, billing, meter), sample candidates, verify join relationship to service points, present to user for confirmation
  - [x] Explain that customer layer names and join fields are NEVER standardized — each utility uses different naming and relationships
  - [x] Common relationship patterns: meter_id join, account_number join, service_point GlobalID join, premise_id join, spatial proximity
  - [x] Instruct LLM to pass discovered config to workflow tools via explicit parameters (customer_layer_url, customer_join_field)
- [x] Create `.kiro/steering/utility-network-trace-interpretation.md`:
  - [x] Front-matter with `inclusion: manual`
  - [x] How to read trace results (elements, sourceMapping, globalFunctionResults)
  - [x] Phase bitfield interpretation (A=4, B=2, C=1, ABC=7)
  - [x] Subnetwork controller significance
  - [x] Tier context in results
  - [x] Plain-language explanation patterns
  - [x] Identifying unexpected results (empty, too large, missing expected elements)
- [x] Register each `.md` file as an MCP resource via `@utilitynetwork_router.resource` in a `resources.py` module
- [x] Mirror the same content as Kiro steering files in `.kiro/steering/` with `inclusion: manual` front-matter

**Test:** Verify steering files load correctly when referenced via `#` in chat. Verify content guides correct tool selection for all 7 target workflows.

---

## Task 8: Integration wiring and documentation

**Objective:** Wire all new modules into the router, ensure tools are discoverable, update documentation.

**Requirements:** AC-9, NFR-1, NFR-9, NFR-10, NFR-11

**Implementation guidance:**
- Update `__init__.py` to import all new modules (metadata, associations, traces, domain_resolver, workflows)
- Verify all tools appear in `psmcp router list`
- Update router `README.md` with new tools and their usage
- Update `CHANGELOG.md` under `[Unreleased]`

**Subtasks:**
- [x] Update `packages/psmcp-router-utilitynetwork/src/psmcp_router_utilitynetwork/__init__.py` to import new modules
- [x] Run `psmcp router list` and verify all new tools appear under the utilitynetwork router
- [x] Update `packages/psmcp-router-utilitynetwork/README.md`:
  - Document all new tools with descriptions
  - Document env vars (existing, no new ones)
  - Add usage examples
- [x] Update `CHANGELOG.md` under `[Unreleased]` with new features
- [x] Run full test suite: `uv run pytest tests/ -v`
- [x] Run linter: `uv run ruff check .` and `uv run ruff format --check .`
- [x] End-to-end verification: start server, verify tools are callable

**Test:** `make test && make lint` — everything passes.
