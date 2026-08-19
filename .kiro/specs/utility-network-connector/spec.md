# Spec: Utility Network Connector

## Related Documents

- [Requirements](requirements.md) — Functional and non-functional requirements
- [Design](design.md) — Architecture, tool design, module organization, steering files
- [Tasks](tasks.md) — Implementation task checklist

## Problem Statement

An LLM needs to work with Esri Utility Network data services and trace functions to complete workflows such as downstream customer impact analysis, isolation device identification, and spatial impact assessment. The existing `psmcp-router-utilitynetwork` already provides foundational tools (named traces, direct upstream/downstream traces, terminal resolution, customer data). We need to extend this router with metadata discovery, association queries, additional trace types, trace configuration builders, result formatting, and workflow orchestration tools — plus LLM steering files that guide tool selection and result interpretation.

## Approach

**Extend the existing router** — new modules added to `psmcp-router-utilitynetwork` that register tools on the same `utilitynetwork_router` FastMCP instance.

## What Already Exists

| Capability | Tool/Helper | Status |
|-----------|-------------|--------|
| Named trace execution | `network_named_trace` | ✅ Done |
| Named trace discovery | `network_list_named_traces` | ✅ Done |
| Terminal + tier resolution | `network_device_terminals` | ✅ Done |
| Direct downstream trace | `network_downstream_trace` | ✅ Done |
| Direct upstream trace | `network_upstream_trace` | ✅ Done |
| Customer data resolution | `query_customer_data` | ✅ Done |
| Data element fetch | `_un_data_element()` helper | ✅ Done (internal) |
| Trace with topology retry | `run_trace()` helper | ✅ Done (internal) |
| Feature queries | `query_feature_layer` (feature_service router) | ✅ Done |
| Geocoding | `find_address_candidates` (location_services router) | ✅ Done |

## What's Being Added

| Capability | New Tool/Component | Task |
|-----------|-------------------|------|
| Metadata discovery (6 tools) | `network_get_domain_networks`, `network_get_asset_types`, etc. | Task 1 |
| Association queries | `network_query_associations` | Task 2 |
| Additional trace types | `network_isolation_trace`, `network_connected_trace`, `network_subnetwork_trace`, `network_trace` | Task 3 |
| Configured traces with builders | `network_configured_trace` + builder functions | Task 4 |
| Result formatting | `summarize_trace_results`, `format_customer_impact`, `truncate_results` | Task 5 |
| Workflow orchestration (3 tools) | `network_downstream_customer_impact`, `network_isolation_analysis`, `network_spatial_impact` | Task 6 |
| LLM steering (3 files) | `utility-network-workflows.md`, `utility-network-data-model.md`, `utility-network-trace-interpretation.md` | Task 7 |

## Key Design Decisions

1. **Single router, multiple modules** — new code in separate `.py` files but all tools on the same router instance
2. **`arcgis` Python API** — consistent with existing tools; no httpx for UN operations
3. **Module-level metadata cache** — queryDataElements is expensive; cache with explicit invalidation
4. **Named traces first via steering** — LLM guidance handles prioritization, not server-side logic
5. **Manual-inclusion steering files** — `.kiro/steering/` with `inclusion: manual` to avoid polluting non-UN sessions

## Success Criteria

1. All 7 target workflows completable end-to-end via MCP tools
2. All trace types work (downstream, upstream, isolation, connected, subnetwork, shortest_path, loops)
3. Metadata tools return focused subsets without redundant fetches
4. Workflow tools orchestrate multi-step operations in a single call
5. Steering files guide correct tool selection and result interpretation
6. All new tools discoverable via `psmcp router list`
7. Unit tests pass with mocked arcgis API responses
