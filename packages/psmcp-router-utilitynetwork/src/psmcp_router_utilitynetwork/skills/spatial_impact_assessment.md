# Spatial Impact Assessment Workflow

You are assessing customer impact within a geographic area by manually orchestrating spatial queries, start-point minimization, downstream tracing, and customer resolution.

## Prerequisites

- A geometry (polygon, envelope, or buffered point)
- The utility network FeatureServer URL
- Optionally: customer data layer URL and join field

## Step 1: Acquire Geometry

- If user provides a polygon: use directly as `{"rings": [[[x1,y1],[x2,y2],...]]}`
- If user provides an envelope/bbox: use as `{"xmin":..., "ymin":..., "xmax":..., "ymax":...}`
- If user provides an address or point:
  1. Geocode via `find_address_candidates(single_line="{address}")`
  2. Buffer the point by 250 feet (or user-specified distance) to create a polygon
  3. A simple buffer: create a square envelope around the point

Determine `geometry_type`:
- Polygon (rings): `"esriGeometryPolygon"`
- Envelope (bbox): `"esriGeometryEnvelope"`

## Step 2: Identify Device Layers

Call `network_get_metadata(section="asset_types")`.

From the results, identify source layers that are device junction sources:
- Look for sources where `utilityNetworkFeatureClassUsageType == "esriUNFCUTDevice"` (or `usageType == "esriUNFCUTDevice"`)
- Note their `layerId` values — these are the layers you'll query spatially

## Step 3: Spatial Query for Devices in the Impact Area

For EACH device layer identified in Step 2, run a spatial query:

```
query_feature_layer(
    endpoint_url="{UTILITY_NETWORK_URL}/{layerId}",
    parameters={
        "geometry": "{geometry_json}",
        "geometryType": "{geometry_type}",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
        "outFields": "globalid,assetgroup,assettype,subnetworkname",
        "returnGeometry": "false"
    }
)
```

Collect ALL features from ALL device layers. For each feature:
- Normalize attribute keys to lowercase for consistency
- Record `globalid` — track these as "inside the impact area" (store in a set for later comparison)
- Record `subnetworkname` (for grouping in Step 4)
- Record `assetgroup` and `assettype` codes

**If NO features found across all layers:** report "No network devices found within the specified geometry" and STOP.

## Step 4: Minimize Start Points

The goal is to reduce the number of features you trace from. Tracing from every device is wasteful — if you trace from a device's upstream controller, you'll cover all downstream devices automatically.

**The final pruned set must NEVER be larger than the original input.** If it is, discard the pruning and use the original elements.

### 4a. Group by Subnetwork

- Group the spatial query results by their `subnetworkname` field
- If NO elements have a `subnetworkname` value, treat ALL elements as a single group
- Process each subnetwork group independently

### 4b. For Each Subnetwork Group:

**Step i — Check for controller in selection:**
- Look for any element whose `assetGroupName` or `assetTypeName` contains "controller" (case-insensitive)
- If found: use ONLY that controller as the start point for this subnetwork (discard other elements in the group)
- Move to the next group

**Step ii — If no controller in selection, probe upstream:**
- Pick the FIRST element from the group
- Call `network_upstream_trace(starting_global_id="{element_globalid}")`
- In the upstream trace results, check for elements with "controller" in `assetGroupName` or `assetTypeName` (case-insensitive):
  - If a controller is found upstream: use that controller as the sole start point for this subnetwork
  - Move to the next group

**Step iii — If no controller found upstream, check for protective devices:**
- In the same upstream trace results, search for elements matching protective device categories:
  - Call `network_get_metadata(section="categories")` (if not already cached)
  - Look for categories whose name contains "protective", "protection", "interrupter", "isolation", or "oprable" (case-insensitive)
  - Filter upstream elements whose (`networkSourceId`, `assetGroupCode`, `assetTypeCode`) matches those category members
  - **Fallback**: if no matching categories, use device source heuristic (elements whose `networkSourceId` belongs to a source with `usageType == "esriUNFCUTDevice"`)
- If protective device(s) found: use the FIRST one as the start point for this subnetwork
- Move to the next group

**Step iv — If nothing found:**
- Keep ALL elements in this subnetwork group as start points (no minimization possible)

**Error handling for upstream probe:**
- If the upstream trace call fails (network error, timeout, etc.): keep ALL original elements for this subnetwork group
- Do NOT let a probe failure crash the entire workflow

### 4c. Verify Result

- Count the pruned start points. If `len(pruned) > len(original_elements)`, something went wrong — fall back to using the original elements as-is.

## Step 5: Run Downstream Trace from All Start Points

For each pruned start point, run a downstream trace:

```
network_downstream_trace(starting_global_id="{globalid}")
```

**Important:** The server tool only accepts one starting point per call. Run one trace per start point and merge results (collect all unique elements across all traces, deduplicate by `globalId`).

If domain/tier scoping was provided, pass it to each trace call.

## Step 6: Filter for Service Points

Apply the same service point filtering logic described in the Downstream Customer Impact skill (Step 4):
1. Call `network_get_metadata(section="categories")`
2. Find "Service Point" category members by (`networkSourceId`, `assetGroupCode`, `assetTypeCode`)
3. Filter combined trace elements by those tuples
4. Fallback: filter where `sourceName` contains "service" if no category exists

## Step 7: Distinguish Inside vs. Downstream-Outside

Compare each service point's `globalId` against the spatial query results from Step 3:
- **Inside the impact area:** Service point's GlobalID WAS in the set of GlobalIDs collected in Step 3 (the spatial query results)
- **Downstream outside:** Service point's GlobalID was NOT in the spatial query results but was found by the downstream trace

Separate service points into two lists: `inside_service_points` and `outside_service_points`.

## Step 8: Resolve Customer Data (Conditional)

Apply the same customer resolution logic described in the Downstream Customer Impact skill (Step 5), but run it **separately** for inside and outside service point groups:

1. Resolve join values for INSIDE service points (query service_point_layer with inside GlobalIDs)
2. Resolve join values for OUTSIDE service points (same, with outside GlobalIDs)
3. Query customer layer separately for each group's join values
4. Apply `network_resolve_coded_values` on both sets of customer records
5. Present with distinction: "X customers inside the area, Y customers downstream-outside"

### If customer config NOT known:

- Report service point counts (inside vs. outside) with their GlobalIDs
- Suggest running the `utility_network_customer_data_discovery` prompt

### Error handling:

If customer resolution fails at any step, still report trace results and service point breakdown. Do NOT discard the spatial and trace work.

## Step 9: Present Results

Structure the report:
- "Impact area contains **N devices** across M subnetworks"
- "After minimization, traced from **P start points**"
- "**Inside impact area:** X service points (Y customers, Z kW)"
- "**Downstream outside:** A service points (B customers, C kW)"
- "**Total affected:** X+A service points, Y+B customers"

## 811 Call-Before-You-Dig Variant

For 811/dig-site scenarios:
1. Geocode the dig address
2. Buffer by 250 feet (standard utility clearance)
3. Follow Steps 2-9 above
4. Emphasize reporting ALL network assets in the area (not just service points) — the dig crew needs to know about every buried asset
