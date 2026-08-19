# Feature service module

The `feature_service` router is the focused ArcGIS REST query layer in this repo. Use it to inspect service/layer metadata, preview records, and run safe feature-layer queries.

## Route name

`feature_service`

## Tools

1. `query_feature_layer` — query a feature layer through the ArcGIS REST `/query` endpoint.
2. `get_service_or_layer_details` — fetch JSON metadata from a service, layer, or similar ArcGIS REST endpoint.
3. `get_sample_feature_layer_data` — pull a small sample of records to inspect field names and values before building a larger query.

## Resource

- `resource://feature_service/query_info`

This resource loads guidance from `query_feature_service.md` when available.

## Prompt

- `feature_layer_query_prompt`

## Configuration

- `ARCGIS_VERIFY_SSL`
- `ARCGIS_TOKEN` (optional fallback token)

## Notes

- `query_feature_layer` automatically normalizes the URL to end in `/query`.
- Query defaults are applied when omitted: `f=json`, `where=1=1`, and `outFields=*`.
- `query_feature_layer` accepts `GET` or `POST`; unsupported methods fall back to `POST`.
- Tokens can be passed directly, resolved from auth context, or read from `ARCGIS_TOKEN`.

## Related docs

- [`feature_service.md`](feature_service.md)
- [`query_feature_service.md`](query_feature_service.md)
