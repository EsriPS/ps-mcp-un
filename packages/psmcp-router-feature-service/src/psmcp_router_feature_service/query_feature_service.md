# Feature Layer Query Reference

This resource describes how to construct parameters for the `query_feature_layer` tool.
Use `get_service_or_layer_details` to inspect a layer's fields and geometry type before querying.
Use `get_sample_feature_layer_data` to preview actual field values before building filters.

The `query_feature_layer` tool also accepts optional `method` and `headers` arguments at the tool level.
POST is the default and recommended; GET is supported for compatibility or when required by a proxy.

---

## Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `where` | string | SQL-like filter expression. Use `1=1` for no filter. |
| `outFields` | string | Comma-separated field names to return. Use `*` for all fields. Prefer explicit fields when returning many records. |
| `returnGeometry` | boolean | Set to `false` unless geometry is needed. Reduces response size. |
| `returnCountOnly` | boolean | Set to `true` to return only the count of matching features. |
| `resultRecordCount` | integer | Maximum number of records to return (page size). |
| `resultOffset` | integer | Number of records to skip. Use with `resultRecordCount` and `orderByFields` for pagination. |
| `orderByFields` | string | Comma-separated fields for sorting. Required for stable pagination (typically `OBJECTID`). |
| `outSR` | string | Spatial reference for returned geometries (e.g., `{"wkid": 4326}`). |
| `geometry` | object | Spatial filter geometry. Must be paired with `geometryType` and `inSR`. See geometry examples below. |
| `geometryType` | string | Type of the geometry filter. Values: `esriGeometryPoint`, `esriGeometryPolyline`, `esriGeometryPolygon`, `esriGeometryEnvelope`. |
| `spatialRel` | string | Spatial relationship to apply. Default: `esriSpatialRelIntersects`. Other values: `esriSpatialRelContains`, `esriSpatialRelWithin`, `esriSpatialRelCrosses`, `esriSpatialRelOverlaps`, `esriSpatialRelTouches`. |
| `inSR` | string | Spatial reference of the input geometry. **Required** when `geometry` is provided. |
| `returnIdsOnly` | boolean | Set to `true` to return only the object IDs of matching features. |
| `token` | string | Authentication token. Required for secured services. If not provided as a tool parameter, the token is resolved automatically from the authentication context. |
| `f` | string | Response format. Defaults to `json`. Do not change. |

---

## Geometry Filter Examples

When using a spatial filter, always include `geometry`, `geometryType`, and `inSR` together.

### Point

```json
{
  "geometryType": "esriGeometryPoint",
  "geometry": {
    "x": -118.15,
    "y": 33.80,
    "spatialReference": {"wkid": 4326}
  },
  "inSR": {"wkid": 4326}
}
```

### Envelope (Bounding Box)

```json
{
  "geometryType": "esriGeometryEnvelope",
  "geometry": {
    "xmin": -97,
    "ymin": 32,
    "xmax": -96,
    "ymax": 34,
    "spatialReference": {"wkid": 4326}
  },
  "inSR": {"wkid": 4326}
}
```

### Polygon

```json
{
  "geometryType": "esriGeometryPolygon",
  "geometry": {
    "rings": [
      [
        [-97, 32],
        [-98, 34],
        [-96, 36],
        [-97, 32]
      ]
    ],
    "spatialReference": {"wkid": 4326}
  },
  "inSR": {"wkid": 4326}
}
```

### Polyline

```json
{
  "geometryType": "esriGeometryPolyline",
  "geometry": {
    "paths": [
      [
        [-97.06138, 32.837],
        [-97.06133, 33.836],
        [-98.2, 34.834],
        [-97, 40]
      ]
    ],
    "spatialReference": {"wkid": 4326}
  },
  "inSR": {"wkid": 4326}
}
```

---

## Combined Attribute + Spatial Query Example

```json
{
  "where": "status = 'active'",
  "geometryType": "esriGeometryEnvelope",
  "geometry": {
    "xmin": -97,
    "ymin": 32,
    "xmax": -96,
    "ymax": 34,
    "spatialReference": {"wkid": 4326}
  },
  "inSR": {"wkid": 4326},
  "spatialRel": "esriSpatialRelIntersects",
  "outFields": "OBJECTID,name,status",
  "returnGeometry": true,
  "outSR": {"wkid": 4326}
}
```

---

## Date and Time Query Syntax

Date/time field types use different syntax depending on the field type.

### Field Types

| Field Type | Contains | Example |
|---|---|---|
| `esriFieldTypeDate` | Date and time (local time) | `incident_datetime = timestamp '2003-01-25 14:35:00'` |
| `esriFieldTypeDateOnly` | Date only (no time zone) | `birth_date = date '1990-01-25'` |
| `esriFieldTypeTimeOnly` | Time only (no time zone) | `store_close_time = time '21:00:00'` |
| `esriFieldTypeTimestampOffset` | Date, time, and UTC offset | `flight_arrival = timestamp '2003-01-25 14:35:00 -08:00'` |

### Relative Date Queries Using INTERVAL

Use `CURRENT_DATE` or `CURRENT_TIMESTAMP` with `INTERVAL` to query relative to the current time.

**Syntax:**

```
<DateField> >= CURRENT_TIMESTAMP - INTERVAL '<value>' <unit>
```

**Supported units and formats:**

| Unit | Format | Example |
|---|---|---|
| DAY | `'DD'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '7' DAY` |
| HOUR | `'HH'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '24' HOUR` |
| MINUTE | `'MI'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '30' MINUTE` |
| SECOND | `'SS'` or `'SS.FFF'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '90' SECOND` |
| DAY TO HOUR | `'DD HH'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '3 05' DAY TO HOUR` |
| DAY TO MINUTE | `'DD HH:MI'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '3 05:32' DAY TO MINUTE` |
| DAY TO SECOND | `'DD HH:MI:SS'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '3 05:32:28' DAY TO SECOND` |
| HOUR TO MINUTE | `'HH:MI'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '05:32' HOUR TO MINUTE` |
| HOUR TO SECOND | `'HH:MI:SS'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '05:32:28' HOUR TO SECOND` |
| MINUTE TO SECOND | `'MI:SS'` | `DateField >= CURRENT_TIMESTAMP - INTERVAL '32:28' MINUTE TO SECOND` |

**Example:** Query features from the last 3 days, 5 hours, 32 minutes, and 28 seconds:

```
DateField >= CURRENT_TIMESTAMP - INTERVAL '3 05:32:28' DAY TO SECOND
```

---

## Pagination Pattern

To page through large result sets, combine `resultRecordCount`, `resultOffset`, and `orderByFields`:

```
Page 1: {"where": "1=1", "resultRecordCount": 25, "resultOffset": 0,  "orderByFields": "OBJECTID"}
Page 2: {"where": "1=1", "resultRecordCount": 25, "resultOffset": 25, "orderByFields": "OBJECTID"}
Page 3: {"where": "1=1", "resultRecordCount": 25, "resultOffset": 50, "orderByFields": "OBJECTID"}
```

Always include `orderByFields` when paginating to ensure stable ordering across pages.
