# Named Trace Execution Workflow

You are discovering and executing a named trace configuration for a complex network analysis.

## When to Use

Use named traces when the workflow requires barriers, functions (load sums, customer counts), propagators, or output filters. Named traces are authored by utility engineers with deployment-specific knowledge.

**Note:** The Downstream Customer Impact and Isolation Analysis skills already include a named-trace check in their Step 2. Use this prompt independently when the user explicitly asks to run a named trace, or when no other workflow skill applies.

## Steps

1. **Discover available named traces:**
   Call `network_list_named_traces()`.
   - Note each trace's `name`, `description`, `traceType`

2. **Match to user intent:**
   - Compare trace names/descriptions to what the user is asking
   - Check `traceType` aligns with the needed direction (downstream, upstream, isolation, etc.)
   - If multiple candidates: present options to user

3. **Resolve the starting feature's terminal:**
   Call `network_device_terminals(global_id="{GlobalID}")`.
   - Match terminal direction to the trace's `traceType`:
     - downstream trace → DOWNSTREAM terminal (`recommendedFor = "downstream"`)
     - upstream/isolation trace → UPSTREAM terminal (`recommendedFor = "upstream"`)
   - If ambiguous: ask the user

4. **Execute the named trace:**
   Call `network_named_trace(named_trace_name="{name}", starting_global_id="{GlobalID}", terminal_id={id})`.
   - Do NOT pass `trace_type` unless overriding the saved direction

5. **Interpret results:**
   - `elements`: features the trace traversed (use `sourceMapping` to identify layers)
   - `globalFunctionResults`: aggregated values (load sums, counts, etc.)
   - Report function results in plain language: "Total connected load: X kW (from 'Service Load' Sum)"

## Fallback

If NO named trace matches the user's intent:
- Use `network_downstream_trace`, `network_upstream_trace`, or `network_trace` for simple traces
- These do NOT include barriers, functions, or propagators
- If complex config is needed but no named trace exists: recommend the GIS admin publish one
