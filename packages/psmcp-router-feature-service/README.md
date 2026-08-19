# psmcp-router-feature-service
PS-MCP router plugin: `feature-service`.
This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a
running PS-MCP server via a `psmcp.routers` entry point and is discovered
automatically once installed.
## Install
```bash
uv pip install psmcp-router-feature-service
# or, in the workspace:
uv sync --all-packages
```
## Usage
After install, the router shows up in:
```bash
psmcp router list
```
See the repo-level [README](../../README.md) and [docs/CREATING_A_ROUTER.md](../../docs/CREATING_A_ROUTER.md)
for the broader workflow. Environment variables specific to this router are
documented in the source-level README under `src/`.
