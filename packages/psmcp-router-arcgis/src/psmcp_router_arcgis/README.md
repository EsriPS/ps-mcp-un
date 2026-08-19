# ArcGIS module

The `arcgis` router groups ArcGIS Enterprise discovery tools. It covers portal identity checks, content search, item inspection, user group lookup, and system GP service discovery.

## Route name

`arcgis`

## Tools

1. `get_user_info` — validate the current ArcGIS token and return profile details.
2. `list_system_services` — list ArcGIS Server `System` GP services for the configured portal/server.
3. `get_item_info` — fetch full portal item metadata, with optional `/data` payload retrieval.
4. `search_portal` — search portal content with query text, structured filters, pagination, and sorting.
5. `list_user_groups` — list groups for the authenticated user.

## Prompts

- `arcgis_enterprise_prompt`

## Configuration

Required for most portal-backed operations:

- `ARCGIS_PORTAL_URL`

Common optional settings:

- `ARCGIS_VERIFY_SSL`
- `ARCGIS_TOKEN`
- `USE_ARCGIS_AUTH`
- `MCP_SERVER_BASE_URL`

## Notes

- Token resolution uses the shared auth helper in `auth/`.
- `search_portal`, `get_item_info`, and `list_user_groups` require an authenticated token. `search_portal` includes `portal_url` in its response so downstream tools can reference the correct portal.
- `list_system_services` is implemented here because it relies on ArcGIS portal/server discovery, even though it helps geoprocessing workflows.

## Related docs

- [`arcgis_auth_info.md`](arcgis_auth_info.md)
