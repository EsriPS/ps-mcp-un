---
name: utility-network-isolation-analysis
description: Analyze an isolation trace and identify protective-device candidates from verified network categories.
tags: [agent-runtime, utility-network, isolation]
requires_tools: [network_initialize_session, network_device_terminals, network_list_named_traces, network_named_trace, network_trace, network_get_metadata]
---

# Isolation Analysis

Establish the starting GlobalID and network FeatureServer, initialize the session,
then follow the [terminal procedure](references/trace_terminals.md) for the
intended isolation configuration. Use returned direction recommendations; ask
when a multi-terminal choice is ambiguous.

Discover saved configurations with `network_list_named_traces`. Prefer a matching
isolation configuration and call `network_named_trace` with the exact saved name.
Preserve its saved direction. If no saved configuration fits and a basic isolation
analysis is appropriate, use `network_trace(trace_type="isolation", ...)`.
Only pass domain/tier names discovered from metadata to tools supporting them.

Use `network_get_metadata(section="categories")` and asset-type metadata to
identify protective/isolation devices by actual category membership. Exclude the
starting feature when reporting surrounding devices, but retain it in the audit
of trace inputs. Do not classify every device as operable when category metadata
is unavailable; list unclassified candidates with that limitation.

Report candidate GlobalIDs, resolved source/asset names, configuration, terminal,
and warnings. Empty results may reflect connectivity, topology, start selection,
or the saved configuration; investigate rather than inventing an isolation
boundary. Broad results warrant checking the chosen scope and configuration.

This is network-model analysis, not an approved switching order or confirmation
that an asset is safe to operate. Explain the modeled boundary and defer physical
operations to authorized utility procedures.
