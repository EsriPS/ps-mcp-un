# Requirements: Utility Network Connector

## 1. Purpose

Extend the existing `psmcp-router-utilitynetwork` router plugin with metadata discovery tools, additional trace types, result formatting, workflow orchestration tools, and LLM steering files — enabling an LLM to complete operational Utility Network workflows such as downstream customer impact analysis, isolation device identification, and spatial impact assessment.

## 2. System Context

| Component | Detail |
|-----------|--------|
| Project | PS-MCP monorepo (`ps-mcp`) |
| Router Package | `psmcp-router-utilitynetwork` (extends existing) |
| MCP Framework | FastMCP v3 (`fastmcp>=3.2.4`) |
| Python | 3.13+ (required by the project) |
| ArcGIS Enterprise | Version 11.x |
| Portal URL | Configured via `ARCGIS_PORTAL_URL` env var |
| UN Service URL | Configured via `UTILITY_NETWORK_URL` env var |
| Authentication | `resolve_token()` from `psmcp.core.auth` (explicit → FastMCP context → env var) |
| ArcGIS Python API | `arcgis>=2.4,<3` (existing dependency) |
| Transport | Server-level (streamable-http, stdio, sse — configured at CLI level) |

### 2.1 Existing Capabilities (Already Implemented)

The following tools already exist in `psmcp-router-utilitynetwork` and other routers:

| Tool | Router | What It Does |
|------|--------|-------------|
| `network_named_trace` | utilitynetwork | Runs a persisted trace configuration by name from a starting GlobalID + terminal |
| `network_list_named_traces` | utilitynetwork | Lists all named trace configurations (name, globalId, description, traceType, creator) |
| `network_device_terminals` | utilitynetwork | Resolves terminals, tier info, asset group/type for a feature by GlobalID (uses queryDataElements internally) |
| `network_downstream_trace` | utilitynetwork | Direct downstream trace via UN REST endpoint (no named config) |
| `network_upstream_trace` | utilitynetwork | Direct upstream trace via UN REST endpoint (no named config) |
| `query_customer_data` | utilitynetwork | Resolves ElectricDevice GlobalIDs → meter_ids → CIS_CUST_VIEW customer records |
| `query_feature_layer` | feature_service | Generic feature layer query (attribute, spatial, pagination) |
| `get_service_or_layer_details` | feature_service | Retrieves full JSON metadata from any ArcGIS REST endpoint |
| `get_sample_feature_layer_data` | feature_service | Returns sample features from a layer |
| `find_address_candidates` | location_services | Geocodes an address string to candidate locations |
| `search_portal` | arcgis | Searches ArcGIS Portal for items |
| `get_item_info` | arcgis | Gets metadata for a portal item |

### 2.2 Existing Internal Helpers (Available for Reuse)

These internal helpers already exist in the utility network router and should be leveraged:

| Helper | What It Does |
|--------|-------------|
| `_connect_gis(token)` | Creates `GIS` connection using `resolve_token()` |
| `_un_data_element(flc)` | Calls `queryDataElements` and returns the parsed utility network data element |
| `_utility_network_url(service_url)` | Converts FeatureServer URL to UtilityNetworkServer URL |
| `_starting_point(global_id, terminal_id?, percent_along?)` | Builds trace starting point location |
| `run_trace(gis, url, type, ...)` | Direct trace execution with topology validation and retry |
| `_feature_tier_info(flc, domain, attrs)` | Resolves a feature's tier from its subnetwork membership |
| `_validate_topology(un_manager, url, gis)` | Validates/rebuilds topology on stale results |
| `get_device_terminals(gis, url, global_id)` | Full terminal + tier resolution for a feature |

## 3. Functional Requirements

### FR-1: Utility Network Metadata Discovery

| ID | Requirement |
|----|-------------|
| FR-1.1 | The router MUST provide a single `network_get_metadata(section, domain_network?, source_name?)` tool that returns focused subsets of the utility network data element based on the requested section |
| FR-1.2 | The tool MUST support section values: `domain_networks`, `asset_types`, `network_attributes`, `terminal_configurations`, `categories`, `topology_rules`, `propagators` |
| FR-1.3 | The `asset_types` section MUST support optional `domain_network` and `source_name` filter parameters |
| FR-1.4 | The router MUST provide a separate `network_refresh_metadata()` tool to invalidate the cached data element and re-fetch |
| FR-1.5 | The metadata tool MUST reuse the existing `_un_data_element(flc)` helper and cache the result in memory for the session lifetime |
| FR-1.6 | The metadata tool MUST return focused, LLM-friendly subsets — not the full raw data element |
| FR-1.7 | Adding support for a new data element section MUST require only a new parser function and a steering update — no new MCP tool registration |
| FR-1.8 | The tool MUST return an error dict listing valid section values when an invalid section is provided |
| FR-1.9 | Both tools MUST accept an optional `network_service_url` parameter, falling back to `UTILITY_NETWORK_URL` env var |

### FR-2: Association Queries

| ID | Requirement |
|----|-------------|
| FR-2.1 | The router MUST provide a `network_query_associations(global_id, association_types?)` tool |
| FR-2.2 | The tool MUST call the utility network associations endpoint via the `arcgis` Python API |
| FR-2.3 | The tool MUST support filtering by association type: connectivity, containment, structural attachment |
| FR-2.4 | The tool MUST return structured results with from/to feature identity, association type, and direction |

### FR-3: Generic Trace Tool

| ID | Requirement |
|----|-------------|
| FR-3.1 | The router MUST provide a single generic `network_trace(starting_global_id, trace_type, ...)` tool that accepts any trace type string (isolation, connected, subnetwork, subnetworkController, loops, shortestPath) |
| FR-3.2 | The existing `network_downstream_trace` and `network_upstream_trace` tools MUST remain unchanged |
| FR-3.3 | The generic trace tool MUST NOT duplicate downstream/upstream — those remain as dedicated tools for discoverability |
| FR-3.4 | The generic tool MUST follow the same pattern as existing `network_downstream_trace` / `network_upstream_trace` (using `run_trace()` internally) |
| FR-3.5 | The tool MUST accept optional `domain_network_name`, `tier_name`, `terminal_id`, `percent_along`, and `subnetwork_name` parameters |
| FR-3.6 | The tool MUST support topology validation and retry on "No starting points found" errors (existing pattern) |
| FR-3.7 | The tool's docstring MUST list accepted trace_type values and note terminal conventions per type, so the LLM can select the correct type without needing separate tools |

### FR-4: Trace Configuration Guidance (Steering-Driven)

| ID | Requirement |
|----|-------------|
| FR-4.1 | The steering files MUST teach the LLM to prefer named traces for any workflow requiring barriers, functions, propagators, or output filters |
| FR-4.2 | The steering files MUST teach the LLM to fall back to `network_trace` with domain/tier scoping when no named trace exists and the use case only requires basic tracing |
| FR-4.3 | The steering files MUST teach the LLM to recommend the user contact their GIS admin to publish a named trace when complex configuration is needed but no suitable named trace exists |
| FR-4.4 | No `network_configured_trace` tool is required — named traces authored by utility engineers provide correct barriers, functions, and propagators for each deployment |

### FR-5: Result Formatting

| ID | Requirement |
|----|-------------|
| FR-5.1 | The router MUST provide a formatting layer for trace and query results |
| FR-5.2 | `summarize_trace_results` MUST group elements by sourceMapping/asset group, count, and highlight subnetwork controllers |
| FR-5.3 | Formatted output MUST support summary mode (counts + key attributes) and detail mode (all attributes) |
| FR-5.4 | `format_customer_impact` MUST show customer count, total load, and breakdown by phase |
| FR-5.5 | Results exceeding 100 features MUST be truncated with a count note (e.g., "showing 50 of 247 elements") |
| FR-5.6 | Formatting MUST preserve the information needed for the LLM to reason about next steps |
| FR-5.7 | The `network_configured_trace` tool MUST support an `output_mode` parameter: "summary" (default) or "detail" |
| FR-5.8 | All tool outputs MUST resolve numeric ArcGIS codes to human-readable names using the cached data element: `networkSourceId` → source name, `associationType` → type name, `assetGroupCode` → asset group name, `assetTypeCode` → asset type name, `terminalId` → terminal name. Raw numeric codes MUST NOT appear in output when a mapping exists. |

### FR-6: Workflow Tools

#### FR-6.1: Downstream Customer Impact

| ID | Requirement |
|----|-------------|
| FR-6.1.1 | The router MUST provide a `network_downstream_customer_impact(global_id, terminal_id?, domain_network_name?, tier_name?)` tool |
| FR-6.1.2 | The tool MUST: resolve terminal → run downstream trace → filter service points → resolve to customers via `query_customer_data` → format results |
| FR-6.1.3 | Results MUST include customer identifiers, addresses (if available), and load values |
| FR-6.1.4 | The tool MUST accept optional `customer_layer_url`, `customer_join_field`, and `service_point_layer_url` parameters for explicit customer data resolution configuration |
| FR-6.1.5 | When customer config is NOT provided, the tool MUST return trace results with service point GlobalIDs and a guidance note explaining that customer data source discovery is needed |
| FR-6.1.6 | The tool MUST NOT hard-code any layer name, table name, or field name for customer data resolution |
| FR-6.1.7 | When customer config IS provided, the tool MUST query the specified customer layer using the specified join field, apply domain resolution, and format the results |

#### FR-6.2: Isolation Analysis

| ID | Requirement |
|----|-------------|
| FR-6.2.1 | The router MUST provide a `network_isolation_analysis(global_id, terminal_id?, domain_network_name?, tier_name?)` tool |
| FR-6.2.2 | The tool MUST: resolve upstream terminal → run isolation trace → return isolation devices with type, status, and location |

#### FR-6.3: Spatial Impact Analysis

| ID | Requirement |
|----|-------------|
| FR-6.3.1 | The router MUST provide a `network_spatial_impact(geometry, geometry_type, spatial_ref?, domain_network_name?, tier_name?)` tool |
| FR-6.3.2 | The tool MUST: spatial query to find elements in impact area → minimize start points → single downstream trace → resolve customers → format |
| FR-6.3.3 | Results MUST distinguish between customers inside the impact area and those downstream but outside |
| FR-6.3.4 | The tool MUST implement start-point minimization via an internal `_minimize_start_points` helper using the subnetwork-controller pruning algorithm (FR-6.3.5–FR-6.3.10) |
| FR-6.3.5 | The helper MUST group spatially-selected elements by subnetwork name (tier is implicit in subnetwork) |
| FR-6.3.6 | For each subnetwork whose controller IS in the spatial selection: use the controller's downstream terminal as the sole start point for that subnetwork; discard all other elements in that subnetwork |
| FR-6.3.7 | For each subnetwork whose controller is NOT in the spatial selection: run an upstream protective device trace from the selected elements |
| FR-6.3.8 | If the upstream protective device trace reaches the subnetwork controller: treat as FR-6.3.6 (controller start point, discard others) |
| FR-6.3.9 | If the upstream protective device trace returns a protective device below the controller: run a downstream trace from that device's downstream terminal and remove any spatially-selected elements that appear in its results (they are already covered) |
| FR-6.3.10 | After pruning, the tool MUST pass all remaining start points to a single downstream trace call (multiple `traceLocations` in one request) rather than issuing separate traces per element |
| FR-6.3.11 | The tool MUST handle the case where the spatial area spans multiple subnetworks — each subnetwork is pruned independently |
| FR-6.3.12 | The `network_spatial_impact` tool MUST accept the same optional customer resolution parameters as `network_downstream_customer_impact` (FR-6.1.4) and follow the same conditional resolution logic |
| FR-6.3.13 | The `_minimize_start_points` helper MUST identify protective devices via category membership from the data element (e.g., categories containing "Protective" or similar), not via hard-coded asset group/type codes |

### FR-7: LLM Guidance (MCP Resources + Steering Files)

| ID | Requirement |
|----|-------------|
| FR-7.0 | All guidance content MUST be served as MCP resources via `@router.resource` on the utility network router (as `.md` files in the router's `src/` directory) so that any MCP client can access them — in addition to being available as Kiro steering files in `.kiro/steering/` |

#### FR-7.1: Workflow Guidance

| ID | Requirement |
|----|-------------|
| FR-7.1.1 | The project MUST include a steering file (`.kiro/steering/utility-network-workflows.md`) that teaches the LLM which workflow tool to use for each type of question |
| FR-7.1.2 | The workflow steering MUST include decision logic: how to choose between trace types, how to select the correct terminal (upstream vs downstream), and what inputs are required |
| FR-7.1.3 | The steering MUST encode the "named traces first" strategy: discover available traces → offer matches to user → fall back to direct trace only when needed |
| FR-7.1.4 | The steering MUST explain tier-terminal directional coupling for multi-tier devices |
| FR-7.1.5 | The steering MUST explain that `network_device_terminals` resolves BOTH terminal and tier in one call |

#### FR-7.2: Data Model Disambiguation

| ID | Requirement |
|----|-------------|
| FR-7.2.1 | The project MUST include a steering file (`.kiro/steering/utility-network-data-model.md`) that teaches the LLM how to resolve ambiguous user references to specific UN data model elements |
| FR-7.2.2 | The steering MUST instruct the LLM to NEVER assume it knows the exact asset group/type for a user-provided term — it must always verify against live metadata |
| FR-7.2.3 | The steering MUST define a disambiguation strategy: when a user references a network asset by common name, call `network_get_asset_types()` to resolve the exact asset group and type codes BEFORE constructing any query |
| FR-7.2.4 | The steering MUST instruct the LLM to present options to the user when multiple asset types match a common term |
| FR-7.2.5 | The steering MUST include a common term mapping as HINTS (not source of truth) |
| FR-7.2.6 | The steering MUST instruct the LLM to use asset type CODES (not descriptions) in all query filters |
| FR-7.2.7 | The steering MUST instruct the LLM to call `network_get_domain_networks()` at session start to orient itself |
| FR-7.2.8 | The steering MUST cover disambiguation for layers, asset groups, and asset types |
| FR-7.2.9 | The steering MUST instruct the LLM to ask clarifying questions when the user's intent cannot be resolved from metadata alone |
| FR-7.2.10 | The steering MUST include a customer data discovery pattern: probe service layers/tables for customer-like data sources (CIS, customer, account, subscriber, consumer, ratepayer, billing, meter), sample candidate layers to inspect schema, verify the join relationship to service points, and present the discovered method to the user for confirmation before use |
| FR-7.2.11 | The steering MUST explain that customer data layer names and join fields are NEVER standardized — each utility uses different naming, different schemas, and different relationship mechanisms |

#### FR-7.3: Trace Interpretation

| ID | Requirement |
|----|-------------|
| FR-7.3.1 | The project MUST include a steering file (`.kiro/steering/utility-network-trace-interpretation.md`) that teaches the LLM how to interpret trace results |
| FR-7.3.2 | The steering MUST explain: sourceMapping, phase bitfield values (A=4, B=2, C=1, ABC=7), subnetwork controllers, and how to identify unexpected results |
| FR-7.3.3 | The steering MUST guide reasoning and decision-making only — it MUST NOT instruct the LLM to construct raw trace JSON |

#### FR-7.4: Address to Service Point Resolution

| ID | Requirement |
|----|-------------|
| FR-7.4.1 | The project MUST include domain knowledge (in a steering file) that teaches the LLM how to resolve a physical address to a network service point element |
| FR-7.4.2 | The steering MUST explain that there is no standard method for storing the address-to-service-point relationship — each utility may store it differently |
| FR-7.4.3 | The steering MUST instruct the LLM to probe the data model first before choosing a resolution method |
| FR-7.4.4 | The steering MUST teach the LLM to distinguish between billing/mailing address and service/premise address in CIS data |
| FR-7.4.5 | The steering MUST instruct the LLM to present the chosen resolution method to the user for confirmation before executing |
| FR-7.4.6 | The steering MUST instruct the LLM to warn users when falling back to geocode + spatial proximity |
| FR-7.4.7 | No new tools are required — existing tools (`find_address_candidates`, `query_feature_layer`, `get_service_or_layer_details`, `get_sample_feature_layer_data`, `query_customer_data`, `search_portal`) cover all resolution patterns |

### FR-9: Subtype Domain Resolution

| ID | Requirement |
|----|-------------|
| FR-9.1 | The router MUST provide a shared internal helper `resolve_subtype_domains(features, layer_metadata)` that resolves coded attribute values to human-readable labels using the layer's subtype-specific domain assignments |
| FR-9.2 | The helper MUST determine each feature's subtype from the layer's `subtypeField`, then look up the correct domain for each field from the `types[].domains` mapping for that subtype |
| FR-9.3 | Resolved fields MUST preserve both the raw code and the label in the output: `{"code": N, "label": "Human Name"}` — so codes remain available for filtering while labels are available for display |
| FR-9.4 | Fields without a domain assignment for the feature's subtype MUST be left unchanged |
| FR-9.5 | The layer metadata (containing `subtypeField`, `types`, and `fields`) MUST be cached per layer URL to avoid repeated fetches |
| FR-9.6 | All workflow tools (FR-6) MUST auto-resolve subtype domains on features before returning results — the LLM never sees unresolved coded values from UN-specific tools |
| FR-9.7 | The router MUST provide a `network_resolve_coded_values(features, layer_url)` tool for ad-hoc resolution when the LLM has features from other sources (e.g., `query_feature_layer` on UN layers) |
| FR-9.8 | The steering files MUST explain that UN workflow tools auto-resolve domains, but `query_feature_layer` used directly on UN layers returns raw codes that need resolution via `network_resolve_coded_values` |
| FR-9.9 | When workflow tools resolve customer data (with explicit config), they MUST apply `resolve_subtype_domains` on returned customer records before formatting |

### FR-8: Named Trace Prioritization (Steering-Driven)

| ID | Requirement |
|----|-------------|
| FR-8.1 | When a trace is needed, the LLM MUST first discover available named trace configurations by calling `network_list_named_traces` (enforced via steering) |
| FR-8.2 | Named traces MUST be preferred over direct trace execution — they are authored by utility engineers with correct barriers, functions, propagators, and output filters |
| FR-8.3 | If a named trace matching the user's intent is found, the LLM MUST offer it to the user and execute via `network_named_trace` |
| FR-8.4 | Only if NO suitable named trace exists SHOULD the LLM fall back to the direct trace tools or `network_configured_trace` |
| FR-8.5 | The system MUST handle networks that have no named traces gracefully — falling back to direct trace without error |

## 4. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Implementation MUST follow the PS-MCP router development pattern (FastMCP instance, `@router.tool` decorators, `resolve_token()`, entry point in pyproject.toml) |
| NFR-2 | Python 3.13 required. Use modern syntax (type unions with `\|`, match statements where appropriate) |
| NFR-3 | The router MUST use the `arcgis` Python API (`GIS`, `FeatureLayerCollection`, `UtilityNetworkManager`) for all UN operations — not raw httpx calls |
| NFR-4 | Configuration MUST use `os.getenv()` at module level (project convention — no Pydantic settings models) |
| NFR-5 | The router MUST support configurable service URLs to work with multiple UN services (via `network_service_url` parameter on each tool, falling back to `UTILITY_NETWORK_URL`) |
| NFR-6 | The router MUST respect `ARCGIS_VERIFY_SSL` (default `"True"`) for self-signed ArcGIS Enterprise installs |
| NFR-7 | Errors MUST be reported as LLM-friendly messages (not raw stack traces or HTTP status codes) |
| NFR-8 | End-to-end latency for a typical trace + customer resolution workflow SHOULD be < 30 seconds |
| NFR-9 | Logging MUST use `logging.getLogger(__name__)` with lazy formatting (project convention) |
| NFR-10 | New public functions MUST have corresponding unit tests |
| NFR-11 | Tool docstrings MUST be clear and actionable — they are shown to LLM clients |
| NFR-12 | Steering files MUST use `inclusion: manual` front-matter so they are only loaded when the user explicitly includes them via `#` in chat |

## 5. Target Workflows

These workflows MUST be completable end-to-end via the MCP tools:

| # | User Prompt (Natural Language) | Expected Tool Chain |
|---|-------------------------------|---------------------|
| W1 | "What is the total connected downstream load?" | `network_list_named_traces` → match load trace → `network_named_trace` → read function results |
| W2 | "List all downstream customers relying on this element" | `network_downstream_customer_impact(global_id)` |
| W3 | "What isolation devices must be operated to render this element safe?" | `network_isolation_analysis(global_id)` |
| W4 | "Given this flood area, what are all affected customers?" | `network_spatial_impact(geometry)` |
| W5 | "Find all customers affected by a broken main" | `network_downstream_customer_impact(global_id)` |
| W6 | "Trace upstream from a meter to the source" | `network_upstream_trace(global_id)` |
| W7 | "What is the load at 123 Main Street?" | Steering-guided: probe data model for address fields → resolve address to service point GlobalID → `network_downstream_customer_impact` or `network_configured_trace` |
| W8 | "811 call-before-you-dig What assets may be impacted by digging activities" | Steering-guided: geocode location or address or provided  geometry  -> if address or point buffer location by default 250 ft if user defined distance -> `network_spatial_impact(geometry)`|

## 6. Constraints

| ID | Constraint |
|----|-----------|
| C-1 | Customer data resolution requires the LLM to have discovered and verified a customer data source (layer URL + join field) before workflow tools can resolve customers. The data source is deployment-specific and not guaranteed to exist on the utility network FeatureServer. |
| C-2 | The `queryDataElements` response can be large; caching is essential to avoid repeated heavy fetches |
| C-3 | Spatial impact start-point minimization uses upstream protective device traces; the number of intermediate traces is bounded by the number of distinct subnetworks in the selection |
| C-4 | Trace config builders must produce configuration dicts compatible with `UtilityNetworkManager.trace()` |
| C-5 | Steering files guide LLM reasoning but must not instruct the LLM to construct trace JSON directly |
| C-6 | New tools MUST follow existing naming convention (`network_*` prefix for utility network tools) |

## 7. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-1 | All 7 target workflows (W1–W7) complete successfully with formatted results |
| AC-2 | Direct traces execute for all supported types via the existing downstream/upstream tools and the generic `network_trace` tool: isolation, connected, subnetwork, subnetworkController, loops, shortestPath |
| AC-3 | Named traces execute correctly via `network_named_trace` for all complex trace workflows requiring barriers, functions, or propagators |
| AC-4 | Metadata tools return parsed subsets from `queryDataElements` without re-fetching on repeat calls |
| AC-5 | `network_refresh_metadata()` invalidates cache and subsequent metadata calls return fresh data |
| AC-6 | Trace results in summary mode are concise enough for LLM context (< 2000 tokens for typical traces) |
| AC-7 | Spatial impact analysis correctly minimizes start points via subnetwork-controller pruning and issues a single downstream trace |
| AC-8 | Steering files enable the LLM to select the correct workflow tool for all 7 target workflows without user guidance |
| AC-9 | All new tools are discoverable via `psmcp router list` and work within the existing PS-MCP server |
| AC-10 | Adding a new trace workflow requires only: publishing a named trace on the server + steering update (no MCP code changes) |
| AC-11 | Unit tests pass for all new public functions with mocked `arcgis` API responses |
| AC-12 | Coded attribute values from UN layers are resolved to human-readable labels in all workflow tool outputs — no unresolved domain codes in user-facing results |
