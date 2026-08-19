# Design: Utility Network Connector

## 1. Overview

This design extends the existing `psmcp-router-utilitynetwork` router plugin with metadata discovery tools, additional trace types, trace configuration builders, result formatting, workflow orchestration tools, and LLM steering files. The goal is to enable an LLM to complete utility network workflows conversationally — tracing networks, querying assets, identifying affected customers, and analyzing load.

## 2. Context

### 2.1 Existing Architecture

PS-MCP is a FastMCP v3 server with a plugin-based architecture. Routers are separate installable Python packages discovered at startup via entry points. The utility network router (`psmcp-router-utilitynetwork`) already provides:

- **Named trace execution** (`network_named_trace`) — runs persisted trace configurations
- **Named trace discovery** (`network_list_named_traces`) — lists available configurations
- **Terminal resolution** (`network_device_terminals`) — resolves terminals, tier info, asset group/type using `queryDataElements`
- **Direct downstream trace** (`network_downstream_trace`) — traces downstream without a named config
- **Direct upstream trace** (`network_upstream_trace`) — traces upstream without a named config
- **Customer data resolution** (`query_customer_data`) — GlobalIDs → meter_ids → CIS customer records

The router uses the `arcgis` Python API (`GIS`, `FeatureLayerCollection`, `UtilityNetworkManager`) for all UN operations. Authentication is handled by `resolve_token()` from `psmcp.core.auth`.

### 2.2 Key Internal Helpers Already Available

| Helper | Purpose |
|--------|---------|
| `_connect_gis(token)` | Creates authenticated `GIS` connection |
| `_un_data_element(flc)` | Fetches and parses the utility network data element via `queryDataElements` |
| `_utility_network_url(url)` | Converts FeatureServer URL → UtilityNetworkServer URL |
| `_starting_point(gid, terminal_id?, percent_along?)` | Builds trace starting-point dict |
| `run_trace(gis, url, type, gid, dn?, tier?, tid?, pa?, fs_url?)` | Direct trace execution with topology validation and retry |
| `_feature_tier_info(flc, domain, attrs)` | Resolves tier from subnetwork membership |
| `_trace_response(type, url, gid, raw, named_trace_name?)` | Wraps raw trace output into standard response envelope |
| `get_device_terminals(gis, url, gid)` | Full terminal + tier + asset type resolution |
| `get_customer_data(gis, url, gids, meter_ids?)` | Customer record resolution (legacy — uses hard-coded layer/field names; being superseded by discovery-based approach) |

### 2.3 Other Router Capabilities (Cross-Router)

| Tool | Router | Used For |
|------|--------|----------|
| `query_feature_layer` | feature_service | Spatial/attribute queries, feature inspection |
| `get_service_or_layer_details` | feature_service | Layer metadata inspection |
| `get_sample_feature_layer_data` | feature_service | Sample data for field discovery |
| `find_address_candidates` | location_services | Address geocoding |
| `search_portal` | arcgis | Portal item search |

## 3. What's Being Added

### 3.1 Summary of Additions

| Category | New Components |
|----------|---------------|
| **Metadata Tools** | `network_get_metadata(section)` (single tool for all data element queries), `network_refresh_metadata` (cache invalidation) |
| **Association Tool** | `network_query_associations` |
| **Trace Tool** | `network_trace` (generic — accepts any trace type; existing downstream/upstream remain) |
| **Formatting** | `_summarize_trace_results`, `_format_customer_impact`, truncation logic |
| **Workflow Tools** | `network_downstream_customer_impact`, `network_isolation_analysis`, `network_spatial_impact` |
| **Steering Files** | `utility-network-workflows.md`, `utility-network-data-model.md`, `utility-network-trace-interpretation.md` |
| **Domain Resolution** | `resolve_subtype_domains` (internal helper), `network_resolve_coded_values` (ad-hoc tool) |

## 4. Detailed Design

### 4.1 Module Organization

New code is added to the existing `psmcp-router-utilitynetwork` package:

```
packages/psmcp-router-utilitynetwork/
├── pyproject.toml                          (unchanged)
├── README.md                               (updated with new tools/env vars)
└── src/psmcp_router_utilitynetwork/
    ├── __init__.py                          (unchanged — exports utilitynetwork_router)
    ├── utility_network_service.py           (existing tools — unchanged)
    ├── metadata.py                          (NEW — metadata discovery tools)
    ├── associations.py                      (NEW — association query tool)
    ├── formatting.py                        (NEW — result formatting helpers)
    ├── domain_resolver.py                   (NEW — subtype domain resolution)
    ├── workflows.py                         (NEW — orchestration workflow tools)
    └── traces.py                            (NEW — additional trace type tools)
```

All new modules register their tools on the same `utilitynetwork_router` FastMCP instance (imported from `utility_network_service.py`). This keeps all UN tools in a single router entry point.

### 4.2 Metadata Discovery Tools (`metadata.py`)

#### Data Source & Caching

All metadata queries share a single cached call to `_un_data_element(flc)`. The cache is module-level:

```python
_cached_data_element: dict[str, Any] | None = None
_cached_service_url: str | None = None

def _get_data_element(service_url: str, token: str | None = None) -> dict[str, Any]:
    """Return cached data element, fetching on first call or URL change."""
    global _cached_data_element, _cached_service_url
    if _cached_data_element is not None and _cached_service_url == service_url:
        return _cached_data_element
    gis = _connect_gis(token)
    flc = FeatureLayerCollection(service_url.rstrip("/"), gis=gis)
    _cached_data_element = _un_data_element(flc)
    _cached_service_url = service_url
    return _cached_data_element
```

#### Single Metadata Tool

Instead of individual tools per section, a single `network_get_metadata` tool dispatches to section-specific parser functions:

```python
_SECTION_PARSERS: dict[str, Callable] = {
    "domain_networks": _parse_domain_networks,
    "asset_types": _parse_asset_types,
    "network_attributes": _parse_network_attributes,
    "terminal_configurations": _parse_terminal_configurations,
    "categories": _parse_categories,
    "topology_rules": _parse_topology_rules,
    "propagators": _parse_propagators,
}

@utilitynetwork_router.tool(name="network_get_metadata")
async def network_get_metadata(
    section: str,
    domain_network: str | None = None,
    source_name: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Query the utility network data element for a specific section.

    Returns focused, LLM-friendly subsets of the network schema. Use this to
    discover the network's structure, asset types, attributes, and rules.

    section values:
    - domain_networks: domain networks with tiers, topology type, tier groups
    - asset_types: asset groups/types with codes, categories (filterable by domain_network, source_name)
    - network_attributes: network attributes with data type, domain, usage
    - terminal_configurations: terminal configs with names, paths, direction
    - categories: categories with member asset types
    - topology_rules: connectivity rules, edge-junction rules, containment rules
    - propagators: network attribute propagators

    Args:
        section: Which part of the data element to return.
        domain_network: Filter for asset_types section (case-insensitive).
        source_name: Filter for asset_types section (case-insensitive).
        network_service_url: FeatureServer URL. Falls back to UTILITY_NETWORK_URL.
        token: Optional authentication token.
    """
    if section not in _SECTION_PARSERS:
        return {
            "error": f"Invalid section '{section}'. Valid: {', '.join(sorted(_SECTION_PARSERS))}."
        }
    # ... resolve service_url, get cached data element, dispatch to parser
```

**Design rationale:** Individual tools per section were implemented initially but consolidated because:
- All tools follow identical structure (resolve URL → get cached data element → parse subset → return)
- A single tool with a `section` parameter is extensible without registering new MCP tools
- New sections (topology_rules, propagators, diagrams) can be added as parser functions + steering hints
- Reduces MCP tool surface area from 6 to 2 while covering MORE of the data element
- The LLM selects the correct section via steering guidance, same as it selects trace types

#### Extensibility

Adding a new data element section requires:
1. A `_parse_<section>(data_element, **filters)` function
2. An entry in `_SECTION_PARSERS`
3. A hint in the steering file

No new tool registration, no schema changes, no router restart needed beyond code reload.

### 4.3 Association Query Tool (`associations.py`)

```python
@utilitynetwork_router.tool(name="network_query_associations")
async def network_query_associations(
    global_id: str,
    association_types: list[str] | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Query utility network associations for a feature by GlobalID.

    Returns connectivity, containment, and/or structural attachment associations.
    Use association_types to filter (e.g., ["connectivity", "containment"]).
    """
```

Implementation uses the `arcgis` Python API — specifically `UtilityNetworkManager` if it exposes an associations method, otherwise falls back to a direct REST call via the GIS connection's `_con.post()` method to `{UN_URL}/associations/query`.

### 4.4 Generic Trace Tool (`traces.py`)

A single generic tool handles all trace types beyond the existing downstream/upstream. This avoids tool proliferation while maintaining full capability — trace-type-specific guidance lives in steering files (Section 4.8).

```python
@utilitynetwork_router.tool(name="network_trace")
async def network_trace(
    starting_global_id: str,
    trace_type: str,
    network_service_url: str | None = None,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    terminal_id: int | None = None,
    percent_along: float | None = None,
    subnetwork_name: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Execute any type of utility network trace.

    Accepts trace_type: isolation, connected, subnetwork, subnetworkController,
    loops, shortestPath. For downstream/upstream, use the dedicated tools
    (network_downstream_trace, network_upstream_trace).

    Terminal conventions by trace type:
    - isolation: start from upstream terminal (high side / source side)
    - connected: either terminal works
    - subnetwork: either terminal works; supply subnetwork_name to constrain
    - subnetworkController: finds controllers for a subnetwork
    - loops: either terminal works
    - shortestPath: requires two starting points (second via traceLocations)

    Args:
        starting_global_id: GlobalID of the feature to start from.
        trace_type: The trace algorithm to execute.
        subnetwork_name: Required for "subnetwork" trace type to constrain results.
    """
```

The tool enriches trace result elements with resolved `sourceName`, `assetGroupName`, `assetTypeName` from the cached data element before returning.

**Design rationale:** Individual trace tools (isolation, connected, subnetwork) were considered but rejected because:
- They are identical in signature — only the `trace_type` string differs
- The LLM can select the correct `trace_type` via steering guidance
- A single tool reduces the MCP tool surface area without losing capability
- The `subnetwork_name` parameter is optional and only used for subnetwork traces

### 4.5 Result Formatting (`formatting.py`)

Internal helpers (not exposed as tools) applied by workflow tools:

```python
def summarize_trace_results(
    raw_results: dict[str, Any],
    source_mapping: dict[str, str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Group trace elements by source/asset group, count, highlight controllers."""

def format_customer_impact(
    customers: list[dict[str, Any]],
    phases: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Format customer impact: count, total load, phase breakdown."""

def truncate_results(
    items: list[Any],
    limit: int = 100,
    label: str = "elements",
) -> dict[str, Any]:
    """Return first N items with a count note if truncated."""
```

### 4.5.5 Subtype Domain Resolution (`domain_resolver.py`)

Utility network layers use subtypes where each subtype (asset group) has different coded value domains assigned to the same field. The layer JSON metadata (from `get_service_or_layer_details`) includes the full subtype definitions in its `types` array.

#### Layer Metadata Structure

```json
{
  "subtypeField": "assetgroup",
  "types": [
    {
      "id": 10,
      "name": "Switch",
      "domains": {
        "status": {"type": "codedValue", "codedValues": [{"code": 1, "name": "Open"}, {"code": 2, "name": "Closed"}]},
        "lifecycle": {"type": "codedValue", "codedValues": []}
      }
    }
  ],
  "fields": []
}
```

#### Internal Helper

```python
def resolve_subtype_domains(
    features: list[dict[str, Any]],
    layer_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve coded values to labels using subtype-specific domains.

    For each feature:
    1. Read the subtype value from the subtypeField
    2. Look up the subtype's domain assignments from types[]
    3. For each field with a coded value domain for that subtype,
       replace the value with {"code": N, "label": "Human Name"}
    4. Fields without domains are left unchanged

    Args:
        features: List of feature attribute dicts.
        layer_metadata: Layer JSON containing subtypeField, types, and fields.

    Returns:
        Features with coded values resolved to {code, label} dicts.
    """
```

#### Layer Metadata Cache

Layer metadata is cached per layer URL (similar to the data element cache). The subtypes/domains don't change during a session.

```python
_cached_layer_metadata: dict[str, dict[str, Any]] = {}

def _get_layer_metadata(layer_url: str, token: str | None = None) -> dict[str, Any]:
    """Fetch and cache layer metadata (fields, subtypes, domains)."""
```

#### Standalone Tool

```python
@utilitynetwork_router.tool(name="network_resolve_coded_values")
async def network_resolve_coded_values(
    features: list[dict[str, Any]],
    layer_url: str,
    token: str | None = None,
) -> dict[str, Any]:
    """Resolve coded attribute values to human-readable labels using layer subtype domains.

    Use this when you have features from query_feature_layer on a UN layer and
    need to decode their coded values. UN workflow tools (network_downstream_customer_impact,
    etc.) resolve domains automatically — this tool is for ad-hoc resolution.

    Args:
        features: List of feature attribute dicts with raw coded values.
        layer_url: The feature layer URL (e.g., .../FeatureServer/0) to fetch
            subtype/domain definitions from.
        token: Optional authentication token.

    Returns:
        Dict with resolved features and metadata about which fields were resolved.
    """
```

#### Integration with Workflow Tools

Workflow tools call `resolve_subtype_domains` internally:
1. After `get_customer_data()` returns records → resolve against the CIS layer metadata
2. After filtering trace elements for isolation devices → resolve against the device layer metadata
3. The LLM never sees unresolved codes from UN-specific workflow tools

**Design rationale:** Resolution at the tool boundary ensures coded values are always human-readable in output, regardless of whether the LLM remembers to resolve them. The standalone tool covers the case where the LLM queries UN layers directly via `query_feature_layer`.

### 4.6 Workflow Orchestration Tools (`workflows.py`)

High-level tools that orchestrate multiple steps. Customer data resolution is CONDITIONAL — it only occurs when the LLM has already discovered and verified the customer data source and passes explicit configuration.

#### `network_downstream_customer_impact`

```python
@utilitynetwork_router.tool(name="network_downstream_customer_impact")
async def network_downstream_customer_impact(
    global_id: str,
    terminal_id: int | None = None,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    customer_layer_url: str | None = None,
    customer_join_field: str | None = None,
    service_point_layer_url: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Find all customers downstream of a network feature.

    Orchestrates: terminal resolution → downstream trace → enrich elements →
    filter service points → optionally resolve customers (when config provided).

    Customer data resolution follows a discovery-first philosophy: this tool does
    NOT hard-code any layer name or join field. The LLM must first discover the
    customer data source (probe layers, verify schema, confirm with user), then
    pass the explicit config here. Without config, the tool returns trace results
    with service point identifiers and guidance for the LLM to discover customer data.
    """
```

**Orchestration flow:**
1. Resolve terminal (if not provided) via `get_device_terminals()`
2. Run downstream trace via `run_trace(type="downstream")` with resolved parameters
3. Enrich trace elements with resolved names from cached data element (`_enrich_trace_elements`)
4. Filter results for service point elements (by category membership or asset group/type from data element)
5. **If `customer_layer_url` AND `customer_join_field` are provided:** query the customer layer using service point join values, apply `resolve_subtype_domains`, apply `format_customer_impact`, return full results
6. **If customer config NOT provided:** return trace summary with service point GlobalIDs and a guidance note explaining the LLM should probe available layers/tables for customer data, verify the relationship, then re-call with explicit config

#### `network_isolation_analysis`

```python
@utilitynetwork_router.tool(name="network_isolation_analysis")
async def network_isolation_analysis(
    global_id: str,
    terminal_id: int | None = None,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Find isolation devices that must be operated to isolate a network element.

    Orchestrates: terminal resolution → isolation trace → enrich elements →
    filter isolation devices → format with device type, status, and location.
    """
```

**Orchestration flow:**
1. Resolve upstream terminal via `get_device_terminals()`
2. Run isolation trace via `run_trace(type="isolation")`
3. Enrich trace elements with resolved names from cached data element (`_enrich_trace_elements`)
4. Filter for isolation device elements (by category membership from data element)
5. Apply `resolve_subtype_domains` on device features against device layer metadata
6. Format with device type, status, location

#### `network_spatial_impact`

```python
@utilitynetwork_router.tool(name="network_spatial_impact")
async def network_spatial_impact(
    geometry: dict[str, Any],
    geometry_type: str,
    spatial_ref: int = 4326,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    customer_layer_url: str | None = None,
    customer_join_field: str | None = None,
    service_point_layer_url: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Find customers affected by a spatial impact area (flood, fire, etc.).

    Orchestrates: spatial query for network elements in area → minimize start
    points via subnetwork-controller pruning → single downstream trace with
    multiple traceLocations → enrich and filter service points → optionally
    resolve customers (when config provided).
    Distinguishes customers inside vs. downstream-but-outside the impact area.

    Customer data resolution follows the same discovery-first philosophy as
    network_downstream_customer_impact — explicit config required.
    """
```

**Orchestration flow:**
1. Spatial query for network elements in area (via feature layer query)
2. Call `_minimize_start_points` to reduce to minimum start points per subnetwork
3. Single downstream trace with all pruned start points as `traceLocations`
4. Enrich trace elements and filter service points
5. **If `customer_layer_url` AND `customer_join_field` provided:** resolve customers, distinguish inside vs. downstream-outside, apply `resolve_subtype_domains`, format and return
6. **If customer config NOT provided:** return trace summary with service point GlobalIDs (inside vs. outside) and a guidance note for the LLM to discover customer data

**Start-point minimization (`_minimize_start_points` internal helper):**

The spatial query may return many elements across multiple subnetworks. Rather than tracing from each one individually, the tool minimizes start points per subnetwork:

1. **Group by subnetwork** — tier is implicit in subnetwork membership
2. **Check for controller** — if a subnetwork's controller is in the selection, use it as the sole start point (downstream terminal); discard all other elements in that subnetwork
3. **Upstream protective device probe** — for subnetworks whose controller is NOT selected:
   - Run an upstream protective device trace from the selected elements
   - If the trace reaches the controller → go to step 2
   - If it returns a protective device below the controller → downstream trace from that device's downstream terminal; remove any spatially-selected elements covered by its results
   - Protective devices are identified via category membership from the data element (categories like "Protective" or similar), NOT via hard-coded asset group/type codes
4. **Single trace** — pass all remaining pruned start points to one `UtilityNetworkManager.trace()` call with multiple `traceLocations`

Each subnetwork is pruned independently when the spatial area spans multiple subnetworks.

#### Customer Data Discovery Philosophy

Customer data is NOT standardized across utility network deployments. The layer name, field names, join mechanism, and relationship to the network vary per organization. Common patterns include:
- CIS (Customer Information System) views joined to service points via meter ID
- Customer tables joined via account number or premise ID
- GIS layers with embedded customer attributes on service delivery points
- External systems accessed via related tables

The workflow tools do NOT hard-code any customer data assumptions. Instead:
1. If the LLM has already discovered and verified the customer data source (layer URL, join field), it passes these as explicit parameters
2. If not provided, the workflow tool returns the trace/analysis results with service point identifiers and a guidance note
3. The steering file teaches the LLM the probe → discover → verify → resolve pattern:
   a. Inspect the FeatureServer layers and tables for candidate customer data (look for fields like "customer", "account", "meter", "CIS", "subscriber", "consumer", "ratepayer", etc.)
   b. Sample the candidate layer to inspect field names and values
   c. Determine the join relationship (meter_id, account_number, service_point_globalid, etc.) by inspecting fields present in both the service point features and the candidate customer layer
   d. Present the discovered relationship to the user for confirmation
   e. Only then call the workflow tool with explicit customer config

This ensures the tools work across ANY deployment without assumptions about schema.

### 4.7 Steering Files

Located in `.kiro/steering/` with `inclusion: manual` front-matter:

#### `utility-network-workflows.md`

Teaches the LLM:
- What workflow tools are available and when to use each
- **Named traces first strategy:** discover → match → offer → execute (or fallback to direct trace)
- Terminal selection logic (downstream → low terminal, upstream → high terminal)
- Tier-terminal directional coupling for multi-tier devices
- That `network_device_terminals` resolves BOTH terminal and tier in one call
- How to get a starting GlobalID
- Trace configuration strategy: named traces for complex workflows (barriers, functions, propagators); `network_trace` for simple type-only traces; recommend GIS admin publish named traces when neither fits

#### `utility-network-data-model.md`

Teaches the LLM:
- NEVER assume asset group/type — always verify via `network_get_asset_types()`
- Disambiguation strategy: common name → metadata lookup → present options if ambiguous
- Common term hints (transformer, switch, fuse, pole, etc.) as guidance only
- Use asset type CODES in queries, not descriptions
- Call `network_get_domain_networks()` at session start to orient
- Three-level disambiguation: layer → asset group → asset type
- Address → service point resolution (discovery-based, no standard method)

#### `utility-network-trace-interpretation.md`

Teaches the LLM:
- How to read trace results (elements, sourceMapping, globalFunctionResults)
- Phase bitfield interpretation (A=4, B=2, C=1, ABC=7)
- Subnetwork controller significance
- Tier context in results
- How to explain results to users in plain language
- Identifying unexpected results (empty traces, excessive elements)

## 5. Architecture Diagram

```mermaid
graph TD
    A[LLM Client] -->|MCP<br/>streamable-http/stdio/sse| B[PS-MCP Server]
    B --> C[psmcp-router-utilitynetwork<br/>EXTENDED]
    B --> D[psmcp-router-feature-service]
    B --> E[psmcp-router-location-services]
    B --> F[psmcp-router-arcgis]

    subgraph "Utility Network Router (Extended)"
        C --> C1[Existing Tools<br/>network_named_trace<br/>network_list_named_traces<br/>network_device_terminals<br/>network_downstream_trace<br/>network_upstream_trace<br/>query_customer_data]
        C --> C2[NEW: Metadata<br/>network_get_metadata(section)<br/>network_refresh_metadata]
        C --> C3[NEW: Association Tool<br/>network_query_associations]
        C --> C4[NEW: Generic Trace<br/>network_trace]
        C --> C6[NEW: Workflow Tools<br/>network_downstream_customer_impact<br/>network_isolation_analysis<br/>network_spatial_impact]
        C --> C7[NEW: Formatting Layer<br/>summarize_trace_results<br/>format_customer_impact<br/>truncate_results]
        C --> C8[NEW: Domain Resolution<br/>resolve_subtype_domains (internal)<br/>network_resolve_coded_values (tool)]
    end

    C1 & C2 & C3 & C4 & C6 --> G[arcgis Python API<br/>GIS / FeatureLayerCollection<br/>UtilityNetworkManager]
    G --> H[ArcGIS Enterprise 11.x<br/>UtilityNetworkServer<br/>FeatureServer]

    subgraph "Steering Files (.kiro/steering/)"
        S1[utility-network-workflows.md]
        S2[utility-network-data-model.md]
        S3[utility-network-trace-interpretation.md]
    end

    S1 & S2 & S3 -.->|guides reasoning| A
```

## 6. Design Decisions

### 6.1 Single Router, Multiple Modules

New tools are added to the existing `utilitynetwork_router` FastMCP instance via separate modules (`metadata.py`, `traces.py`, `workflows.py`, etc.) that import and decorate on the shared router. This avoids creating a new package/entry point while keeping the code organized.

### 6.2 `arcgis` Python API Over Raw HTTP

The existing router uses the `arcgis` Python API for all UN operations. New code continues this pattern for consistency, even though it means synchronous calls wrapped in `asyncio.to_thread()`. Benefits:
- Consistent auth handling via `GIS` connection
- Built-in handling of ArcGIS response formats
- Access to `UtilityNetworkManager` methods
- Reuse of existing `_connect_gis()`, `_un_data_element()`, etc.

### 6.3 Module-Level Metadata Cache

The data element cache is module-level (not per-request) because:
- The UN schema doesn't change during a typical session
- `queryDataElements` is expensive (large response, network round-trip)
- `network_refresh_metadata()` provides explicit invalidation when needed
- Cache key is the service URL (supports multiple networks)

### 6.4 Named Traces First (Steering, Not Code)

Named trace prioritization is enforced via steering files, not via server-side logic in workflow tools. Reasons:
- Workflow tools should be composable primitives
- The LLM decides the strategy; tools execute the decision
- Different deployments may have different prioritization needs
- Keeps tool implementations simple and testable

### 6.5 Steering Files With Manual Inclusion

Steering files use `inclusion: manual` so they're only loaded when a user explicitly includes them (via `#` in chat). This avoids polluting every session with UN-specific context that's only relevant when working with utility network data.

### 6.6 No Trace Configuration Builders (Named Traces Preferred)

Trace configuration builders (`network_configured_trace`) were considered but removed because:
- Named traces authored by utility engineers encode correct barriers, functions, propagators, and output filters for each deployment
- Builder functions would encode assumptions about asset types and network attributes that vary per deployment (e.g., "which attribute represents load?", "which devices are normally-open?")
- The "named traces first" strategy (Section 4.7 steering) already directs the LLM to discover and use pre-authored configurations
- Adding a new workflow requires only publishing a named trace on the server — no MCP code changes
- If no named trace exists and the user needs complex configuration, the correct response is to recommend the GIS admin publish one

### 6.7 Discovery-Based Customer Resolution (No Hard-Coded Layer Names)

Customer data resolution is NOT embedded in workflow tool logic with hard-coded layer names or join fields. Reasons:
- Layer names (e.g., "CIS_CUST_VIEW") are deployment-specific and cannot be assumed
- The join relationship (meter_id, account_number, premise_id) varies per utility
- The LLM must verify relationships before using them — incorrect joins produce wrong results
- The existing `query_customer_data` tool hard-codes assumptions that don't generalize
- Making customer config optional allows the workflow tools to be useful even without customer data (trace analysis alone is valuable)

The correct approach: the LLM probes available data sources, verifies relationships, then passes explicit configuration to workflow tools. The steering file encodes this discovery pattern.

## 7. Correctness Properties

*A property is a characteristic that should hold true across all valid executions. Properties bridge human-readable requirements and machine-verifiable tests.*

### Property 1: Metadata cache identity until invalidation

*For any* sequence of metadata tool calls against the same `service_url`, `_get_data_element` SHALL return the same cached object on every call after the first, until `network_refresh_metadata` is called — after which the next call SHALL re-fetch.

**Validates: FR-1.7, AC-4, AC-5**

### Property 2: Code resolution completeness

*For any* tool output produced when the data element provides a mapping, the output SHALL contain no raw numeric codes for `networkSourceId`, `associationType`, `assetGroupCode`, `assetTypeCode`, or `terminalId` — each SHALL have a corresponding resolved name field.

**Validates: FR-5.8**

### Property 3: Result truncation

*For any* result set larger than the configured limit, the formatted output SHALL contain at most `limit` items and SHALL include a count note stating the total ("showing N of M").

**Validates: FR-5.5**

### Property 4: Trace type passthrough

*For any* call to `network_trace`, the `trace_type` parameter passed to `run_trace()` SHALL exactly equal the caller-supplied `trace_type` string.

**Validates: FR-3.1, FR-3.4**

### Property 5: Start-point minimization never increases count and preserves coverage

*For any* set of spatially-selected elements, `_minimize_start_points` SHALL return a start-point set no larger than the input, and every subnetwork represented in the input SHALL be represented by at least one start point in the output.

**Validates: FR-6.3.4–FR-6.3.11, AC-7**

### Property 6: Metadata subsets are focused

*For any* valid `section` value passed to `network_get_metadata`, the returned structure SHALL be a focused subset of the data element for that section and SHALL NOT include the full raw data element.

**Validates: FR-1.6**

### Property 7: Subtype domain resolution completeness

*For any* feature returned by a UN workflow tool where the source layer has subtype-specific coded value domains, every field with a domain assignment for the feature's subtype SHALL be resolved to a `{code, label}` structure. Fields without domain assignments SHALL be unchanged.

**Validates: FR-9.1–FR-9.4, AC-12**

### Property 8: Workflow tools never hard-code layer names or join fields

*For any* call to a workflow tool (network_downstream_customer_impact, network_spatial_impact), customer data resolution SHALL only occur when `customer_layer_url` and `customer_join_field` are explicitly provided. The tool SHALL NOT hard-code or assume any layer name, table name, or field name for customer data resolution.

**Validates: FR-6.1.4, FR-6.3.12**

## 8. Error Handling

All tool errors are returned as LLM-friendly messages (not raw stack traces or HTTP codes), consistent with existing router tools.

| Scenario | Behavior |
|----------|----------|
| No `network_service_url` and no `UTILITY_NETWORK_URL` env var | Raise `ValueError` with a message telling the caller to provide one |
| No token resolvable and none required | Proceed unauthenticated (existing `_connect_gis` behavior) |
| Feature GlobalID not found in any source layer | Return an error dict naming the GlobalID; do not raise |
| Trace returns "No starting points found" (stale topology) | Validate topology and retry once (existing `run_trace` behavior) |
| Trace returns empty elements | Return a valid result with an empty list and a note that nothing was found |
| Invalid `trace_type` to `network_trace` | Return an error dict listing the accepted trace types |
| `queryDataElements` returns no UN data element | Raise `ValueError` (service is not a utility network) — existing `_un_data_element` behavior |
| Associations endpoint unavailable / returns error | Return an error dict with the endpoint and reason |
| Customer config not provided to workflow tool | Return trace/analysis results with service point identifiers and a guidance note for the LLM to discover customer data sources |
| Data element lacks a mapping for a code | Leave the raw code and add a note; do not fail the request |
| Layer metadata fetch fails for domain resolution | Log warning and return features with raw codes intact; do not fail the request |

### Error Response Format

Tool errors return a dict with an `"error"` key containing a human-readable message plus context (accepted values, the GlobalID, or the service URL) to help the LLM recover — matching the convention used by the other routers.

## 9. Testing Strategy

### Test Framework

- **Unit / integration**: `pytest` with `pytest-asyncio` (auto mode)
- **Property-based**: `hypothesis`
- **ArcGIS API mocking**: `unittest.mock` to patch `GIS`, `FeatureLayerCollection`, and `UtilityNetworkManager` (the router uses the `arcgis` Python API, not httpx, so `respx` does not apply)
- **Live service**: tests marked `@pytest.mark.integration` run against a real Utility Network service configured via `UTILITY_NETWORK_URL` and are excluded from the default run

### Property-Based Tests

| Property | Test Function | Key Generators |
|----------|--------------|----------------|
| 1: Cache identity | `test_metadata_cache_identity` | `st.text()` service URLs, call sequences |
| 2: Code resolution completeness | `test_output_resolves_all_codes` | synthetic data element + result payloads |
| 3: Result truncation | `test_results_truncated_with_count` | `st.lists()` of elements, `st.integers()` limits |
| 4: Trace type passthrough | `test_trace_type_passthrough` | trace tool + type pairs |
| 5: Start-point minimization | `test_minimize_start_points_invariants` | synthetic subnetwork/element sets |
| 6: Metadata subsets focused | `test_metadata_returns_subset` | synthetic data element |

Configuration: `@settings(max_examples=100)`. Each test tagged `# Feature: utility-network-connector, Property {N}: {title}`.

### Unit Tests (Example-Based)

| Area | Tests |
|------|-------|
| `metadata.py` | Each section parser returns correct subset; cache hit/miss; invalid section returns error; `network_refresh_metadata` invalidation |
| `associations.py` | Response parsing; code resolution; type filtering |
| `traces.py` | Correct `trace_type` passthrough; `subnetwork_name` forwarding; element name enrichment |
| `formatting.py` | Grouping, counting, truncation; no unresolved codes when mapping present |
| `domain_resolver.py` | Subtype domain resolution; cache hit/miss; fields without domains unchanged; standalone tool |
| `workflows.py` | Orchestration step order; service-point filtering; `_minimize_start_points` pruning logic |

### Integration Tests (Live Service)

Marked `@pytest.mark.integration`, run against a real UN service:
- Metadata tools return real domain networks / asset types
- Each trace type executes against a known start feature
- `network_downstream_customer_impact` resolves real customers
- `network_spatial_impact` prunes start points and returns customers for a known polygon

### Test File Layout

```
packages/psmcp-router-utilitynetwork/tests/
├── test_un_metadata.py
├── test_un_associations.py
├── test_un_traces.py
├── test_un_formatting.py
├── test_un_workflows.py
├── test_un_properties.py        ← all property-based tests
└── test_un_integration.py       ← @pytest.mark.integration (live service)
```

## 10. Success Criteria

1. All 7 target workflows (W1–W7) can be completed conversationally via MCP tools
2. All trace types are accessible via existing downstream/upstream tools plus the generic `network_trace` tool (isolation, connected, subnetwork, subnetworkController, loops, shortestPath)
3. Metadata tools return parsed subsets without re-fetching on repeat calls
4. Workflow tools orchestrate terminal resolution → trace → service point identification in a single call, with customer data resolution occurring only when explicit configuration is provided
5. Spatial impact analysis minimizes start points via subnetwork-controller pruning and issues a single downstream trace
6. Result formatting produces concise, LLM-friendly output (< 2000 tokens for typical traces)
7. Steering files guide the LLM to select correct tools and interpret results
8. All new tools discoverable via `psmcp router list` within the existing server
9. Unit tests pass with mocked `arcgis` API responses
