---
name: utility-transformer-lookup
description: Find nearby verified transformer candidates through the configured network server and highlight their GlobalIDs in the browser.
tags: [agent-runtime, utility-network, transformer]
requires_tools: [network_initialize_session, network_find_nearest_transformers]
---

# Nearby Transformer Lookup

Use for a transformer near an address, selected location, supplied coordinates,
or the current map. Obtain WGS84 latitude/longitude from `getUserAddedContext({})`,
`getCurrentMapContext({})`, or an available geocoding result. Never treat projected
map coordinates as degrees. Resolve an ambiguous address or missing location first.

Initialize the network session, then call
`network_find_nearest_transformers(latitude=..., longitude=...,
radius_meters=1609.344, limit=5, network_service_url=...)`.
Latitude must be -90..90, longitude -180..180, radius 25..25000 meters, and limit
an integer 1..25. The service argument is the network FeatureServer and can be
omitted to use deployment configuration; never hardcode a device layer endpoint.
Authentication normally comes from the connection.

The server discovers transformer classification and returns `featureServiceUrl`,
`searchPoint`, `radiusMeters`, `count`, and ranked `nearest` candidates. Each
candidate includes `layerId`, `layerUrl`, `objectId`, `globalId`, `distanceMeters`,
WGS84 `coordinates`, and `attributes`. Keep these identities for subsequent work.
An empty result is valid; offer a larger radius within supported bounds, but do
not silently change the user's requested search. Classification/service errors
are failures, not permission to treat every device as a transformer.
Classification requires unambiguous transformer subtype or asset/equipment domain
labels; a layer title or an unverified abbreviation is not enough. The search
verifies complete candidate retrieval and ranks WGS84 ellipsoid geodesic distances
with stable layer/object-ID ties. Report classification or paging limitations
instead of substituting an arbitrary device query. Concurrent service edits are
not prevented by this read-only operation.

Highlight returned GlobalIDs with browser `highlightFeaturesByGlobalIds`.
Use browser-discovered layer IDs for optional map-layer targeting, not the server's
numeric `layerId`. `zoomTo` can show the search location or a returned coordinate.
Check highlighting results and distinguish lookup success from map presentation.
Report the nearest candidate, distance in meters, search radius, and identifiers.
For later traces use its GlobalID and the returned FeatureServer, resolving
terminals using the trace workflow. Never invent a missing GlobalID.
