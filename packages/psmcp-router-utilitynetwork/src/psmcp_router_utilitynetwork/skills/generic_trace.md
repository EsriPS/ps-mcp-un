---
name: generic-trace
description: Run any utility-network trace with network_generic_trace. Lists, for every trace type, the mandatory and optional parameters and the tools to call first to obtain each value.
tags:
  - agent-runtime
---
# Generic Trace Workflow

You are running an ad-hoc trace with `network_generic_trace`, which sends a full `UtilityNetworkServer/trace` request. A trace that is missing a required input fails or returns nothing useful, so gather every required value **before** calling the tool. This guide tells you, for each trace type, what is mandatory, what is optional, and which tool provides each value.

Sources: Esri REST `trace` operation, ArcGIS Pro "Utility network trace types" and "Configure a trace", and the ArcGIS API for Python trace configuration reference.

## 0. Choose the Right Tool

| Situation | Tool |
|-----------|------|
| A saved (named) trace matches the request | `network_named_trace` (see `utility_network_named_trace_execution`). Preferred, because engineers encode barriers, functions and filters in it. |
| Plain downstream or upstream from one feature, nothing custom | `network_downstream_trace` / `network_upstream_trace` |
| Anything else: several starting points, barriers, stopping points, custom configuration, other result types, path, circuit, loops, subnetwork by name | `network_generic_trace` (this guide) |

## 1. Pre-flight Checklist (every trace)

Do these in order. Skip a step only if you already hold its result in this session.

| # | Step | Tool | Gives you |
|---|------|------|-----------|
| 1 | Initialize | `network_initialize_session()` once per session | Data model guidance |
| 2 | Check for a saved trace | `network_list_named_traces()` | A named trace to use instead (go to section 0) |
| 3 | Resolve each feature to a GlobalID | The user's GlobalID, or `utility_network_address_resolution` for an address, or `query_feature_layer` (by OBJECTID / ASSETID / name) | `global_id` for every location |
| 4 | Find the terminal of each junction | `network_device_terminals(global_id=...)` | `terminalId`, `terminalName`, `recommendedFor` |
| 5 | Find the tier and domain network | `network_get_metadata(section="domain_networks")` | `domainNetworkName`, tier `name`, `rank`, `tierDefinition` (partitioned or hierarchical), `subnetworkTableName` |
| 6 | Find names used in conditions | `network_get_metadata(section="network_attributes")` and `section="categories"` | Valid network attribute and category names for barriers, functions and filters |
| 7 | Find asset codes for output filters | `network_get_metadata(section="asset_types")` | `networkSourceId`, `assetGroupCode`, `assetTypeCode` |

Rules for step 3 and 4:
- An **edge** (line, edge object) needs `percent_along` between 0.0 and 1.0. If the user gives no position along the line, use `0.5` and say so in the answer.
- A **junction** (device, junction, junction object): choose the terminal by `terminalCount` from `network_device_terminals`:

| `terminalCount` | Terminal to use | Direction check |
|-----------------|-----------------|-----------------|
| 0 | Omit `terminal_id` | None |
| 1 | That terminal's `terminalId`, for **every** trace type (upstream, downstream, isolation, ...) | **None.** `recommendedFor` is `"any"`. A lone terminal is the only way into the feature, so it is always the correct start. Do not mention its direction or report it as a caveat |
| 2 or more | `recommendedFor == "downstream"` for downstream traces; `recommendedFor == "upstream"` for upstream and isolation traces | If more than one terminal fits, or none is marked, **ask the user**. Never guess on a multi-terminal device |

Single-terminal features include service points, meters, line ends, junctions and most connection points. Multi-terminal features are typically transformers, switches, fuses, breakers and reclosers.
- A location missing a required property (terminal for a junction, percent for an edge) is silently ignored by the server, which can produce "no starting points".

## 2. Parameter Reference for `network_generic_trace`

| Parameter | Type | Meaning | How to obtain |
|-----------|------|---------|---------------|
| `trace_type` | string, **always required** | `connected`, `subnetwork`, `subnetworkController`, `upstream`, `downstream`, `isolation`, `loops`, `path`, `circuit`, `shortestPath` (deprecated) | From the user's question, section 3 |
| `starting_points` | list of locations | Where the trace begins | Steps 3 and 4 |
| `barriers` | list of locations | Features that stop the trace. A barrier with `is_filter_barrier: true` is a filter barrier | Steps 3 and 4 |
| `stopping_points` | list of locations | End of a path. **`path` only** | Steps 3 and 4 |
| `trace_configuration` | object | Full REST `traceConfiguration`. **Replaces** the tier defaults | Section 5 |
| `configuration_overrides` | object | Keys merged **on top of** the tier defaults (or on top of `trace_configuration`) | Section 5 |
| `result_types` | list | What to return. Default `["elements"]` | Section 6 |
| `domain_network_name` | string | Domain network to trace | Step 5 |
| `tier_name` | string | Tier to trace. Required to disambiguate a feature that is in several tiers | Step 5 |
| `target_tier_name` | string | Tier where an upstream/downstream trace ends (multi-tier traces) | Step 5 |
| `subnetwork_name` | string | Subnetwork to trace by name | Query the subnetwork table (section 3.2) |
| `use_tier_defaults` | bool, default true | Use the tier's subnetwork definition as the configuration | Leave true unless the user wants an unscoped trace |
| `moment` | int | Epoch milliseconds, to trace the network as of a past time | User |
| `out_sr` | int | Output spatial reference wkid | User |
| `max_elements` | int or null, default 500 | Cap on returned `elements` | Raise only if the user needs the full list |
| `summarize` | bool | Add counts grouped by source and asset group | Use for large traces |

Location shape: `{"global_id": "{GUID}", "terminal_id": 3, "percent_along": 0.5, "is_filter_barrier": false}`. Only `global_id` is always needed.

### How the tool builds the configuration

For `upstream`, `downstream`, `isolation`, `subnetwork` and `subnetworkController`, when you pass **no** `trace_configuration` and `use_tier_defaults` is true, the tool loads the tier's subnetwork definition (its condition barriers, inclusion flags and propagators). The tier comes from the first starting point's actual subnetwork membership, or from `domain_network_name` + `tier_name` when there are no starting points. Then `domain_network_name`, `tier_name`, `target_tier_name`, `subnetwork_name` are filled in if the configuration does not already set them, and finally `configuration_overrides` is applied.

- To **change a few settings**, use `configuration_overrides`. This keeps the tier's barriers that stop the trace at subnetwork controllers.
- To **replace everything**, use `trace_configuration`. You then own every barrier. Do this only when the user supplied a full configuration.
- `connected`, `loops`, `path`, `circuit`, `shortestPath` never get tier defaults. They run on connectivity alone unless you configure them.

## 3. Trace Types: Mandatory and Optional Inputs

Summary matrix. M = mandatory, O = optional, X = not used or rejected.

| Trace type | Starting points | Barriers | Stopping points | Domain network + tier | Other mandatory | Server version |
|------------|-----------------|----------|-----------------|-----------------------|-----------------|------------|
| `connected` | M (1+) | O | X | O | none | any |
| `subnetwork` | M (1+) **or** `subnetwork_name` | O | X | M (derived or supplied) | none | any |
| `subnetworkController` | M (1+) **or** `subnetwork_name` | O | X | M (derived or supplied) | none | any |
| `upstream` | M (1+) | O | X | M (derived or supplied) | none | any |
| `downstream` | M (1+) | O | X | M (derived or supplied) | none | any |
| `isolation` | M (1+) | O | X | M (derived or supplied) | A **filter barrier** | 10.7 or later |
| `loops` | M (exactly 1) | O | X | O | none | any |
| `path` | M (1+) | O | M for traditional domains, O for telecom | O | none | 12.1 or later |
| `circuit` | M (1+) **or** `trace_configuration.circuitName` | O | X | M (telecom domain) | Telecom domain network | 12.1 or later |
| `shortestPath` (deprecated) | M (2) | O | X | O | `shortestPathNetworkAttributeName` | any (deprecated 12.1) |

"Derived" means the tool works the tier out from the starting point's subnetwork membership. Supply `tier_name` only when the tool reports it is ambiguous, or when you have no starting point.

Subnetwork-based traces (subnetwork, subnetworkController, upstream, downstream, isolation) need the network topology validated and the subnetworks updated. A dirty area or dirty subnetwork makes them fail or return stale results.

### 3.1 `connected`

Purpose: everything physically connected to the starting points, in all directions, until a barrier or the end of the network. Use it to check that newly edited features connect as expected. It ignores the subnetwork definition, terminal direction and valid paths (it is subject to terminal paths only).

| | |
|-|-|
| Mandatory | `starting_points` (1 or more) |
| Optional | `barriers`; `trace_configuration` or `configuration_overrides` (traversability, `includeContainers`, `includeContent`, `includeStructures`, `functions`, `outputConditions`, `outputFilters`); `domain_network_name`, `tier_name`; `result_types` |
| Not needed | Subnetwork controllers |

Prerequisites: step 3 (GlobalID), step 4 (terminal for each junction, or an edge `percent_along`).

Warning: with no barriers or conditions a connected trace can cover the whole network and return a very large result. Add a barrier, a condition barrier, or `summarize=true` with a small `max_elements`.

```
network_generic_trace(trace_type="connected",
  starting_points=[{"global_id": "{G}", "terminal_id": 1}],
  summarize=true, max_elements=100)
```

### 3.2 `subnetwork`

Purpose: all features that belong to a subnetwork (a feeder, circuit or zone), from a starting point, or from the controller(s) of a named subnetwork. Use it to validate that a subnetwork is defined correctly or to list its members.

| | |
|-|-|
| Mandatory | `starting_points` **or** `subnetwork_name` (when `subnetwork_name` is given the starting points are ignored and the controllers are used) |
| Mandatory (resolved for you) | Domain network and tier. With a starting point the tool derives them. With `subnetwork_name` only, **you must pass `domain_network_name` and `tier_name`** so the tier definition can be loaded |
| Optional | `barriers`; `configuration_overrides` (for example stop at certain devices with `conditionBarriers`); `result_types` |

Prerequisites:
1. `network_get_metadata(section="domain_networks")` for the domain network and tier names, and `subnetworkTableName`.
2. To find a subnetwork name, query the subnetwork table with `query_feature_layer`. Use `get_service_or_layer_details` first to find the table's layer ID. Read the `SUBNETWORKNAME`, `TIERNAME` and dirty-status fields. Match the user's wording to `SUBNETWORKNAME` and take its `TIERNAME` for `tier_name`.
3. If the subnetwork is dirty, tell the user: results may be stale until the subnetwork is updated.

```
network_generic_trace(trace_type="subnetwork",
  subnetwork_name="RMT001",
  domain_network_name="ElectricDistribution", tier_name="Medium Voltage Radial",
  result_types=["elements"], summarize=true)
```

If no output filter is set, the subnetwork's own line feature is also part of the result.

### 3.3 `subnetworkController`

Purpose: find the controller devices (sources or sinks, such as circuit breakers) of a subnetwork, including boundary devices such as tie switches.

| | |
|-|-|
| Mandatory | `starting_points` **or** `subnetwork_name` |
| Mandatory (resolved for you) | Domain network and tier (same rules as `subnetwork`) |
| Optional | `barriers`, `configuration_overrides`, `result_types` |

Prerequisites: same as 3.2. Trace direction through terminals matters, so use the correct terminal (step 4) for the starting point.

### 3.4 `downstream`

Purpose: features between the starting points and the end of the flow, away from the subnetwork controller in a source-based network. The direction is worked out at trace time from the subnetwork controllers.

| | |
|-|-|
| Mandatory | `starting_points` (1 or more), with the **downstream** terminal on multi-terminal devices |
| Mandatory (resolved for you) | Domain network, tier. Needs the start feature to belong to a built subnetwork |
| Optional | `barriers`; `target_tier_name` (continue into a lower tier); `configuration_overrides` (for example `includeBarriers`, `outputConditions` to return only protective devices, `functions` for load sums); `result_types`; `moment` |

Prerequisites:
1. `network_device_terminals`. With one terminal, use it (`recommendedFor` is `"any"`). With 2 or more, pick `recommendedFor == "downstream"`.
2. If the result is `status: "tier_ambiguous"` (the feature is in several tiers, for example in a hierarchical domain): ask the user which tier, then call again with `tier_name`. See section 7.
3. If the result is `status: "tier_no_membership"`: the feature is in no built subnetwork. Tell the user. Do not retry blindly.

Alternative: `use_digitized_direction` in `configuration_overrides` (`{"useDigitizedDirection": true}`) determines flow from the line's digitized direction instead of controllers. Then the domain network, tier and target tier are ignored and propagators are ignored. Use it only when the network models flow by digitized direction. It is the only way to run a directional trace on a telecom domain network.

```
network_generic_trace(trace_type="downstream",
  starting_points=[{"global_id": "{G}", "terminal_id": 2}],
  barriers=[{"global_id": "{B}", "terminal_id": 1}],
  result_types=["elements"], summarize=true)
```

### 3.5 `upstream`

Purpose: features between the starting points and the subnetwork controller(s), toward the source in a source-based network.

| | |
|-|-|
| Mandatory | `starting_points` (1 or more), with the **upstream** terminal on multi-terminal devices |
| Mandatory (resolved for you) | Domain network, tier |
| Optional | Same as `downstream`. `ignoreBarriersAtStartingPoints` is useful when you use discovered protective devices as the starting points of the next upstream trace |

Prerequisites: same as `downstream`, but on a multi-terminal device pick `recommendedFor == "upstream"`. A single-terminal feature (for example a service point or meter) is traced upstream from its only terminal; this is correct and needs no caveat.

To return only upstream protective devices, add an output condition for the protective category: first run `network_get_metadata(section="categories")` to find the category name, then pass it in `configuration_overrides.outputConditions` (section 5).

### 3.6 `isolation`

Purpose: the minimum set of operable devices (valves, switches) that must be operated to isolate the starting points from the resource. Use for "what do I close to isolate this leak or fault".

| | |
|-|-|
| Mandatory | `starting_points` (1 or more), with the **upstream** terminal on multi-terminal devices |
| Mandatory | A **filter barrier** that identifies isolating devices. Without it the tool returns `{"error": ...}` and does not call the server |
| Mandatory (resolved for you) | Domain network, tier |
| Optional | `barriers`; `includeIsolated: true` (also return every isolated feature, not only the isolating devices); `includeBarriers`; `outputConditions` / `outputFilters` to narrow the isolating types (for example only accessible valves) |

Terminal: with one terminal use it; with 2 or more use `recommendedFor == "upstream"` (see section 1).

Where the filter barrier comes from, in order:
1. `network_get_metadata(section="categories")`. Look for a category such as "Isolating" or "Protective" (the name is user-defined, so use the exact name returned).
2. Pass it as `configuration_overrides={"filterBarriers": [ ... ]}` (shape in section 5), or mark a barrier location with `is_filter_barrier: true`.
3. If no isolating category exists, use `network_get_metadata(section="asset_types")` to find the device sources and ask the user which asset types isolate. Do not invent a category name.

After the trace, remove the starting feature from the list. See `utility_network_isolation_analysis` for the full workflow that also names the devices.

```
network_generic_trace(trace_type="isolation",
  starting_points=[{"global_id": "{G}", "terminal_id": 1}],
  configuration_overrides={"filterBarriers": [
    {"name": "Isolating", "type": "category", "operator": "equal", "value": "1",
     "combineUsingOr": false, "isSpecificValue": true}]},
  result_types=["elements"])
```

Confirm the exact condition shape with the server's response: if it rejects the category condition, report the server error to the user instead of guessing new shapes.

### 3.7 `loops`

Purpose: find features that take part in loops (areas where flow direction is ambiguous). Loops are expected in mesh networks and usually indicate errors in radial ones.

| | |
|-|-|
| Mandatory | `starting_points` with **exactly one** entry. The tool rejects more than one |
| Optional | `barriers`; `configuration_overrides` such as a condition barrier for one phase, or `filterBitsetNetworkAttributeName` to return only loops that keep the same bit set (for example the same phase) all the way around; `domain_network_name`, `tier_name` |

Prerequisites: step 3 and 4 for the single start. The trace is connectivity-based and does not use tier defaults.

### 3.8 `path`

Purpose: valid paths between a start location and a stop location. With `numPaths` of 1 and a cost attribute it returns the shortest path. It replaces `shortestPath` from Enterprise 12.1.

| | |
|-|-|
| Mandatory | `starting_points` (1 or more) |
| Mandatory for a traditional domain network | `stopping_points` (1 or more). Telecom domain networks may omit them. Without stopping points the tool still runs and adds a warning |
| Optional | `barriers`; `trace_configuration.shortestPathNetworkAttributeName` (numeric cost attribute such as `Shape length`; without it every edge costs 1); `numPaths` (default 1; paths returned = starts x stops x numPaths); `maxHops` (default 100; a terminal device counts 2); `includeBarriers` (set true if a stopping point sits on a barrier); `inferConnectivity` (telecom only); `result_types` |

Prerequisites:
1. Resolve both ends to GlobalIDs and terminals (steps 3 and 4).
2. `network_get_metadata(section="network_attributes")` to confirm the cost attribute name before using it.
3. Because path traces do not use tier defaults, put these keys in `configuration_overrides` (or `trace_configuration`). The key names `numPaths`, `maxHops` and `inferConnectivity` follow the Pro tool parameters. If the server rejects one, report the server message.
4. The server must be ArcGIS Enterprise 12.1 or later. On older servers use `shortestPath`.

The returned paths are not ordered. When `numPaths` is above 1 only the first is guaranteed to be the shortest.

```
network_generic_trace(trace_type="path",
  starting_points=[{"global_id": "{A}", "terminal_id": 1}],
  stopping_points=[{"global_id": "{Z}", "terminal_id": 1}],
  configuration_overrides={"shortestPathNetworkAttributeName": "Shape length", "numPaths": 1},
  result_types=["elements", "connectivity"])
```

### 3.9 `circuit`

Purpose: the elements of a circuit in a **telecom** domain network, using the circuit management tables as well as connectivity.

| | |
|-|-|
| Mandatory | `starting_points` (1 or more) **or** `trace_configuration.circuitName` (the circuit's own start is used and starting points are ignored) |
| Mandatory | `domain_network_name` (the telecom domain network) |
| Optional | `barriers` (constrain the path); `maxHops`; `includeContainers` and `synthesizeGeometries` (draw non-spatial objects); `result_types` including `circuits` (the circuit definition) |

Prerequisites: `network_get_metadata(section="domain_networks")` to confirm a telecom domain exists. This trace needs Enterprise 12.1 or later. If the network has no telecom domain, tell the user a circuit trace does not apply. The `circuitName` key is read from the trace configuration: pass it in `trace_configuration`, not as a separate argument. Because `trace_configuration` replaces defaults, include `domainNetworkName` there too.

### 3.10 `shortestPath` (deprecated)

Deprecated from Enterprise 12.1 and Pro 3.7. It still works until the next major release. Prefer `path` when the server is 12.1 or later.

| | |
|-|-|
| Mandatory | `starting_points` with **two** entries (the two ends of the path) |
| Mandatory | `shortestPathNetworkAttributeName` in the configuration (numeric attribute) |
| Optional | `barriers`, traversability settings, `result_types` |

The response carries a `warnings` entry about the deprecation.

## 4. Decision Table: User Question to Trace

| User asks | Trace type | Starting points | Extra |
|-----------|-----------|-----------------|-------|
| "What is connected to this?" | `connected` | the feature | barriers or a limit |
| "What does this feeder / circuit contain?" | `subnetwork` | controller, or `subnetwork_name` | domain + tier for a name |
| "Which breaker feeds this?" / "Find the source" | `upstream`, or `subnetworkController` | the feature (upstream terminal) | |
| "What loses power if this fails?" | `downstream` | the feature (downstream terminal) | barriers for open devices |
| "What do I operate to isolate this?" | `isolation` | the feature (upstream terminal) | filter barrier, category from metadata |
| "Are there loops here?" | `loops` | one feature | optional phase filter |
| "Route / shortest way from A to B" | `path` (or `shortestPath` on old servers) | A | B as stopping point, cost attribute |
| "Show the circuit" (telecom) | `circuit` | start or circuit name | telecom domain |
| "Total load / customer count downstream" | `downstream` with `functions` | the feature | `globalFunctionResults` in the response |

## 5. Trace Configuration Reference

Pass these as `trace_configuration` (replaces defaults) or `configuration_overrides` (merged over the tier defaults). Use the camelCase names below. Validate every attribute and category name against `network_get_metadata` first. Never invent names.

| Key | Type | Purpose | Default |
|-----|------|---------|---------|
| `domainNetworkName`, `tierName` | string | Scope the trace to a tier | from tool |
| `targetTierName` | string | End tier of an upstream/downstream trace across tiers | none |
| `subnetworkName` | string | Subnetwork to trace by name | none |
| `includeContainers` | bool | Return containers of traced content | false |
| `includeUpToFirstSpatialContainer` | bool | With `includeContainers`, stop at the first spatial container | false |
| `includeContent` | bool | Return the content of traced containers | false |
| `includeStructures` | bool | Return structures of traced attachments | false |
| `includeBarriers` | bool | Return the barrier features themselves | true |
| `includeIsolated` | bool | Isolation: also return all isolated features | false |
| `ignoreBarriersAtStartingPoints` | bool | Do not stop at a barrier located on a starting point | false |
| `allowIndeterminateFlow` | bool | Upstream, downstream, isolation: keep features whose flow is indeterminate | true |
| `useDigitizedDirection` | bool | Directional traces use digitized direction instead of controllers | false |
| `validateConsistency` | bool | Fail if dirty areas are in the result | check server default |
| `validateLocatability` | bool | Fail if non-spatial objects cannot be located | false |
| `synthesizeGeometries` | bool | Infer geometry for edge objects and associations (aggregated geometry and circuits) | false |
| `traversabilityScope` | `junctionsAndEdges` / `junctions` / `edges` | Where condition and function barriers apply | `junctionsAndEdges` |
| `filterScope` | same values | Where filter barriers apply | `junctionsAndEdges` |
| `conditionBarriers` | list | Stop where a network attribute or category condition is true | none |
| `functionBarriers` | list | Stop when a running calculation meets a condition | none |
| `arcadeExpressionBarrier` | string | Arcade expression that stops traversal | none |
| `filterBarriers` | list | Isolation: identify isolating features | none |
| `filterFunctionBarriers` | list | Filter barriers driven by a function | none |
| `functions` | list | Calculations over traced features | none |
| `outputFilters` | list | Return only these asset types | none |
| `outputConditions` | list | Return only features that meet a condition | none |
| `propagators` | list | Propagate values (for example phases) along the trace | tier's |
| `shortestPathNetworkAttributeName` | string | Cost attribute for `path` / `shortestPath` | none |
| `filterBitsetNetworkAttributeName` | string | Loops, upstream, downstream: keep results that share the bits set in the start | none |
| `nearestNeighbor` | object | Return the N nearest assets by cost: `count`, `costNetworkAttributeName`, `nearestCategories`, `nearestAssets` | none |
| `numPaths`, `maxHops`, `inferConnectivity` | number / number / bool | `path` options (names follow the Pro tool parameters) | 1 / 100 / false |

Condition object (used by `conditionBarriers`, `filterBarriers`, `outputConditions`, and inside `functions[].conditions`):

```json
{"name": "Device Status", "type": "networkAttribute", "operator": "equal",
 "value": "1", "combineUsingOr": false, "isSpecificValue": true}
```

- `type`: `networkAttribute` or `category`.
- `operator`: `equal`, `notEqual`, `greaterThan`, `greaterThanEqual`, `lessThan`, `lessThanEqual`, `includesTheValues`, `doesNotIncludeTheValues`, `includesAny`, `doesNotIncludeAny`. The last four are bitwise and are for phase-style attributes.
- `isSpecificValue: true` compares to `value`. `false` compares to another network attribute.
- `combineUsingOr` joins this condition to the next with OR instead of AND.
- `value`: use the **coded value** from the attribute's domain, not the description. Look the domain up with `network_get_metadata(section="network_attributes")` and `network_resolve_coded_values`.

Function object:

```json
{"functionType": "add", "networkAttributeName": "Load", "conditions": []}
```

`functionType` is one of `add`, `subtract`, `average`, `count`, `min`, `max`. Results come back as `globalFunctionResults` in the response. Request them by including functions in the configuration and `elements` in `result_types`.

Phase bitfield: A is 4, B is 2, C is 1, so ABC is 7, AB is 6, AC is 5, BC is 3. To keep only features that include phase A use `includesAny` (or `doesNotIncludeAny` as a filter barrier with `includeBarriers: false`) with value `4`.

Output filter object: `{"networkSourceId": 9, "assetGroupCode": 7, "assetTypeCode": 1}`. Get the codes from `network_get_metadata(section="asset_types")`.

Common recipes (put in `configuration_overrides`):

| Goal | Override |
|------|----------|
| Stop at open devices | `{"conditionBarriers": [{"name": "<status attribute>", "type": "networkAttribute", "operator": "equal", "value": "<open code>", "combineUsingOr": false, "isSpecificValue": true}]}` |
| Include containers and their content | `{"includeContainers": true, "includeContent": true}` |
| Total of an attribute over the trace | `{"functions": [{"functionType": "add", "networkAttributeName": "<attribute>", "conditions": []}]}` |
| Only return transformers | `{"outputFilters": [{"networkSourceId": <id>, "assetGroupCode": <code>, "assetTypeCode": <code>}]}` |
| Downstream to the next tier | `{"targetTierName": "<lower tier>"}` (or the `target_tier_name` argument) |
| Next upstream protective device | start from the previous device and set `{"ignoreBarriersAtStartingPoints": true}` |

## 6. Choosing `result_types`

Default is `["elements"]`. Ask for the least that answers the question.

| Type | Returns | Use for |
|------|---------|---------|
| `elements` | `networkSourceId`, `globalId`, `objectId`, `terminalId`, asset group and type codes (the tool adds `sourceName`, `assetGroupName`, `assetTypeName`) | Counts, lists, device filtering, function results |
| `features` | Feature records with `propagatedValues`, `networkAttributeValues`, geometry, `positionFrom` / `positionTo`, `flowDirection` | Showing features, reading phases |
| `connectivity` | `via`, `from`, `to` records joining features through terminals | Drawing or ordering the topology |
| `aggregatedGeometry` | One merged point, line and polygon geometry for the trace | Highlighting the trace on a map |
| `associations` | Containment and structural-attachment associations in the result | Containers and structures |
| `circuits` | The circuit definition (telecom `circuit` trace) | Circuit reports |

Object form, for options: `{"type": "features", "include_geometry": true, "include_propagated_values": true, "network_attribute_names": ["Is subnetwork controller"]}`. `features`, `connectivity` and `elements` responses contain `sourceMapping` (string `networkSourceId` to source name). The `paths` result type (Enterprise 12.2) is not supported by this tool.

Interpret results with `utility_network_trace_interpretation`. For customer counts and totals over large traces, prefer `functions` and `summarize=true` over listing every element (see `large_result_aggregation`).

## 7. Reading the Response

| Response | Meaning | What to do |
|----------|---------|-----------|
| `{"error": "..."}` | The arguments were invalid. Nothing was sent to the server | Read the message, fix the argument, call again. Messages name the missing item (starting point, filter barrier, stopping point rules, result type) |
| `status: "tier_ambiguous"` with `memberTiers` or `configuredTiers` | The start feature fits several tiers. No trace was run | Ask the user which tier. Call again with `tier_name` |
| `status: "tier_no_membership"` | The feature is in no built subnetwork. No trace was run | Tell the user. Offer another start feature, or `connected` if connectivity is what they need |
| `tierResolution.resolvedBy == "configured"` | Tier was inferred from configuration, not membership | Say the result is best-effort |
| `warnings` list | Non-fatal advice (deprecated trace type, path without stopping point) | Pass the substance to the user |
| `traceResults.totalElements`, `truncated`, `note` | The element list was cut at `max_elements` | Say how many exist. Use `summarize` or raise `max_elements` if needed |
| `summary` | Counts by source and asset group | Lead the answer with it for large traces |
| A raised "Trace failed" error | The server rejected the trace | Report the server message. Do not retry with guessed values |
| "Trace spans multiple subnetworks" | The trace was not scoped to one tier definition | Pass `tier_name`, or choose a feature that is in one subnetwork |

## 8. Troubleshooting

| Symptom | Likely cause and action |
|---------|-------------------------|
| "No starting points found" | A junction is missing `terminal_id`, an edge is missing `percent_along`, or the topology is dirty. The tool revalidates the topology once and retries. If it persists, re-run `network_device_terminals` |
| Empty `elements` | The start terminal faces away from the flow, a barrier sits on the start (try `ignoreBarriersAtStartingPoints`), or the start is a controller with nothing beyond it |
| Directional trace returns little for a subnetwork controller | Check the terminal with 
etwork_device_terminals and confirm the direction (
ecommendedFor) matches the trace |
| Result is huge | Add barriers or `outputFilters`, drop geometry, use `summarize`, lower `max_elements` |
| Server error about dirty areas | The topology is not validated for the traced area. Report it. Results are not reliable until validated |
| Server error naming an attribute or category | The name does not exist. Re-read `network_get_metadata` |
| `path` or `circuit` rejected | The server is older than 12.1. Use `shortestPath`, or tell the user the trace type is unavailable |

## 9. Rules for the Agent

1. Always call `network_initialize_session` first, and read this guide before the first `network_generic_trace` of a task.
2. Never run a trace until every mandatory input in section 3 for that trace type is known. Ask the user for what you cannot look up.
3. Never guess a terminal, tier, category name, attribute name or coded value. Look them up with the tools in section 1, or ask.
4. Prefer a matching named trace. Prefer `configuration_overrides` over `trace_configuration`.
5. Keep requests small: request only the result types the question needs.
6. State your assumptions in the answer: the terminal chosen on a multi-terminal device, a default `percent_along`, the tier resolved, a truncated list. Do not raise a caveat about the direction of a single terminal (`recommendedFor: "any"`).
7. Report warnings and best-effort resolutions to the user.
