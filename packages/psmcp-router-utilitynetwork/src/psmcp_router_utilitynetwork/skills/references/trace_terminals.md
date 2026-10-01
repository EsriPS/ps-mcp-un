# Terminal selection for every trace

Call `network_device_terminals(global_id=..., network_service_url=...)` for the
chosen feature. Use the returned `terminals`, not a remembered numeric ID.

- One terminal: copy its `terminalId`.
- Multiple terminals: prefer a unique `recommendedFor` matching the intended
  direction (downstream versus upstream/isolation). If direction is absent,
  conflicting, or ambiguous, present terminal names/IDs and ask the user.
  Do not choose the first list entry arbitrarily.
- No terminals on a successfully resolved feature: omit `terminal_id`.
  An error or unresolved feature is not evidence that there are no terminals.
  Junctions do not receive an invented terminal 1.
- For edge starts, consult the called tool's `percent_along` schema. Do not
  pretend that the named-trace tool accepts that argument.

Keep the service, GlobalID, selected terminal, and intended trace together.
Re-resolve when the starting feature or service changes.
