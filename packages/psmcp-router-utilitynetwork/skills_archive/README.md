# Archived skills

Skill files kept for reference only. This folder is outside `src/`, so it is not
packaged into the wheel, not registered as an MCP prompt, and never served to agents.

| File | Archived | Replaced by | Reason |
|------|----------|-------------|--------|
| `isolation_analysis.md` | 2026-11-24 | `skills/utilitynetwork_trace.md`, section 3.6 (`utility_network_trace_guide` prompt) | Ran the same isolation trace through the older `network_trace` tool without the filter barrier that Esri requires for isolation traces. Its device filtering, presentation and troubleshooting steps were merged into section 3.6. |

To restore a skill, move it back to `src/psmcp_router_utilitynetwork/skills/` and
re-add its `@utilitynetwork_router.prompt` in `utility_network_service.py`.
