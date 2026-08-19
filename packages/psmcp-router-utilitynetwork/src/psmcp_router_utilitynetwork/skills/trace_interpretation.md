# Utility Network Trace Result Interpretation

This document teaches you how to read and interpret utility network trace results, understand phase encoding, recognize subnetwork controllers, and identify unexpected results.

---

## Trace Result Structure

A trace result contains these primary sections:

### `elements`

The main output — a list of network features the trace traversed or identified:

```json
{
  "networkSourceId": 9,
  "globalId": "{12345678-ABCD-...}",
  "objectId": 42,
  "terminalId": 1,
  "assetGroupCode": 4,
  "assetTypeCode": 2
}
```

After enrichment by workflow tools, elements include resolved names:
- `sourceName` — the layer/source name (e.g., "ElectricDevice")
- `assetGroupName` — human-readable group (e.g., "Distribution Transformer")
- `assetTypeName` — human-readable type (e.g., "Three Phase")

### `sourceMapping`

Maps `networkSourceId` (as string) to layer/source names:

```json
{
  "9": "ElectricDevice",
  "6": "ElectricLine",
  "11": "ElectricJunction"
}
```

Use this to translate element `networkSourceId` values to meaningful layer names when elements are not pre-enriched.

### `globalFunctionResults`

Aggregated computation results from named traces (not available in direct traces):

```json
{
  "functionType": "Sum",
  "networkAttributeName": "ServiceLoad",
  "result": 1250.5,
  "conditions": []
}
```

Common function types:
- **Sum** — total of a network attribute across traced elements (e.g., total load)
- **Count** — number of elements matching conditions
- **Min** / **Max** — minimum/maximum attribute value in the trace
- **Average** — mean attribute value

### `warnings`

Server-side warnings about the trace execution. Empty when none. May contain messages about dirty areas, topology validation, or trace limitations.

---

## Phase Bitfield Interpretation

Utility network phases are encoded as a bitfield integer:

| Bit | Phase | Value |
|-----|-------|-------|
| Bit 2 | A | 4 |
| Bit 1 | B | 2 |
| Bit 0 | C | 1 |

### Common Combinations

| Value | Phases | Description |
|-------|--------|-------------|
| 7 | ABC | Three-phase |
| 6 | AB | Two-phase (A and B) |
| 5 | AC | Two-phase (A and C) |
| 4 | A | Single-phase A |
| 3 | BC | Two-phase (B and C) |
| 2 | B | Single-phase B |
| 1 | C | Single-phase C |

### How to Decode

To determine which phases are present, use bitwise AND:

- Phase A present: `value & 4 != 0`
- Phase B present: `value & 2 != 0`
- Phase C present: `value & 1 != 0`

### Where Phases Appear

- Network attribute values on elements (e.g., `phasesNormal`, `phasesCurrent`)
- Named trace function conditions (filtering by phase)
- Propagator configurations (phase propagation rules)

### Phase in Plain Language

When reporting phases to users, translate the bitfield:
- "This transformer serves phases A and B (value 6)"
- "The conductor carries all three phases (ABC, value 7)"
- "Single-phase C service (value 1)"

---

## Subnetwork Controller Significance

### What is a Subnetwork Controller?

A subnetwork controller is the "source" device that feeds a subnetwork. For electric networks, this is typically:
- A circuit breaker at a substation (for distribution)
- A transmission switch or breaker (for transmission)

### Identifying Controllers in Results

Controllers appear in trace results as elements with special significance:
- They define the boundary of a subnetwork
- Downstream traces originate FROM a controller
- Upstream traces terminate AT a controller
- Isolation traces identify devices between the target and the controller

### Controller Information

The `network_device_terminals` tool returns `subnetworkNames` which links a feature to its subnetwork. The controller for that subnetwork can be found via:

```
network_trace(starting_global_id="...", trace_type="subnetworkController")
```

### Why Controllers Matter

- They represent the feeding source for a subnetwork
- Isolation analysis finds devices between the target and the controller
- Load calculations sum everything downstream from the controller
- Outage analysis: if a controller trips, everything downstream is affected

---

## Tier Context in Results

### What Tier Tells You

The tier indicates the voltage/pressure level and hierarchy position:
- **Higher tier** (higher rank) = closer to generation/source
- **Lower tier** (lower rank) = closer to customer/load

### Tier in Trace Interpretation

- A downstream trace on a **distribution** tier shows the path from a device to customers
- A downstream trace on a **transmission** tier shows the path to distribution substations
- An isolation trace may cross tier boundaries (e.g., tracing from distribution up to transmission)

### Multi-Tier Results

When trace results span multiple tiers:
- Group results by tier for clearer reporting
- Explain the tier transition to the user
- Higher-tier elements typically represent bulk infrastructure
- Lower-tier elements are closer to end customers

---

## Identifying Unexpected Results

### Empty Results

Possible causes:
- **Invalid GlobalID:** The feature doesn't exist in the network
- **Disconnected feature:** The feature isn't connected to the network topology
- **Dirty areas:** Network topology needs rebuilding (check warnings)
- **Wrong terminal:** Tracing from the wrong terminal may yield no results
- **Tier mismatch:** The feature isn't on the specified tier

Action: Verify the GlobalID, check topology status, try the other terminal.

### Results Too Large

Possible causes:
- **Starting too high in the hierarchy:** Tracing from a controller or high-tier device
- **No barriers in a direct trace:** Named traces have barriers; direct traces don't
- **Broad subnetwork:** Some subnetworks feed thousands of elements

Action: Use a named trace (which has barriers), or scope to a more specific starting point.

### Missing Expected Elements

Possible causes:
- **Barriers in named trace:** The named trace may have barriers that stop traversal
- **Phase mismatch:** The element is on a different phase than the trace follows
- **Normally-open devices:** Open devices block trace traversal
- **Topology errors:** Missing connectivity in the network model

Action: Check if a named trace's barriers are filtering results. Verify connectivity via `network_query_associations`.

### Duplicate Elements

Elements may appear with different terminal IDs if the trace passes through a device's multiple terminals. This is normal for multi-terminal devices. Group by GlobalID for unique feature counts.

---

## Reading Named Trace Function Results

Named traces can include function computations. Interpret them as follows:

### Load Functions

```json
{"functionType": "Sum", "networkAttributeName": "ServiceLoad", "result": 1250.5}
```
→ "Total connected load downstream: 1,250.5 kW"

### Count Functions

```json
{"functionType": "Count", "networkAttributeName": "ObjectId", "result": 47}
```
→ "47 elements found in the trace"

### Conditional Functions

```json
{
  "functionType": "Count",
  "networkAttributeName": "ObjectId",
  "result": 12,
  "conditions": [{"name": "Category", "value": "ServicePoint"}]
}
```
→ "12 service points found downstream"

### Multiple Functions

Named traces often return multiple function results. Present them together:
> "Trace results summary:
> - Total load: 1,250.5 kW (Sum of ServiceLoad)
> - Transformer count: 8 (Count with transformer condition)
> - Service point count: 47 (Count with ServicePoint category)"
