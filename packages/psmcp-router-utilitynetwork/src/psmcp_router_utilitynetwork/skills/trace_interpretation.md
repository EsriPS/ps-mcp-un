---
name: utility-network-trace-interpretation
description: Interpret utility trace elements, functions, phases, warnings and failures without inventing operational conclusions.
tags: [agent-runtime, utility-network, trace]
requires_tools: [network_initialize_session, network_get_metadata, network_device_terminals, network_query_associations]
---

# Trace Result Interpretation

Read the actual tool response before reporting success. Trace data may be wrapped
in `traceResults`; use the returned structure rather than assuming flat elements.
`elements` identify network features by `networkSourceId`, `globalId`, `objectId`,
and possibly `terminalId` and asset codes. Use returned `sourceMapping` and
`network_get_metadata` to resolve names where enrichment is absent.
Network source IDs, FeatureServer layer IDs, and browser map layer IDs are
different identifiers.

## Counts, functions, and phases

Count unique GlobalIDs for features while retaining terminal-level records.
`globalFunctionResults` can contain Sum, Count, Min, Max, or Average results and
conditions. Report the attribute, function, filters, and verified units; do not
label an unknown numeric load as kW. A named trace can have no functions or
barriers, and the presence of a function does not prove the requested scope.

Discover phase domains and propagators before decoding. If metadata establishes
the A=4, B=2, C=1 bitfield, combinations include ABC=7, AB=6, AC=5 and BC=3;
otherwise do not apply that encoding. Report raw values when interpretation is
unverified.

Use returned tier/subnetwork/controller metadata for hierarchy and boundary
interpretation. Do not infer tier rank meaning, controller identity, or energized
state from names alone. Traces describe the network model, not field confirmation.

## Diagnose failures without fabricated retries

Initialize the network session before diagnostic tools. Inspect warnings for dirty
areas/topology issues. Empty results can reflect a wrong start, terminal,
connectivity, configuration filters, or an actual empty traversal; do not report
every empty result as success or as a tier violation.

For terminal issues, inspect `network_device_terminals` and follow the
[terminal procedure](references/trace_terminals.md). Correct an unambiguous input
once, preserving the real start and service. For outside-tier errors, report the
actual message and known tier context; do not assume a distribution requirement.
For named-configuration errors, rediscover the live catalog in the execution
workflow rather than substituting a fixed example name.

When results are unexpectedly broad or omit expected assets, compare the saved
configuration's filters/barriers with the requested scope. Inspect
`network_query_associations` for relevant modeled connectivity/containment, but
do not claim associations prove energized connectivity. Retain successful partial
work while clearly marking failed traces or unresolved joins.

Lead with a plain-language finding, next diagnostic step, and a short labeled
error detail when useful. Authentication, service execution, or topology failures
are not permission to keep retrying unchanged inputs.
