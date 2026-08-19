---
inclusion: manual
---

# Utility Network Workflow Guidance

This steering file teaches you how to reason about utility network workflows, select the correct tools, resolve terminals, and orchestrate multi-step operations.

---

## Decision Tree: Which Tool for Which Question

| User Question Pattern | Tool Chain |
|----------------------|------------|
| "What is the total connected downstream load?" | `network_list_named_traces` → match load trace → `network_named_trace` |
| "List all downstream customers" / "Who is affected by this outage?" | Use prompt `utility_network_downstream_customer_impact` (multi-step: terminal → trace → filter → resolve) |
| "What isolation devices must be operated?" / "How do I isolate this?" | Use prompt `utility_network_isolation_analysis` (multi-step: terminal → trace → filter devices) |
| "Given this flood/fire area, what customers are affected?" | Use prompt `utility_network_spatial_impact` (multi-step: spatial query → minimize → trace → resolve) |
| "Trace upstream from this meter to the source" | `network_upstream_trace` |
| "What is the load at [address]?" | Probe data model → resolve address to service point → trace |
| "811 call-before-you-dig" / "What assets near this dig site?" | Use prompt `utility_network_spatial_impact` (geocode → buffer → spatial query → trace) |
| "What is connected to this device?" | `network_trace` with `trace_type="connected"` |
| "Find loops in the network" | `network_trace` with `trace_type="loops"` |
| "What subnetwork does this belong to?" | `network_trace` with `trace_type="subnetwork"` + `subnetwork_name` |

### Address-Based Workflows

When the user provides an address rather than a GlobalID:

1. Use `find_address_candidates` to geocode the address
2. Use the resulting coordinates to spatially query network features via `query_feature_layer`
3. Identify the service point or device closest to the geocoded location
4. Extract its GlobalID and proceed with the appropriate trace/workflow tool
5. Warn the user that geocode + spatial proximity is approximate — confirm the identified feature before tracing

### 811 Call-Before-You-Dig Workflow

1. Geocode the dig location via `find_address_candidates` (or accept user-provided geometry)
2. If a point location, buffer by 250 feet (or user-specified distance) to create an impact polygon
3. Call `network_spatial_impact` with the buffered geometry
4. Report all network assets within the impact area as potentially impacted if dig was to damage the network

---

## Named Traces First Strategy

When a trace is needed, ALWAYS follow this sequence:

### 1. Discover

Call `network_list_named_traces` to retrieve all available named trace configurations. Each entry includes `name`, `description`, `traceType`, and `creator`.

### 2. Match

Inspect the returned configurations against the user's intent:
- Compare trace names and descriptions to what the user is asking for
- Check `traceType` aligns with the direction needed (downstream, upstream, isolation, etc.)
- Named traces authored by utility engineers encode the correct barriers, functions, propagators, and output filters for the deployment

### 3. Offer

Present the matched trace(s) to the user for confirmation before executing. Example: "I found a named trace called 'Balanced Distribution Transformer Load and Count' that calculates connected load downstream. Shall I run it?"

### 4. Execute

Run the confirmed trace via `network_named_trace` with the correct starting GlobalID and terminal ID.

### 5. Fallback

Only fall back to direct trace tools when NO named trace matches the user's intent:
- `network_downstream_trace` / `network_upstream_trace` — for simple directional traces
- `network_trace` — for isolation, connected, subnetwork, loops, etc.
- These direct traces do NOT include barriers, functions, propagators, or output filters

### Why Named Traces Are Preferred

- They are authored by utility engineers who understand the network's specific configuration
- They include correct barriers (normally-open devices, phase barriers)
- They include functions (load sums, customer counts) and propagators
- They include output filters that limit results to relevant elements
- Adding a new workflow = publishing a named trace on the server (no MCP code changes needed)

---

## Terminal Selection Logic

### Downstream Traces

Use the **DOWNSTREAM** terminal:
- Secondary / low side / line side
- `isUpstreamTerminal` is `False`
- `recommendedFor` is `'downstream'`

### Upstream and Isolation Traces

Use the **UPSTREAM** terminal:
- Primary / high side / source side
- `isUpstreamTerminal` is `True`
- `recommendedFor` is `'upstream'`

### Ambiguous Cases

If multiple terminals match the needed direction, or the direction is unclear:
- **DO NOT guess** — present the terminal list to the user
- Let the user choose
- Single-terminal features do not require terminal selection

---

## Tier-Terminal Directional Coupling for Multi-Tier Devices

A device connecting two tiers (e.g., a station transformer between transmission and distribution) has terminals on BOTH tiers:

```
[Transmission Tier] ←→ [HIGH/UPSTREAM Terminal] — Device — [LOW/DOWNSTREAM Terminal] ←→ [Distribution Tier]
```

Key rules:
- The **upstream terminal** connects to the **higher tier** (source side)
- The **downstream terminal** connects to the **lower tier** (load side)

### Examples

**Distribution downstream trace starting at a station transformer:**
→ Use the downstream/low-side terminal (which feeds INTO distribution)

**Transmission upstream trace from the same transformer:**
→ Use the upstream/high-side terminal (which connects TO transmission)

**Isolation trace on a distribution element fed by that transformer:**
→ The isolation trace starts upstream, so it may reach the transformer's upstream terminal on the transmission tier

### How Tier Rank Helps

The `tiers` catalog returned by `network_device_terminals` includes `rank` for each tier. Higher rank = higher voltage tier (closer to source). Use rank to confirm directional coupling when tier names alone are ambiguous.

---

## Using `network_device_terminals`

This tool resolves BOTH terminal information AND tier context in a single call. Always call it BEFORE any trace on a multi-terminal device.

### What It Returns

| Field | Purpose |
|-------|---------|
| `terminals` | List of `{terminalId, terminalName, isUpstreamTerminal, recommendedFor}` |
| `terminalCount` | Number of terminals (1 = no selection needed) |
| `domainNetworkName` | Which domain network the feature belongs to |
| `assetGroupCode` / `assetGroupName` | The feature's asset group |
| `assetTypeCode` / `assetTypeName` | The feature's asset type |
| `featureTierNames` / `featureTierRanks` | Which tier(s) the feature participates in |
| `subnetworkNames` | The subnetwork(s) the feature belongs to |
| `tiers` | Full tier catalog for the domain: `{tierId, name, rank, tierGroupName}` |

### How to Use the Response

1. Check `terminalCount` — if 1, no terminal selection needed
2. Read `recommendedFor` on each terminal to pick the right one for your trace direction
3. Use `featureTierNames` to confirm the feature is on the expected tier
4. If `featureTierNames` is empty, use `subnetworkNames` + `tiers` catalog to reason about tier membership

---

## How to Get a Starting GlobalID

The starting GlobalID is required for all trace operations. Sources:

### From the User Directly

The user may provide a GlobalID or select a feature on a map (the client passes the GlobalID).

### From a Feature Query

Use `query_feature_layer` with an attribute or spatial filter:
```
query_feature_layer(endpoint_url=".../FeatureServer/0", parameters={"where": "facilityid = 'ABC123'", "outFields": "globalid", "returnGeometry": false})
```

### From Address Resolution

1. Geocode via `find_address_candidates`
2. Spatial query near the geocoded point to find nearby network features
3. Extract the GlobalID from the closest match

### From Portal Item Inspection

1. Use `search_portal` or `get_item_info` to find a web map
2. Inspect its layers to get FeatureServer URLs
3. Query the appropriate layer for the feature of interest

### Validation

Always confirm the GlobalID identifies a valid network feature before tracing. If a trace returns "feature not found" or an empty result, verify the GlobalID against the network's source layers.

---

## Trace Configuration Strategy

### Named Traces (Preferred for Complex Workflows)

Use `network_named_trace` when the workflow requires:
- Barriers (normally-open devices, specific phase barriers)
- Functions (load calculation, customer count aggregation)
- Propagators (phase propagation, status propagation)
- Output filters (only return specific element types)

Named traces are pre-configured on the server by utility engineers.

### `network_trace` (Generic — Simple Traces)

Use for simple traces that only need:
- A trace type (isolation, connected, subnetwork, subnetworkController, loops)
- A starting point (GlobalID + optional terminal)
- Optional domain network / tier scoping

No barriers, functions, propagators, or output filters are available via this tool.

### `network_downstream_trace` / `network_upstream_trace` (Simple Directional)

Use for straightforward directional traces without complex configuration. Same capabilities as `network_trace` with `trace_type="downstream"` or `"upstream"`, but with dedicated discoverability.

### When No Named Trace Exists and Complex Config is Needed

If the user needs a workflow with barriers, functions, or propagators but no suitable named trace exists:
- Recommend the user contact their GIS administrator to publish a named trace configuration
- Explain that named traces encode deployment-specific knowledge (which devices are barriers, which attributes represent load, etc.)
- A new named trace on the server immediately becomes available via `network_list_named_traces` + `network_named_trace` — no MCP code changes needed

---

## Customer Data Resolution — Conditional Workflow Step

### How It Works

Workflow tools (`network_downstream_customer_impact`, `network_spatial_impact`) resolve customers ONLY when the LLM provides explicit configuration:

| Parameter | Purpose |
|-----------|---------|
| `customer_layer_url` | Full URL to the customer data layer/table |
| `customer_join_field` | Field name used to join service points to customer records |
| `service_point_layer_url` | (Optional) Explicit service point layer URL if needed |

### When Config is NOT Provided

The workflow tool returns:
- Trace results with enriched element names
- Service point GlobalIDs identified from the trace
- A guidance note explaining that customer data source discovery is needed

### When Config IS Provided

The workflow tool additionally:
- Queries the specified customer layer using the join field
- Applies subtype domain resolution on customer records
- Formats results with customer identifiers, addresses, and load values

### Why This Design

- Customer data layer names are NEVER standardized across utilities
- Layer names like "CIS_CUST_VIEW", "CUSTOMER_ACCOUNT", "Billing_Data" are all valid
- Join mechanisms vary: meter_id, account_number, service_point GlobalID, premise_id, spatial proximity
- The tools NEVER hard-code layer names, table names, or field names

---

## Discovery-First Pattern for Customer Data

The LLM discovers customer data BEFORE calling workflow tools, not after.

### Discovery Steps

1. **Probe available layers/tables** on the FeatureServer:
   - Use `get_service_or_layer_details` on the utility network FeatureServer URL (no layer ID) to list all layers and tables
   - Look for sources with names containing: CIS, customer, account, subscriber, consumer, ratepayer, billing, meter, service

2. **Sample candidate layers:**
   - Use `get_sample_feature_layer_data` on promising layers/tables
   - Inspect field names and sample values
   - Look for fields that could join to service point features (meter IDs, account numbers, GlobalIDs)

3. **Verify join relationship:**
   - Compare fields in the candidate customer layer to fields on the service point features
   - Use `query_feature_layer` to test the join (query a known service point's meter_id against the customer layer)
   - Common join patterns:
     - `meter_id` field on service point → `meter_id` field on customer table
     - `account_number` on service point → `account_no` on customer table
     - Service point `GlobalID` → `service_point_globalid` on customer table
     - `premise_id` on both layers
     - Spatial proximity (last resort)

4. **Present to user for confirmation:**
   - Show the discovered layer, join field, and a sample match
   - Ask the user to confirm before proceeding

5. **Pass config to workflow tools:**
   - Only after confirmation, call the workflow tool with `customer_layer_url` and `customer_join_field`

### Discovery Tools

| Tool | Use For |
|------|---------|
| `get_service_or_layer_details` | List layers/tables on a FeatureServer, inspect fields and subtypes |
| `get_sample_feature_layer_data` | Preview data in candidate layers |
| `query_feature_layer` | Test join relationships, query by specific values |
| `search_portal` | Find additional data sources not on the UN FeatureServer |

### If No Customer Data is Found

- Report the trace results without customer resolution
- Explain that no customer data layer was found on the accessible services
- Suggest the user provide the customer data source location if one exists outside the FeatureServer
