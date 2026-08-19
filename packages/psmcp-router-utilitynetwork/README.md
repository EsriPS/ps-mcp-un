# psmcp-router-utilitynetwork

PS-MCP router plugin: `utilitynetwork`.

This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a running
PS-MCP server via a `psmcp.routers` entry point and provides utility network trace
tools.

## Install

```bash
uv pip install psmcp-router-utilitynetwork
```

Or, in the workspace:

```bash
uv sync --all-packages
```

## Usage

After install, the router appears in:

```bash
psmcp router list
```

The package exposes the following tools (via the ArcGIS API for Python
`UtilityNetworkManager` and feature layer queries):

- `network_list_named_traces` — lists the saved/named trace configurations, each with
  its `traceType` (the direction it was configured with).
- `network_named_trace` — runs a saved/named trace configuration from a starting feature
  `starting_global_id`. `trace_type` is optional and defaults to the configuration's
  persisted type; pass `terminal_id` when starting from a multi-terminal device.
- `network_device_terminals` — `global_id`; returns the terminal ID(s), names, and
  `recommendedFor`/`isUpstreamTerminal` direction hints for a network feature, plus the
  source's `usageType`/`isDevice` role. Use it to choose the correct `terminal_id` before
  running a direction-sensitive trace.
- `query_customer_data` — `global_ids`, optional `meter_ids`; queries `CIS_CUST_VIEW`
  (excludes PII fields).

### Terminal selection workflow

Direction-sensitive named traces (downstream vs. upstream/isolation) starting from a
device with multiple terminals need the correct `terminal_id`:

1. Call `network_list_named_traces` and note the chosen trace's `traceType`.
2. Call `network_device_terminals` for the starting feature.
3. Pick the terminal whose `recommendedFor` matches the trace direction —
   `downstream` (secondary / low side / line side) for downstream traces,
   `upstream` (primary / high side) for upstream/isolation traces.
4. If more than one terminal matches or the direction is unclear, ask the user to pick
   (a map selection in the client) rather than guessing.
5. Call `network_named_trace` with the chosen `terminal_id`.

Pass the utility network **FeatureServer** URL. Authentication uses `resolve_token()`
and `ARCGIS_PORTAL_URL` / `ARCGIS_TOKEN` like other PS-MCP routers.

See the repo-level [README](../../README.md) and [docs/CREATING_A_ROUTER.md](../../docs/CREATING_A_ROUTER.md)
for the broader router development workflow.
