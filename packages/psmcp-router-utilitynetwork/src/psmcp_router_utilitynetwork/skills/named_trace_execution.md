---
name: utility-network-named-trace
description: Discover and execute saved utility network traces, resolve terminals, or choose a basic upstream or downstream trace.
tags: [agent-runtime, utility-network, trace]
requires_tools: [network_initialize_session, network_list_named_traces, network_named_trace, network_device_terminals, network_get_metadata, network_upstream_trace, network_downstream_trace, network_trace]
---

# Named Trace Execution

Use a saved trace when the user names a configuration or needs its engineered
barriers, functions, propagators, or output filters. There is no fixed trace menu.

1. Call `network_initialize_session()` once per session before network tools.
2. Resolve the intended network FeatureServer from deployment configuration,
   the user, or browser map service discovery. Keep that service consistent across
   discovery, terminal lookup, execution, and result queries.
3. Call `network_list_named_traces(network_service_url=...)`. Read `namedTraces`,
   including each configuration's exact `name`, `description`, and `traceType`.
   Match user intent, not a remembered demo catalog. Ask when several match.
4. Resolve the real starting GlobalID from user-added context or a feature query.
   Follow the [terminal procedure](references/trace_terminals.md) before execution.
5. Call `network_named_trace(named_trace_name=..., starting_global_id=...,
   terminal_id=...)`, omitting the terminal when metadata indicates none.
   `trace_type`, `network_service_url`, and `token` are also optional schema
   fields, not forbidden extra arguments. Preserve the saved `traceType` by
   default; only override `trace_type` for an explicit, understood request.
   Authentication normally comes from the connection; do not ask for tokens in chat.
6. Read the actual response, including `traceResults`, `elements`, `sourceMapping`,
   function results, warnings, and errors where present. A successful request does
   not prove that the desired features were traversed.

## Basic upstream and downstream workflows

If no saved trace fits and the user needs a simple directional trace, call
`network_upstream_trace` or `network_downstream_trace` with the resolved start and
terminal. Upstream investigates supply/connectivity toward sources; downstream
investigates potentially served features. For other supported algorithms use
`network_trace` with an accepted `trace_type`. Read the actual tool schema for
optional `domain_network_name`, `tier_name`, `percent_along`, and
`subnetwork_name`; these are not arguments to `network_named_trace`.
Discover domain/tier names using `network_get_metadata(section="domain_networks")`.
Do not silently replace a complex saved configuration with a basic trace.

## Errors and tier context

No distribution-only restriction is imposed by this collection. Terminal/tier
preflight is instruction guidance, not a claim that named-trace execution enforces
helper validation. Use returned tier/subnetwork metadata and actual service errors.
For an outside-tier error, explain the reported incompatibility without inventing
the required tier or choosing a different start behind the user's back.

For a mistaken name, rediscover saved names and retry once only if one unambiguous
match preserves user intent. For a terminal error, re-read metadata and retry once
with a supported correction; ask about ambiguous choices. Never repeatedly retry
unchanged inputs, replace the GlobalID with an example, or dump only raw errors.
For execution/auth/topology failures, state the observed failure and the next
diagnostic step. Keep confirmed results separate from incomplete work.

Browser presentation uses `highlightFeaturesByGlobalIds` with returned GlobalIDs;
verify its result before claiming success. The browser's map layer IDs are not
utility network source IDs.
