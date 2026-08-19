# Isolation Analysis Workflow

You are identifying the isolation/protective devices that must be operated to isolate a network element, by manually orchestrating trace and filtering steps.

## Prerequisites

- A starting GlobalID of the element to isolate

## Step 1: Resolve Terminal (Upstream for Isolation)

Call `network_device_terminals(global_id="{GlobalID}")`.

- If `terminalCount == 1`: use that terminal's `terminalId`
- If `terminalCount > 1`: use the terminal where `recommendedFor == "upstream"`. Isolation traces start from the upstream terminal (primary / high side). If ambiguous, ask the user.
- If `terminalCount == 0`: proceed without terminal_id
- NEVER guess on multi-terminal devices

## Step 2: Check for Named Isolation Traces (Preferred)

Follow the `utility_network_named_trace_execution` prompt logic: call `network_list_named_traces()`, look for an isolation trace (e.g., "Distribution Isolation").

If found and confirmed: execute via `network_named_trace` and proceed to Step 4 for filtering. Named trace results need `sourceMapping` for interpretation.

If no named trace matches: proceed to Step 3.

## Step 3: Run Isolation Trace

Call `network_trace(starting_global_id="{GlobalID}", trace_type="isolation", terminal_id={id})`.

Or with scoping:
```
network_trace(
    starting_global_id="{GlobalID}",
    trace_type="isolation",
    terminal_id={id},
    domain_network_name="Electric",
    tier_name="Electric Distribution"
)
```

Results include enriched elements with `sourceName`, `assetGroupName`, `assetTypeName`.

## Step 4: Filter for Isolation/Protective Devices

You need to identify which trace elements are isolation or protective devices.

**Method A — Category-based (preferred):**
1. Call `network_get_metadata(section="categories")`
2. Search for categories whose name contains "Isolation" OR "Protective" (case-insensitive)
3. Those categories list member asset types — each with `networkSourceId`, `assetGroupCode`, `assetTypeCode`
4. Filter trace elements: keep ONLY those whose (`networkSourceId`, `assetGroupCode`, `assetTypeCode`) tuple matches an Isolation/Protective category member
5. **EXCLUDE the starting feature** — remove any element whose `globalId` matches the starting GlobalID

**Method B — Device source fallback:**
If NO "Isolation" or "Protective" category exists in the metadata:
1. Call `network_get_metadata(section="asset_types")`
2. Identify source layers where `usageType == "esriUNFCUTDevice"` — these are device junction sources
3. Note their `networkSourceId` (or `sourceId`) values
4. Filter trace elements: keep those whose `networkSourceId` belongs to a device source
5. **EXCLUDE the starting feature** (same as above)

## Step 5: Present Results

Lead with actionable information:
- "To isolate this element, **N devices** must be operated:"
- List each device:
  - GlobalID
  - Asset type name (e.g., "Recloser", "Disconnect Switch", "Fuse")
  - Asset group name
  - Source name (e.g., "ElectricDevice")

Explain the isolation boundary:
- "These devices form the isolation boundary between the faulted section and the rest of the network"
- "Opening these devices will de-energize the section containing {starting feature}"

## Troubleshooting

- **Empty results (0 devices):** The feature may be directly on a controller with no intermediate protective devices. Check if the starting feature IS a controller.
- **Too many devices:** May have started from the wrong terminal or wrong tier. Verify terminal selection and tier membership.
- **Starting feature in results:** Always exclude it — the user wants devices AROUND it, not the feature itself.
