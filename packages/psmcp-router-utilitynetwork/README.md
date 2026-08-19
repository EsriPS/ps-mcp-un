# psmcp-router-utilitynetwork

PS-MCP router plugin: `utilitynetwork`.

This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a running
PS-MCP server via a `psmcp.routers` entry point and provides utility network trace
tools.

## Install

```bash
uv pip install psmcp-router-utilitynetwork
```

Or, in the workspace:

```bash
uv sync --all-packages
```

## Usage

After install, the router appears in:

```bash
psmcp router list
```

The package exposes the following tools:

- `network_downstream_trace`
- `network_upstream_trace`

See the repo-level [README](../../README.md) and [docs/CREATING_A_ROUTER.md](../../docs/CREATING_A_ROUTER.md)
for the broader router development workflow.
