# psmcp-router-utilitynetwork

PS-MCP router plugin: ArcGIS Utility Network trace and metadata tools.

This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a running
PS-MCP server via a `psmcp.routers` entry point and provides utility network trace
operations, network metadata discovery, association queries, prompt-driven workflow
orchestration, and customer data queries.

## Install

```bash
uv pip install psmcp-router-utilitynetwork
```

Or, in the workspace:

```bash
uv sync --all-packages
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `UTILITY_NETWORK_URL` | Yes | FeatureServer URL of the utility network service (e.g. `https://server/arcgis/rest/services/UN/FeatureServer`) |
| `ARCGIS_PORTAL_URL` | No | Portal URL for GIS connection. Falls back to anonymous/token-only auth if unset. |
| `ARCGIS_TOKEN` | No | ArcGIS token. Resolved via `resolve_token()` (explicit param → auth context → env var). |
| `ARCGIS_VERIFY_SSL` | No | Set to `"false"` for self-signed certificates. Default: `"True"`. |

All tools accept an optional `token` parameter that overrides the environment variable.
Most tools accept an optional `network_service_url` parameter that overrides `UTILITY_NETWORK_URL`.

## Tools

### Metadata Discovery

| Tool | Description |
|------|-------------|
| `network_get_metadata` | Query the utility network data element for a specific section. Sections: `domain_networks`, `asset_types`, `network_attributes`, `terminal_configurations`, `categories`, `topology_rules`, `propagators`. Optional `domain_network` and `source_name` filters for `asset_types`. |
| `network_refresh_metadata` | Invalidate the cached data element and re-fetch. Call after schema changes. |

### Trace Operations

| Tool | Description |
|------|-------------|
| `network_named_trace` | Run a saved/named trace configuration from a starting feature. Resolves config by name, uses persisted traceType. |
| `network_list_named_traces` | List all saved trace configurations with name, globalId, description, traceType, creator. |
| `network_downstream_trace` | Direct downstream trace. Derives the from-tier from the start feature and applies that tier's subnetwork trace definition automatically. |
| `network_upstream_trace` | Direct upstream trace. Derives the from-tier from the start feature and applies that tier's subnetwork trace definition automatically. |
| `network_trace` | Generic trace accepting any trace type: isolation, connected, subnetwork, subnetworkController, loops, shortestPath. Enriches results with resolved names. |
| `network_generic_trace` | Full `UtilityNetworkServer/trace` request: all trace types (incl. path and circuit), multiple starting points, barriers, custom `traceConfiguration`, selectable result types, `moment`/`out_sr`, result cap and summary. See [Generic trace](#generic-trace). |

### Feature Inspection

| Tool | Description |
|------|-------------|
| `network_device_terminals` | Resolve terminal IDs, names, direction, tier membership, asset group/type for a feature by GlobalID. |
| `network_query_associations` | Query connectivity, containment, and structural attachment associations for a feature. All codes resolved to names. |

### Workflow Prompts

Complex workflows are implemented as MCP prompts that guide the LLM through
step-by-step orchestration using the atomic tools above. Each prompt reads a
skill file with detailed decision logic, filtering rules, and error handling.

| Prompt | Description |
|--------|-------------|
| `utility_network_metadata_discovery` | Exploring network schema, tiers, assets, and categories |
| `utility_network_downstream_customer_impact` | Finding customers affected downstream of a device |
| `utility_network_spatial_impact` | Assessing customer impact within a geographic area |
| `utility_network_named_trace_execution` | Discovering and executing named trace configurations |
| `utility_network_customer_data_discovery` | Discovering customer data sources on the network |
| `utility_network_address_resolution` | Resolving an address to a network element GlobalID |
| `utility_network_generic_trace` | Choosing arguments for and running any trace with `network_generic_trace` |
| `utility_network_trace_interpretation` | Reading trace results, phases, and troubleshooting |

### Domain Resolution

| Tool | Description |
|------|-------------|
| `network_resolve_coded_values` | Resolve coded attribute values to human-readable labels using layer subtype domains. |

### Customer Data (Legacy)

| Tool | Description |
|------|-------------|
| `query_customer_data` | Query CIS_CUST_VIEW by meter IDs, or resolve meter IDs from ElectricDevice GlobalIDs. |

### MCP Resources

| Resource URI | Description |
|------|-------------|
| `resource://utility-network/workflow-guidance` | Workflow decision trees, named traces strategy, terminal selection |
| `resource://utility-network/data-model-guidance` | Data model disambiguation, asset type resolution, customer discovery |
| `resource://utility-network/trace-interpretation` | Reading trace results, phase bitfields, troubleshooting |

## Usage

After install, the router appears in:

```bash
psmcp router list
```

### Terminal selection workflow

Direction-sensitive traces starting from a multi-terminal device need the correct
`terminal_id`:

1. Call `network_list_named_traces` and note the chosen trace's `traceType`.
2. Call `network_device_terminals` for the starting feature.
3. Pick the terminal whose `recommendedFor` matches the trace direction —
   `"downstream"` (secondary / low side / line side) for downstream traces,
   `"upstream"` (primary / high side) for upstream/isolation traces.
   A feature with a single terminal reports `recommendedFor: "any"` and a
   `terminalNote`. Use that terminal for every trace direction.
4. If more than one terminal matches or the direction is unclear, ask the user to pick
   rather than guessing.
5. Call `network_named_trace` with the chosen `terminal_id`.

### Generic trace

`network_generic_trace` is the single entry point for traces that the saved-trace and
directional tools cannot express. It maps onto the
[Trace (UtilityNetworkServer)](https://developers.arcgis.com/rest/services-reference/enterprise/trace-utility-network-server/)
REST operation.

#### Arguments

| Argument | REST parameter | Notes |
|----------|----------------|-------|
| `trace_type` | `traceType` | `connected`, `subnetwork`, `subnetworkController`, `upstream`, `downstream`, `isolation`, `loops`, `path`, `circuit`, `shortestPath` (deprecated) |
| `starting_points` | `traceLocations` (`startingPoint`) | List of `{global_id, terminal_id?, percent_along?}`. |
| `barriers` | `traceLocations` (`barrier`) | Same shape, plus `is_filter_barrier`. |
| `stopping_points` | `traceLocations` (`stoppingPoint`) | `path` traces only. |
| `trace_configuration` | `traceConfiguration` | Sent as given. Replaces the tier defaults. |
| `configuration_overrides` | `traceConfiguration` | Merged over the tier defaults (or over `trace_configuration`). |
| `result_types` | `resultTypes` | `elements` (default), `features`, `connectivity`, `aggregatedGeometry`, `associations`, `circuits`. Strings or objects (`include_geometry`, `include_propagated_values`, `network_attribute_names`, ...). |
| `domain_network_name`, `tier_name`, `target_tier_name`, `subnetwork_name` | inside `traceConfiguration` | Fill keys the configuration leaves empty. They never replace a populated value. |
| `moment`, `out_sr` | `moment`, `outSR` | Session moment (epoch ms) and output wkid. |
| `use_tier_defaults`, `max_elements`, `summarize` | router only | Tier defaults on/off, element cap (default 500), grouped counts. |

#### Required inputs by trace type

M = mandatory, O = optional, X = rejected or unused. The agent skill
([`skills/generic_trace.md`](src/psmcp_router_utilitynetwork/skills/generic_trace.md))
also lists which tool supplies each value.

| Trace type | Starting points | Barriers | Stopping points | Also needed |
|------------|-----------------|----------|-----------------|-------------|
| `connected` | M | O | X | |
| `subnetwork` | M, or `subnetwork_name` | O | X | Domain network and tier (derived from the start, or pass both with `subnetwork_name`) |
| `subnetworkController` | M, or `subnetwork_name` | O | X | Same as `subnetwork` |
| `upstream` | M | O | X | Tier (derived; pass `tier_name` if ambiguous) |
| `downstream` | M | O | X | Tier (derived; pass `tier_name` if ambiguous) |
| `isolation` | M | O | X | A filter barrier, in the configuration or on a barrier location |
| `loops` | M, exactly one | O | X | |
| `path` | M | O | M for traditional domains | Enterprise 12.1 or later. Optional cost attribute, `numPaths`, `maxHops` |
| `circuit` | M, or `trace_configuration.circuitName` | O | X | Telecom domain network. Enterprise 12.1 or later |
| `shortestPath` | M, two | O | X | `shortestPathNetworkAttributeName`. Deprecated in 12.1: use `path` |

#### Behavior added by the router

- **Tier defaults.** For `upstream`, `downstream`, `isolation`, `subnetwork` and
  `subnetworkController` with no `trace_configuration`, the tier's subnetwork definition is
  used as the configuration. The tier comes from the first starting point's subnetwork
  membership, or from `domain_network_name` + `tier_name` when there are no starting
  points. An ambiguous tier returns `status: "tier_ambiguous"`, and a feature outside any
  subnetwork returns `tier_no_membership`. Set `use_tier_defaults=false` to disable.
- **Validation before any network call.** A bad trace type, a missing GlobalID,
  `percent_along` outside 0 to 1, an unknown result type, a missing starting point,
  more than one `loops` start, `stopping_points` on a non-path trace, or an isolation
  trace with no filter barrier returns `{"error": "..."}`.
- **Warnings.** A `warnings` list is added for a deprecated `shortestPath` and for a
  `path` trace without stopping points.
- **Retry.** If the server reports "No starting points found", topology is validated
  once and the trace is retried.
- **Name enrichment.** `elements` gain `sourceName`, `assetGroupName`, `assetTypeName`.
- **Large results.** `max_elements` caps returned elements and sets `totalElements` and
  `truncated`. `summarize=true` adds counts grouped by source and asset group.

#### Examples

Downstream trace with a barrier, returning elements and a merged geometry:

```json
{
  "trace_type": "downstream",
  "starting_points": [{"global_id": "{GUID}", "terminal_id": 2}],
  "barriers": [{"global_id": "{GUID2}", "terminal_id": 1}],
  "result_types": ["elements", {"type": "aggregatedGeometry"}],
  "summarize": true
}
```

Subnetwork by name, with extra inclusion flags on top of the tier defaults:

```json
{
  "trace_type": "subnetwork",
  "subnetwork_name": "RMT001",
  "domain_network_name": "ElectricDistribution",
  "tier_name": "Medium Voltage Radial",
  "configuration_overrides": {"includeContainers": true, "includeContent": true},
  "result_types": ["elements"]
}
```

Shortest route between two devices (Enterprise 12.1 or later):

```json
{
  "trace_type": "path",
  "starting_points": [{"global_id": "{A}", "terminal_id": 1}],
  "stopping_points": [{"global_id": "{Z}", "terminal_id": 1}],
  "configuration_overrides": {"shortestPathNetworkAttributeName": "Shape length", "numPaths": 1},
  "result_types": ["elements", "connectivity"]
}
```

#### Which trace tool to use

| Need | Tool |
|------|------|
| A saved configuration matches | `network_named_trace` |
| Simple directional trace from one feature | `network_downstream_trace`, `network_upstream_trace` |
| Everything else | `network_generic_trace` |

The agent-facing guide is the `utility_network_generic_trace` prompt, served from
[`skills/generic_trace.md`](src/psmcp_router_utilitynetwork/skills/generic_trace.md). It
walks an agent through the pre-flight tools (`network_initialize_session`,
`network_list_named_traces`, `network_device_terminals`, `network_get_metadata`), the
inputs each trace type needs, the configuration keys and condition format, result type
choice, and how to react to each response.

### Metadata caching

The data element (fetched via `queryDataElements`) is expensive. All metadata tools
share a single cached copy keyed by service URL. The cache lives for the process
lifetime until:

- `network_refresh_metadata` is called explicitly, or
- A different `network_service_url` is passed (replaces the cached entry).

### Direct traces vs. named traces

- **Named traces** (`network_named_trace`) use a server-saved configuration that
  encapsulates barriers, conditions, output filters, and result types. Preferred when
  a matching saved config exists.
- **Direct traces** (`network_downstream_trace`, `network_upstream_trace`) hit the
  trace endpoint without a named config. The from-tier is derived from the start
  feature, and that tier's subnetwork trace definition (its condition barriers and
  inclusion flags) is applied automatically so the trace stops at subnetwork
  controllers. `domain_network_name` and `tier_name` are optional hints/
  disambiguators, not the sole source of truth.

  The from-tier is resolved in this order:

  1. **Actual subnetwork membership** — the tier(s) of the subnetwork(s) the
     feature is genuinely a member of (`SUBNETWORKNAME` → `TIERNAME`), not the tiers
     it is merely configured as a valid object in. This is authoritative. A single
     member tier resolves cleanly. A feature that is an actual member of subnetworks
     in more than one tier — e.g. a barrier object between two subnetworks, which can
     occur even in a partitioned domain — yields multiple tiers (`memberTiers`).
  2. **Configured-validity fallback** — when the feature is *not* a member of a
     built subnetwork (for example the subnetwork failed to build) but a controller
     may still be traceable, the from-tier is inferred from the tiers the feature is
     a configured valid object of. A single configured tier resolves best-effort;
     the trace response is flagged with `tierResolution.resolvedBy = "configured"`
     and a note that the result should be verified. Configured validity is usually
     broad (a device is often valid in several tiers), so this frequently yields
     multiple tiers (`configuredTiers`).
  3. **Disambiguation** — when more than one tier remains, a supplied `tier_name`
     is validated against the candidate set and used; otherwise the tool returns a
     structured `tier_ambiguous` result (listing `memberTiers` or `configuredTiers`)
     so the caller can choose. If the feature is neither a member nor configured-
     valid in any tier, it returns `tier_no_membership`. In all these cases the tool
     declines to run an invalid trace rather than guessing.
- **Generic trace** (`network_trace`) handles all other trace types — isolation,
  connected, subnetwork, subnetworkController, loops, shortestPath — with enriched
  element names in the output.

## Dependencies

- `ps-mcp>=0.1.0,<1.0` — shared core (token resolution, logging)
- `arcgis>=2.4,<3` — ArcGIS API for Python (GIS connection, FeatureLayerCollection,
  UtilityNetworkManager)

## Development

Run the router tests and lint from the repo root:

```bash
uv run pytest packages/psmcp-router-utilitynetwork/tests/test_utility_network_service.py
uv run ruff check packages/psmcp-router-utilitynetwork/src
```

Skill files live in `src/psmcp_router_utilitynetwork/skills/` and are served as MCP
prompts through `_read_skill`. To add a skill, add the `.md` file and a
`@utilitynetwork_router.prompt` that reads it.


See the repo-level [README](../../README.md) and
[docs/CREATING_A_ROUTER.md](../../docs/CREATING_A_ROUTER.md) for the broader router
development workflow.
