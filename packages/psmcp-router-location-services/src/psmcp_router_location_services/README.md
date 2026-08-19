# Location services module

The `location_services` router provides ArcGIS geocoding helpers. Right now it is a focused, single-purpose route for turning a free-form address or place string into candidate coordinates.

## Route name

`location_services`

## Tool

1. `find_address_candidates` — call the configured ArcGIS geocode service and return address candidates, scores, coordinates, and attributes.

## Configuration

- `ARCGIS_GEOCODE_SERVICE_URL` — required geocode service base URL
- `ARCGIS_VERIFY_SSL`
- `ARCGIS_TOKEN` — optional fallback token

## Notes

- The tool calls `{ARCGIS_GEOCODE_SERVICE_URL}/findAddressCandidates`.
- `max_locations` is capped at `50` in code.
- The default output spatial reference is `4326`.
- This module currently exposes no prompts or resources.
