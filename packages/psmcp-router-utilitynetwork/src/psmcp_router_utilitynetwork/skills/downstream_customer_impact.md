---
name: utility-network-downstream-customer-impact
description: Trace downstream from a verified network start, identify service points, and join discovered customer records without losing partial results.
tags: [agent-runtime, utility-network, customers]
requires_tools: [network_initialize_session, network_device_terminals, network_list_named_traces, network_named_trace, network_downstream_trace, network_get_metadata, query_feature_layer, get_service_or_layer_details, network_resolve_coded_values]
---

# Downstream Customer Impact

1. Establish the network FeatureServer and starting GlobalID. Call
   `network_initialize_session()` once and follow the
   [terminal procedure](references/trace_terminals.md) for the downstream direction.
2. Discover `network_list_named_traces`. Prefer a matching saved downstream
   configuration when the user wants its barriers/functions. Confirm ambiguity,
   then call `network_named_trace` with its exact name and preserve its direction.
   If no saved configuration fits a simple downstream request, call
   `network_downstream_trace`. Use optional domain/tier scoping only with discovered
   values. Do not assert that all traces require a distribution start.
3. Inspect the returned trace data and warnings. Identify service points using
   `network_get_metadata(section="categories")` and verified asset-type membership
   (`networkSourceId`, `assetGroupCode`, `assetTypeCode`). Named/directional results
   may not be enriched: resolve `sourceMapping` and metadata as needed.
   A source name containing "service" is only a candidate, not proof of classification.
   If classification is unknown, report unclassified trace features rather than
   inventing a customer count.
4. Collect distinct service-point `globalId` values. Trace elements can repeat for
   different terminals; preserve terminal detail but deduplicate feature counts.
5. If customer data is known, verify its layer/table and relationship fields with
   `get_service_or_layer_details`. Query service-point attributes with
   `query_feature_layer(endpoint_url=..., parameters=...)` using the actual GlobalID
   field. Extract and deduplicate the verified join keys, then query the customer
   layer/table. Validate field names from metadata and escape SQL literal quotes.
   Complete required pages rather than treating a truncated query as all customers.
6. Decode returned customer attributes with `network_resolve_coded_values` when
   needed. If no verified join exists, retain service-point IDs/counts and offer
   customer-data discovery instead of assuming a fixed CIS table or meter field.

Report trace element count, classified service-point count, resolved customer
count, and function results with verified units where available. If joining fails,
retain the successful trace and identify the customer-resolution error. A missing
join value is not proof that the service point has no customer. Never present
modeled impact as a confirmed outage.

For visual presentation in the browser, pass all desired GlobalIDs to
`highlightFeaturesByGlobalIds` and inspect unmatched IDs. Preserve the chosen
service and start for subsequent upstream requests.
