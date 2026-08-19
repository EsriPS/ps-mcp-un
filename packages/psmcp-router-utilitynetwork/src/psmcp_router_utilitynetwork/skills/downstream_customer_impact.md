# Downstream Customer Impact Workflow

You are identifying all customers affected downstream of a network device by manually orchestrating the trace, filtering, and resolution steps.

## Prerequisites

- A starting GlobalID (from user, feature query, or address resolution)
- Optionally: customer data layer URL and join field (run Customer Data Discovery workflow first if unknown)

## Step 1: Resolve Terminal

Call `network_device_terminals(global_id="{GlobalID}")`.

- If `terminalCount == 1`: use that terminal's `terminalId`
- If `terminalCount > 1`: use the terminal where `recommendedFor == "downstream"`. If ambiguous, ask the user.
- If `terminalCount == 0`: proceed without terminal_id
- NEVER guess on multi-terminal devices

## Step 2: Check for Named Traces (Preferred)

Follow the `utility_network_named_trace_execution` prompt logic: call `network_list_named_traces()`, look for a downstream trace matching the user's intent (load calculation, customer counting, etc.).

If a named trace is found and confirmed by the user:
- Execute it via `network_named_trace` and skip to Step 5
- Named trace results include `globalFunctionResults` with computed values
- Note: named trace elements are NOT enriched — use `sourceMapping` to identify service points

If no named trace matches: proceed to Step 3.

## Step 3: Run Downstream Trace

Call `network_downstream_trace(starting_global_id="{GlobalID}", terminal_id={id})`.

Or if you need domain/tier scoping:
```
network_downstream_trace(
    starting_global_id="{GlobalID}",
    terminal_id={id},
    domain_network_name="Electric",
    tier_name="Electric Distribution"
)
```

The results include enriched elements with `sourceName`, `assetGroupName`, `assetTypeName`.

## Step 4: Filter for Service Points

You need to identify which trace elements are service points.

**Method A — Category-based (preferred):**
1. Call `network_get_metadata(section="categories")`
2. Search the results for a category whose name contains "Service Point" (case-insensitive)
3. That category lists its member asset types — each member has `networkSourceId`, `assetGroupCode`, `assetTypeCode`
4. Filter trace elements: keep ONLY those whose (`networkSourceId`, `assetGroupCode`, `assetTypeCode`) tuple matches a Service Point category member

**Method B — Source name fallback:**
If NO "Service Point" category exists in the metadata:
- Filter trace elements where `sourceName` contains "service" (case-insensitive)
- This is less precise but catches most configurations

**Extract GlobalIDs:**
Collect the `globalId` from each identified service point element.

## Step 5: Resolve Customer Data (Conditional)

### If customer_layer_url AND customer_join_field are known:

**5a. Get join field values from service points:**

If `service_point_layer_url` is available:
```
query_feature_layer(
    endpoint_url="{service_point_layer_url}",
    parameters={
        "where": "globalid IN ('{gid1}', '{gid2}', ...)",
        "outFields": "globalid,{join_field}",
        "returnGeometry": "false"
    }
)
```
Extract the join field values from the response features using case-insensitive field lookup (iterate attribute keys, match `join_field.lower()`). Deduplicate values while preserving order.

If `service_point_layer_url` is NOT available:
- Attempt to read the join field directly from trace element attributes (case-insensitive key match)
- Trace elements often lack full attributes, so this is a fallback

**5b. Handle empty join values:**
If no join values are found, report:
- Service point count
- Note: "No join field values found on service point features for field '{join_field}'"
- The trace results are still valid

**5c. Query customer layer:**
```
query_feature_layer(
    endpoint_url="{customer_layer_url}",
    parameters={
        "where": "{join_field} IN ('{val1}', '{val2}', ...)",
        "outFields": "*",
        "returnGeometry": "false"
    }
)
```

**5d. Resolve coded values on customer records:**
```
network_resolve_coded_values(features=[...customer attributes...], layer_url="{customer_layer_url}")
```

**5e. Present results:** customer count, total load (if available), list of affected customers.

### If customer config is NOT known:

- Report the service point GlobalIDs and count
- Suggest: "Customer data source not configured. To resolve customers, provide customer_layer_url (the URL of the customer data layer/table) and customer_join_field (the field linking service points to customers, e.g., 'meter_id'). Use network_get_metadata or search_portal to discover the customer data source."
- The trace results are still valuable without customer data

### Error handling:

If any step in the customer resolution fails (bad URL, field doesn't exist, HTTP error):
- Still report the trace results, service point count, and service point GlobalIDs
- Include a note about the failure: "Customer resolution failed: {error}. Trace results and service points are still available."
- Do NOT let customer resolution failure discard the trace work

## Step 6: Present Results

Lead with the answer:
- "X service points are downstream, serving Y customers with Z kW total load"
- Or if no customer data: "X service points found downstream of {device}. Customer data not yet resolved."

Include:
- Total element count from the trace
- Service point count
- Customer count and load (if resolved)
- Phase breakdown (if available from named trace functions)
