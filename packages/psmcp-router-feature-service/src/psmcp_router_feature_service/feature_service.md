# Feature Service Module

## Overview

The `feature_service.py` module enables AI applications to inspect and query ArcGIS Feature Services and Feature Layers through the MCP server. It provides three tools for progressive data exploration — inspect metadata, preview sample data, then query with full parameters — along with a prompt that guides the AI through this workflow and a resource that serves as a query construction reference.

All tools authenticate via the MCP authentication context. The AI does not need to manage tokens directly.

---

## Components

### Tools

#### `get_service_or_layer_details`

Retrieves JSON metadata from any ArcGIS REST service or layer endpoint.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `endpoint_url` | `str` | Yes | Full URL of the service or layer endpoint |
| `timeout` | `int` | No | Request timeout in seconds. Default: 30 |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |

**Use this tool to:**
- Discover available layers in a Feature Service (pass `.../FeatureServer`)
- Inspect a layer's fields, geometry type, extent, capabilities, and relationships (pass `.../FeatureServer/0`)
- Works with FeatureServer, MapServer, and their individual layers

**Returns:** `success`, `status_code`, `data` (full JSON metadata), `error`

> **Note:** This tool replaces the previous `get_feature_service_details` and `get_feature_layer_details` tools, which were identical in implementation. A single tool with a clear description eliminates ambiguity for the AI.

---

#### `get_sample_feature_layer_data`

Fetches a small sample of features from a layer to preview field names, value formats, and data types before constructing a full query.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `endpoint_url` | `str` | Yes | Full URL of the feature layer endpoint |
| `count` | `int` | No | Number of sample features to retrieve. Default: 5 |
| `timeout` | `int` | No | Request timeout in seconds. Default: 30 |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |

**Use this tool to:**
- Confirm field names match the metadata from `get_service_or_layer_details`
- See actual data values and formats (especially for date fields, coded domains, and null patterns)
- Verify the layer is returning data before building complex queries

**Returns:** `success`, `status_code`, `data` (sample features), `error`

The tool automatically appends `/query` to the URL if not present, and queries with `where=1=1`, `outFields=*`, and `resultRecordCount` set to the requested count.

---

#### `query_feature_layer`

Queries features from a layer using the full range of ArcGIS REST API query parameters, including attribute filters, spatial filters, pagination, and field selection.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `endpoint_url` | `str` | Yes | Full URL of the feature layer endpoint |
| `parameters` | `Dict[str, Any]` | Yes | Dictionary of query parameters (where, outFields, geometry, etc.) |
| `timeout` | `int` | No | Request timeout in seconds. Default: 30 |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |
| `method` | `str` | No | Optional HTTP method (`GET` or `POST`). Defaults to `POST`. |
| `headers` | `Dict[str, Any]` | No | Optional HTTP headers to include in the request. |

**Use this tool to:**
- Filter features by attribute (`where`)
- Filter features by spatial extent (`geometry`, `geometryType`, `inSR`)
- Count matching features (`returnCountOnly=true`)
- Page through large result sets (`resultRecordCount`, `resultOffset`, `orderByFields`)
- Control which fields are returned (`outFields`)
- Control whether geometry is returned (`returnGeometry`)

**Returns:** `success`, `status_code`, `data` (features, count, or IDs depending on parameters), `error`

**Built-in safeguards:**
- Automatically appends `/query` to the URL if not present
- Defaults `f` to `json`, `where` to `1=1`, and `outFields` to `*` if not provided
- Strips any `token` key from the parameters dict to prevent accidental override — the resolved token is always applied internally
- Defaults to POST to avoid URL length limits with complex queries; GET is supported when requested

---

### Prompt

#### `feature_layer_query_prompt`

A system prompt template that guides the AI through the recommended feature layer query workflow.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `endpoint_url` | `str` | No | Feature layer URL to include in the prompt. Optional. |

**Workflow described in the prompt:**

1. Call `get_service_or_layer_details` to read the layer's schema and metadata (fields, geometry type, capabilities).
2. Call `get_sample_feature_layer_data` (default 5 records) to confirm field names and value formats.
3. If the request involves records, run a COUNT first using `query_feature_layer` with `returnCountOnly=true`.
4. If rows are needed, page results in batches of 25 using `resultRecordCount`, `resultOffset`, and `orderByFields`.

**Additional guidance in the prompt:**
- Always include OBJECTID in outFields if the layer supports it
- Prefer explicit outFields over `*` when returning many records
- Set `returnGeometry=false` unless geometry is specifically needed
- Use `outSR={"wkid": 4326}` for distance or area calculations

---

### Resource

#### `feature_service_query_info`

| Property | Value |
|---|---|
| **URI** | `resource://feature_service/query_info` |
| **Type** | Static |
| **Source** | `query_feature_service.md` (loaded from disk at runtime) |

A reference document that provides detailed guidance on constructing the `parameters` dict for `query_feature_layer`. The AI reads this resource to understand available query parameters, geometry filter formats, date/time query syntax, and pagination patterns.

**Content includes:**
- Full parameter table with types and descriptions
- Geometry filter examples for all four geometry types (point, envelope, polygon, polyline)
- Combined attribute + spatial query example
- Date/time field types and INTERVAL syntax for relative date queries
- Pagination pattern with concrete page 1/2/3 examples

The resource complements the prompt: the prompt defines *when and in what order* to call tools, while the resource defines *how to construct parameters* for those tools.

---

## AI Workflow

```
User asks a question about feature data
        │
        ▼
┌─────────────────────────────┐
│  get_service_or_layer_details│  ◄── Inspect metadata: fields, geometry type, capabilities
│  (.../FeatureServer or       │
│   .../FeatureServer/0)       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  get_sample_feature_layer_data│  ◄── Preview: confirm field names and value formats
│  (default 5 records)          │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  query_feature_layer         │  ◄── Count first: returnCountOnly=true
│  (count query)               │
└──────────────┬──────────────┘
               │
       ┌───────┴───────┐
       │ Count only     │ Rows needed
       ▼               ▼
   Return count   query_feature_layer
                  (paged: resultRecordCount=25,
                   resultOffset, orderByFields)
                       │
                       ▼
                   Return results
```

---

## Design Decisions

### Single metadata tool instead of two

The original implementation had `get_feature_service_details` and `get_feature_layer_details` as separate tools, but both were identical in implementation — they made a GET request with `f=json` to whatever URL was provided. Having two tools with the same behavior confused the AI into choosing between them unnecessarily. The merged `get_service_or_layer_details` tool makes it clear that a single tool handles both service-level and layer-level metadata inspection.

### Default to POST, allow GET

POST remains the default because it avoids URL length limits with complex where clauses or geometry filters. GET is still supported for compatibility or edge cases where POST is not accepted.

### Automatic /query URL normalization

Rather than relying on the AI to append `/query` to endpoint URLs (which the prompt previously instructed), the tool now handles this internally via `_ensure_query_url()`. This eliminates a common failure mode where the AI forgets to append `/query` and the request hits the wrong endpoint.

### Token protection in parameters dict

The `query_feature_layer` tool accepts a freeform `parameters` dict, which means the AI could accidentally include a `token` key. The tool now strips any `token` from the parameters dict before applying the resolved authentication token, preventing accidental override or exposure.

### Tool signatures

The tool keeps `method` and `headers` optional for compatibility, while still defaulting to POST. The internal `ctx: Context` parameter remains removed because it was unused.
