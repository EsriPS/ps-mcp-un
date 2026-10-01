---
name: utility-service-discovery
description: Discover deployment-specific utility services, layers, asset classes, tiers, terminals, categories, and network attributes.
tags: [agent-runtime, utility-network, metadata]
requires_tools: [network_initialize_session, network_get_metadata, get_service_or_layer_details]
---

# Utility Service and Metadata Discovery

Use configured services or explicitly supplied URLs. In a browser, inspect
`getUserAddedContext`, `getMapServiceUrls`, `getCurrentMapContext`, `getWebMapInfo`,
and `getLayerInfo` when relevant. Prefer the selected feature's service over
guessing from unrelated visible layers. If several networks fit, ask which one.
There is no built-in demo endpoint or fixed layer/table catalog.

Call `get_service_or_layer_details(endpoint_url=...)` on the FeatureServer to
inspect both layers and tables, then on candidate layer endpoints to inspect
fields, geometry, spatial reference, domains, subtypes, and relationships.
Distinguish parent FeatureServer URLs used by network tools from numeric layer
endpoints used for feature queries. Discover layer IDs; never infer them from
networkSourceId or a browser map layer ID.

Call `network_initialize_session()` once before network tools. Use
`network_get_metadata(section=..., network_service_url=...)` for focused sections:

| Section | What to establish |
|---|---|
| domain_networks | Domain networks, tier groups, actual tier hierarchy and topology |
| asset_types | Source names, asset groups/types and codes; optionally filter by domain_network or source_name |
| network_attributes | Attribute types, domains, and available function/propagator inputs |
| categories | Category membership for service points, protective assets, and other classifications |
| terminal_configurations | Terminal names, directionality and valid paths |
| topology_rules | Supported connectivity patterns |
| propagators | How network attributes propagate |

Use source/layer metadata to associate returned structures with actual endpoints.
Do not claim an omitted layer ID, category, field, relationship, or tier is known.
If no map or configured service identifies the intended network, ask for its
service URL or authorized discovery context. When available, portal search can
help locate datasets; it is optional, not a fixed catalog substitute.
