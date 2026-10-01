---
name: utility-network-address-resolution
description: Resolve an address to a confirmed network feature using geocoding or discovered address/customer fields.
tags: [agent-runtime, utility-network, address]
requires_tools: [find_address_candidates, network_initialize_session, network_get_metadata, get_service_or_layer_details, query_feature_layer]
---

# Address to Network Element

Offer geocoding/proximity or address-field lookup when the user's intended method
is unclear. An address is not itself a trace start; obtain and confirm a real
network GlobalID.

## Geocoding and proximity

1. Call `find_address_candidates(single_line=...)`. Check match score, address,
   coordinates, and spatial reference. Ask about ambiguous candidates.
2. Initialize the network session and discover addressable asset classes using
   `network_get_metadata(section="asset_types")`. Inspect the corresponding
   FeatureServer layers with `get_service_or_layer_details`.
3. Query the discovered source with `query_feature_layer`, using the point's
   actual `inSR`, a disclosed search distance/units, and verified asset-group/type
   filters. For shared layers, preserve valid group/type pairs rather than mixing
   unrelated codes. Do not silently broaden to all devices when classification
   is unknown.
4. Request GlobalIDs, identifying attributes, and geometry if needed to compare
   matches. A proximity result is approximate; it is not proof of service.
   If no matches occur, report the tested radius and agree on a larger search.

## Address fields or customer relationships

Inspect candidate layers/tables for service-address fields, not just billing
addresses. Query verified fields with escaped string literals and disclose
formatting/fuzzy-match limitations. When an address exists only in a customer
table, verify the relationship back to the network service point before using
its GlobalID. Do not assume a fixed meter/premise key.

Present candidates with resolved asset identity and location. Confirm the chosen
feature before tracing, particularly for rural geocodes, multiple meters, or
mailing/service address differences. Browser `zoomTo` can show known WGS84
coordinates; `highlightFeaturesByGlobalIds` can show a matched feature. A pin is
not a verified network connection.
