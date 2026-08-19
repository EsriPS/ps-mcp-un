---
inclusion: manual
---

# Utility Network Trace Result Interpretation

This steering file teaches you how to read, interpret, and explain utility network trace results to users in plain language.

---

## Reading Trace Results

Trace results have three main components: `elements`, `sourceMapping`, and `globalFunctionResults`.

### Elements

A list of features the trace traversed. Each element contains:

| Field | Type | Meaning |
|-------|------|---------|
| `networkSourceId` | int | Numeric ID of the source layer (resolve via sourceMapping) |
| `globalId` | str (GUID) | Unique identifier for the feature |
| `objectId` | int | Object ID within the source layer |
| `terminalId` | int | Terminal the trace passed through (0 if single-terminal) |
| `assetGroupCode` | int | Numeric asset group code |
| `assetTypeCode` | int | Numeric asset type code |

### Source Mapping

A dict mapping `networkSourceId` (as string key) to the source/layer name:

```
"9" → "ElectricDevice"
"7" → "ElectricLine"
"12" → "ElectricJunction"
```

Use this to translate numeric source IDs on elements into meaningful layer names.

### Global Function Results

Aggregated computation results produced by named trace configurations. Each entry:

| Field | Meaning |
|-------|---------|
| `functionType` | The aggregation type (Sum, Count, Min, Max, Average, Add) |
| `networkAttributeName` | Which network attribute was aggregated (e.g., "Service Load", "Phases Current") |
| `result` | The computed value |
| `conditions` | Filter conditions applied before aggregation (may be empty) |

Function results are only present when running a named trace that has functions configured.

### Enriched vs. Raw Results

| Tool | Returns |
|------|---------|
| `network_trace` | Enriched: elements include `sourceName`, `assetGroupName`, `assetTypeName` — no manual mapping needed |
| `network_downstream_trace` | Enriched |
| `network_upstream_trace` | Enriched |
| `network_named_trace` | Raw: only `elements` + `sourceMapping` + `globalFunctionResults` — you must use `sourceMapping` to interpret source IDs |

When working with `network_named_trace` results, cross-reference `networkSourceId` against `sourceMapping` to identify what layer each element belongs to. For full name resolution (asset group/type names), call `network_get_metadata(section="asset_types")` and look up codes.

---

## Phase Bitfield Interpretation

Utility networks encode phase information as a bitmask in the "Phases Current" network attribute.

### Encoding

| Phase | Bit Value | Binary |
|-------|-----------|--------|
| A | 4 | 100 |
| B | 2 | 010 |
| C | 1 | 001 |

### Combinations

| Value | Phases | Binary |
|-------|--------|--------|
| 7 | ABC | 111 |
| 6 | AB | 110 |
| 5 | AC | 101 |
| 4 | A | 100 |
| 3 | BC | 011 |
| 2 | B | 010 |
| 1 | C | 001 |
| 0 | None/Unknown | 000 |

### Usage

- Phase values appear in `globalFunctionResults` (e.g., phase propagation results) and in propagated attributes on elements
- Always convert numeric phase values to letter notation when explaining to users: report "ABC" not "7", "AB" not "6"
- The network attribute is typically named "Phases Current" — verify via `network_get_metadata(section="network_attributes")` if unsure
- Phase bitmasks use bitwise AND to determine commonality: two elements share a phase if `(phase_a & phase_b) != 0`

---

## Subnetwork Controller Significance

Controllers are the source/feeder devices for a subnetwork — typically circuit breakers at substations or fuse cutouts at distribution feeders.

### Role in Traces

- **Downstream traces**: The controller is the root. All returned elements are downstream of the controller.
- **Isolation traces**: Controllers define the boundary of the isolation zone. The trace stops at (or includes) the controller.
- **Named trace functions**: Often aggregate values UP to the controller (e.g., "total load served by this feeder").

### Identifying Controllers in Results

- Controllers appear as element entries with their own `globalId`
- In enriched results, look for elements where the `assetGroupName` or `assetTypeName` indicates a breaker, recloser, or feeder device
- Use `network_get_metadata(section="categories")` to check for a "Subnetwork Controller" category if you need to programmatically identify them
- The controller's GlobalID identifies which feeder/circuit an element belongs to

### Practical Interpretation

When explaining results:
- "This downstream trace starts from circuit breaker [name] at [substation] and serves X customers on feeder [subnetwork name]"
- "The isolation zone is bounded by [controller name] — everything between the fault and the controller must be de-energized"

---

## Tier Context in Results

Trace result elements do NOT directly carry tier information. Tier must be inferred.

### How to Determine Tier

1. **From the starting point**: Use `network_device_terminals` before tracing — it returns `featureTierNames` and `featureTierRanks`
2. **From the named trace**: Named traces are typically tier-scoped (e.g., "Electric Distribution" tier). Check the trace configuration's description.
3. **From subnetwork names**: The starting feature's `subnetworkNames` combined with the domain's `tiers` catalog reveals tier membership.

### Tier Behavior During Tracing

- A distribution trace stays within the distribution tier unless it crosses a tier boundary device (e.g., a station transformer connecting distribution to transmission)
- Results from a distribution trace contain only distribution-tier elements
- If results seem incomplete, verify:
  - The starting point is on the correct tier for the intended trace
  - The starting point isn't on a higher tier (transmission) when distribution results are expected
  - The named trace is scoped to the correct tier

### Reporting Tier Context

Always include tier context in explanations:
- "On the Electric Distribution tier, starting from transformer T-1234..."
- "This feeder (Medium Voltage Distribution) serves..."

---

## Plain-Language Explanation Patterns

When explaining trace results to users, follow these patterns:

### Summary Lead

Always lead with the answer to the user's question, then provide detail:

- "The trace found **42 elements** across 3 sources (18 devices, 22 conductors, 2 junctions)."
- "Starting from transformer T-1234 at Oak Street Substation, the downstream network serves **156 service points**."
- "The total connected load downstream is **847.3 kW** across 156 customers (from the named trace function results)."
- "To isolate this element, **3 devices** must be operated: recloser R-101, switch SW-205, and fuse F-44."

### Impact Reporting

- "The impact area contains **12 devices**; downstream from those, **89 additional service points** are affected."
- "Inside the construction zone: 4 poles, 2 transformers. Total downstream impact: 34 customers."

### Function Result Reporting

- "Connected load: 847.3 kW (Sum of 'Service Load' attribute)"
- "Customer count: 156 (Count of service point elements)"
- "Phases served: ABC (bitwise OR of 'Phases Current')"

### Formatting Rules

- Round load values to nearest 0.1 kW (or 0.01 MW for large values)
- Report counts as integers
- Convert phase bitmasks to letters (7 → "ABC", 4 → "A")
- Use device type names from enriched results, not raw codes
- Group elements by source/type for readability when there are many results

---

## Identifying Unexpected Results

### Empty Trace (0 Elements)

Possible causes and actions:

| Cause | How to Check | Fix |
|-------|-------------|-----|
| Missing `terminal_id` on multi-terminal device | Call `network_device_terminals` — if `terminalCount > 1`, terminal is required | Re-run trace with correct `terminal_id` based on trace direction |
| Wrong tier | Check `featureTierNames` from `network_device_terminals` | Start from a feature on the correct tier |
| Stale network topology | The trace tools auto-retry once after topology validation | If still empty, report that topology may need validation in ArcGIS Pro |
| Isolated/de-energized section | The feature is on an un-energized part of the network | Inform user — the element may not have a connected path to a source |
| Invalid GlobalID | The ID doesn't exist in the utility network | Verify the GlobalID belongs to a network-participating feature |

### Unexpectedly Large Trace (Thousands of Elements)

| Cause | How to Check | Fix |
|-------|-------------|-----|
| Started from high-voltage/transmission device | Check tier rank — high rank = higher voltage | Re-start from a distribution-tier device |
| No barriers configured | Direct traces don't include barriers | Use a named trace with appropriate barriers |
| Started from a subnetwork controller | Controllers are the root — downstream includes entire feeder | Confirm this is what the user intended; if not, start from a more specific downstream device |

When results are very large:
- Summarize by source type and asset group (counts per category)
- Highlight the most relevant subset (e.g., service points for customer impact)
- Offer to narrow the scope ("Would you like me to trace from a specific device further downstream?")

### Missing Expected Elements

| Cause | How to Check | Fix |
|-------|-------------|-----|
| Normally-open device (tie switch) | These are natural trace boundaries | Explain to user that the network is configured to stop at this point |
| Named trace barrier | The named trace has barriers configured | This is expected behavior — the trace is bounded correctly |
| Phase mismatch | Element is on a different phase than the trace | Check phase attributes; inform user of the phase boundary |
| Different subnetwork | Element belongs to another feeder | Verify subnetwork membership; may need to trace from a different starting point |

### Error: "No Starting Points Found"

| Cause | How to Check | Fix |
|-------|-------------|-----|
| Stale topology | Tools auto-retry once after validation | If persists, report that topology needs validation |
| Non-network feature | The GlobalID is in a non-participating layer | Verify the feature is in a utility-network-enabled layer |
| Incorrect terminal ID | Terminal doesn't exist for the feature | Call `network_device_terminals` to get valid terminal IDs |
| Disabled feature | The feature may be marked as disabled in the network | Check feature status attributes |

### General Troubleshooting Sequence

1. Call `network_device_terminals` with the GlobalID to confirm it's a valid network feature
2. Check `terminalCount` — select the correct terminal for the trace direction
3. Verify `featureTierNames` matches the intended tier
4. Try the trace again with confirmed parameters
5. If still empty, try a `connected` trace type to see if the feature has ANY connectivity
6. Report findings to the user with specific diagnostic information
