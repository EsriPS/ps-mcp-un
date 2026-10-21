---
name: trace-result-map-layer-mapping
description: Map utility-network trace result sources to active web map layers and subtype children for reliable highlighting.
tags:
  - agent-runtime
---

# Trace Result to Map Layer Mapping

Use this workflow after a utility-network trace when results should be shown on the active browser map.

## The Identifiers Are Different

Do not assume these identifiers are interchangeable:

| Identifier | Meaning | Use it for |
|---|---|---|
| `networkSourceId` | Utility-network source identifier from a trace result | Resolve the trace source through `sourceMapping` |
| `sourceMapping` value | Utility-network source name, such as `ElectricDevice` | Compare with service and map metadata; names may differ in spacing or wording |
| `serviceLayerId` | Numeric layer ID inside a FeatureServer or MapServer URL | Identify a remote service layer |
| browser `layerId` | Runtime ID of a layer in the active web map | Restrict browser map tools only |
| subtype group | Parent browser layer, such as `Electric Device` | Inspect its child subtype layers |
| subtype child | Queryable `subtype-sublayer` beneath a subtype group | Highlight ObjectIDs when the exact child is known |

Never pass a numeric `serviceLayerId` as a browser `layerId`.

## Preferred Workflow: GlobalIDs

1. Execute the trace or named trace.
2. Preserve every returned `globalId`; group duplicate trace elements by normalized GlobalID for display counts.
3. Call `highlightFeaturesByGlobalIds` once with all unique GlobalIDs. Do not supply a layer restriction unless a prior attempt showed a specific active map layer is needed.
4. Include `targetGlobalId` for the trace starting feature when it is known.
5. Read the response:
   - `matched`: report the highlighted count.
   - `unmatchedGlobalIds`: report that those records are not present in the active web map; do not claim the trace failed.
   - `queryErrors`: report the affected map layer and retry only after correcting the discovered layer target.

GlobalIDs are the safest bridge between a service trace result and a browser map layer because browser and service layer IDs can differ.

## ObjectID Fallback Workflow

Use ObjectIDs only when trace results do not provide GlobalIDs.

1. Read the trace `sourceMapping` and group ObjectIDs by `networkSourceId`.
2. Call `getWebMapInfo` to see the active parent layers and subtype hierarchy.
3. Call `getMapServiceUrls` with no filters. Use it to identify the browser layer, service URL, and numeric `serviceLayerId` for the relevant source.
4. For a subtype group, call `getLayerInfo` on the parent browser `layerId` or exact title. Inspect the returned child subtype layers and their service URLs/IDs.
5. Match the trace source to a map layer using this order:
   - exact service URL and numeric `serviceLayerId`
   - source name after normalizing case, spaces, and punctuation
   - compatible geometry type and known asset-group/subtype metadata
6. Call `highlightFeaturesByGlobalIds` with the ObjectIDs and the exact matched browser subtype-child `layerId` or title.
7. If the mapping is ambiguous, do not guess. Explain which candidate layers were found and ask the user to choose, or return the trace results without a map highlight.

## Subtype Group Rules

- A subtype group is a display parent, not necessarily the queryable feature layer.
- Its subtype children can have their own browser IDs and titles while sharing a service relationship with the parent.
- A visible subtype child may not expose a standalone ArcGIS `LayerView`; this does not prevent point-result overlays.
- For ObjectID highlighting, target the resolved child subtype layer. For GlobalID highlighting, allow the browser highlighter to scan active feature and subtype-child layers first.

## When Results Cannot Be Highlighted

A successful service query or trace can return a valid GlobalID that is absent from the current web map. This means the backend data and visible web-map content are not aligned, or that source layer is not included in the map.

In that case:

1. State that the trace/service result succeeded.
2. State that the result could not be found in the active browser map layers.
3. If the result includes usable coordinates, call `zoomTo` and drop a location pin.
4. Do not retry the same highlight with guessed IDs or unrelated layer titles.

## Example

Trace output:

```json
{
  "networkSourceId": 9,
  "globalId": "{9FCBA909-A718-45F0-ADEE-D8991E1FD0BB}",
  "objectId": 42
}
```

Source mapping:

```json
{ "9": "ElectricDevice" }
```

Correct first action:

```json
{
  "globalIds": ["{9FCBA909-A718-45F0-ADEE-D8991E1FD0BB}"],
  "zoom": true
}
```

Do not use `9`, `42`, or a service-layer number as the browser `layerId`.