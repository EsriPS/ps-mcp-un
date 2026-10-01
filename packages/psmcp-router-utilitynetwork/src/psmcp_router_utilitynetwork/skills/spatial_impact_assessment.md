---
name: hurricane-utility-impact
description: Assess utility assets in a hazard or dig-site geometry, trace downstream impact, and distinguish spatial exposure from modeled customer impact.
tags: [agent-runtime, utility-network, spatial, hazard]
requires_tools: [network_initialize_session, network_get_metadata, network_device_terminals, network_list_named_traces, network_named_trace, network_downstream_trace, query_feature_layer, get_service_or_layer_details, network_resolve_coded_values]
---

# Spatial and Hurricane Utility Impact

## Establish the geometry and scope

Obtain the requested polygon, envelope, point/radius, or hurricane forecast track
from user context or discovered datasets. In a browser, use `getUserAddedContext`
and `getCurrentMapContext` when the request refers to the map. Record forecast
issue/valid times and distinguish projected exposure from observed damage.
Inspect the hazard and target layer schemas using `get_service_or_layer_details`.

Use the geometry's real spatial reference in query `inSR`. A degree is not a
meter; a square envelope is not a circular buffer. For distance-to-track work,
use a supported spatial distance query or an available geoprocessing operation
with the requested distance and units. If a required buffer/intersection tool or
geometry is unavailable, say so rather than inventing a result.

## Identify exposed assets

Initialize the network session and use `network_get_metadata(section="asset_types")`
and layer metadata to discover target sources/classifications. Query the actual
layer endpoints using `query_feature_layer`, passing geometry, geometryType,
spatialRel, inSR, and verified fields. Follow service paging/transfer-limit signals.
Collect all matching GlobalIDs and preserve the original spatial-query set.
An empty successful query is a valid no-matches result.

For overhead-line/vegetation scenarios, verify overhead classification, trim-history
fields or join keys, and the requested age threshold. Compute relative dates from
the current date, not a frozen example date. Separate overdue, recently trimmed,
and missing-history assets. For transformer/temperature scenarios, verify device
classification, phase domains, sensor join keys, and anomaly definitions before
ranking. Do not invent critical-customer classes or thresholds.

## Trace modeled downstream impact

Follow the [terminal procedure](references/trace_terminals.md) for every start.
Discover appropriate saved downstream traces with `network_list_named_traces`;
use `network_named_trace` when the requested analysis needs that configuration,
or `network_downstream_trace` for a simple directional trace. Each call accepts
one start. Merge distinct returned GlobalIDs while retaining start-to-result
provenance and per-trace errors.

Avoid unnecessary repeated traces only when verified connectivity proves an
equivalent result. Do not silently replace exposed starts with an upstream
controller outside the hazard area; that can overstate impact. If a probe or
minimization cannot be verified, keep the original starts and disclose coverage.

Identify service points from actual categories and join customer data through
verified fields using feature queries and `network_resolve_coded_values`.
Report successful traces even when classification or customer resolution fails.
To distinguish service points inside the hazard from downstream-outside points,
spatially test their actual geometries or query their own source layers. Absence
from a device-only query is not proof that a service point lies outside.

## Present and map results

Report exposed assets, trace starts, trace coverage/failures, distinct service
points, and customers inside versus downstream-outside only where established.
Highlight result GlobalIDs through browser `highlightFeaturesByGlobalIds`; server
traces do not themselves update the map. Export only through available tools and
report the real format/location or the limitation.

For an 811/dig-site request, use the supplied or authorized clearance distance,
not an invented universal 250-foot standard. Include discovered buried assets,
not only service points, and identify missing datasets and location uncertainty.
