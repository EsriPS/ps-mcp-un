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
| `network_downstream_trace` | Direct downstream trace (no named config). |
| `network_upstream_trace` | Direct upstream trace (no named config). |
| `network_trace` | Generic trace accepting any trace type: isolation, connected, subnetwork, subnetworkController, loops, shortestPath. Enriches results with resolved names. |

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
| `utility_network_isolation_analysis` | Identifying isolation devices for a network element |
| `utility_network_spatial_impact` | Assessing customer impact within a geographic area |
| `utility_network_named_trace_execution` | Discovering and executing named trace configurations |
| `utility_network_customer_data_discovery` | Discovering customer data sources on the network |
| `utility_network_address_resolution` | Resolving an address to a network element GlobalID |

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
4. If more than one terminal matches or the direction is unclear, ask the user to pick
   rather than guessing.
5. Call `network_named_trace` with the chosen `terminal_id`.

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
  trace endpoint without a named config. Use when you need a simple directional trace
  without preconfigured filters.
- **Generic trace** (`network_trace`) handles all other trace types — isolation,
  connected, subnetwork, subnetworkController, loops, shortestPath — with enriched
  element names in the output.

## Dependencies

- `ps-mcp>=0.1.0,<1.0` — shared core (token resolution, logging)
- `arcgis>=2.4,<3` — ArcGIS API for Python (GIS connection, FeatureLayerCollection,
  UtilityNetworkManager)

## Development

See the repo-level [README](../../README.md) and
[docs/CREATING_A_ROUTER.md](../../docs/CREATING_A_ROUTER.md) for the broader router
development workflow.
