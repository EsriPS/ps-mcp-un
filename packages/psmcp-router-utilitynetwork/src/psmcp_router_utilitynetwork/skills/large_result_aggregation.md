---
name: large-result-aggregation
description: Answer utility-network questions over large feature sets with server-side counts and statistics instead of oversized feature queries.
tags:
  - agent-system
---

# Large Result Aggregation Workflow

Use this workflow whenever a question asks for totals, counts, lengths, grouped breakdowns, or a circuit/subnetwork with many features.

## Core Rule

Do not fetch every feature when the user needs an aggregate. Query the ArcGIS feature service for the aggregate first.

Oversized tool results waste tool rounds, hide the relevant values in saved files, and can prevent a complete answer. A result stored under `/large_tool_results/...` is not a reason to retrieve the entire response; change the query to return less data.

## Safe Query Sequence

1. Discover the exact service and layer URL with `getMapServiceUrls` or `get_service_or_layer_details`.
2. Inspect the layer metadata before querying:
   - object ID field
   - subnetwork/circuit field, such as `SUBNETWORKNAME`
   - asset group/type field
   - geometry type
   - length field, such as `Shape__Length`
   - coded-value domains needed to classify groups
3. Run a count-only query before retrieving records:

```json
{
  "where": "SUBNETWORKNAME = 'RMT002'",
  "returnCountOnly": true,
  "returnGeometry": false
}
```

4. For totals, use `query_feature_layer_statistics`; it serializes `outStatistics` correctly and always disables geometry.
5. For category splits, pass `group_by_fields` to `query_feature_layer_statistics` so the service groups server-side.
6. Fetch individual records only when the user explicitly asks for a list, or when the service does not support statistics. Then page with a small `resultRecordCount` and `resultOffset` and request only needed fields.

## Statistics Pattern

For total line length, request a sum rather than line geometries:

```json
{
  "where": "SUBNETWORKNAME = 'RMT002'",
  "statistics": [
    {
      "statisticType": "sum",
      "onStatisticField": "Shape__Length",
      "outStatisticFieldName": "total_length_m"
    }
  ]
}
```

For an overhead/underground split, group by the field that distinguishes those categories. If `ASSETGROUP` uses numeric codes, resolve the domain labels from layer metadata first:

```json
{
  "where": "SUBNETWORKNAME = 'RMT002' AND ASSETGROUP IN (101, 102)",
  "statistics": [
    {
      "statisticType": "sum",
      "onStatisticField": "Shape__Length",
      "outStatisticFieldName": "total_length_m"
    }
  ],
  "group_by_fields": ["ASSETGROUP"],
  "order_by_fields": "ASSETGROUP"
}
```

Replace field names and codes only after verifying them from that deployment's layer metadata. Do not infer that every conductor class is overhead or underground.

## Map and Trace Result Limits

- Do not pass hundreds or thousands of IDs to `highlightFeaturesByGlobalIds` merely because a trace returned them.
- For large traces, first report counts grouped by `sourceMapping`, asset group, or type.
- Highlight only a user-requested subset, the origin, operationally significant devices, or a safely bounded sample.
- Explain when a complete map overlay would be too dense to be useful.

## Circuit Context Zoom

For every successful circuit or subnetwork aggregate answer, attempt to zoom to its area after calculating the totals. This is required map context even when the user did not explicitly say "zoom." Do not send the final answer until `zoomTo` succeeds or you have reported why the compact extent lookup could not be resolved. Do not fetch all conductor geometries to do this.

1. Discover the `Electric Subnet Line` layer URL from service metadata.
2. Query that layer with the circuit filter and an extent-only response in WGS84:

```json
{
  "where": "SUBNETWORKNAME = 'RMT002'",
  "returnExtentOnly": true,
  "returnGeometry": false,
  "outSR": 4326
}
```

3. If the response includes `extent` with `xmin`, `ymin`, `xmax`, and `ymax`, calculate the center:

```text
longitude = (xmin + xmax) / 2
latitude = (ymin + ymax) / 2
```

4. Call `zoomTo` with that latitude, longitude, and a label such as `RMT002 circuit area`.
5. If the extent query returns no result, query only the one matching subnet feature with `returnGeometry: true`, `outSR: 4326`, and `resultRecordCount: 1`; derive a representative coordinate from that one geometry. Do not query the conductor layer for map context.

Include a short confirmation in the reply, for example: "Map centered on the RMT002 circuit area." The extent is only for navigation context. Do not describe it as the exact circuit boundary or claim the map highlights every conductor unless a bounded highlight was actually applied.

## When Statistics Fail

If the service rejects a statistics query or returns no usable aggregate:

1. Confirm the field names, layer URL, and where clause with a count-only query.
2. Retry one corrected aggregate query with `returnGeometry: false`.
3. If aggregation is genuinely unsupported, page only the two or three fields needed for the calculation. Use `resultRecordCount` no larger than 200 and sum locally across pages.
4. State that the value was calculated from paged records and report the row count used.
5. Do not repeatedly issue unbounded queries or read entire oversized result files.

## Reporting

Report the source layer, filter, unit, raw total, and converted unit. For a requested breakdown, distinguish verified categories from unclassified rows and never silently exclude unclassified assets.

Example:

> Electric Line, filtered to `SUBNETWORKNAME = 'RMT002'`, contains 1,862 matching records. Server-side statistics returned 130,762.76 m total. The overhead/underground totals are grouped by verified asset-group classifications; other conductor classes are reported separately.