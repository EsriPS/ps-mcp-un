# Creating a Custom Router for PS-MCP

This guide walks through building your own router plugin as a standalone Python project, packaging it as a wheel, and registering it with a PS-MCP server.

## Overview

A PS-MCP router is a standard Python package that:

1. Depends on `ps-mcp` for shared utilities (token resolution, logging)
2. Exports a `FastMCP` instance as its router object
3. Declares a `psmcp.routers` entry point so the server discovers it automatically

No changes to the PS-MCP server source are needed.

## Step-by-step

### 1. Create the project structure

```
my-psmcp-router/
├── pyproject.toml
├── README.md
└── src/
    └── my_psmcp_router/
        ├── __init__.py
        └── service.py
```

### 2. Write `pyproject.toml`

```toml
[project]
name = "my-psmcp-router"
version = "0.1.0"
description = "Custom router plugin for PS-MCP"
requires-python = ">=3.13,<3.14"
dependencies = [
    "ps-mcp>=0.1.0,<1.0",           # shared auth + config utilities
    "httpx>=0.27.0",        # add any dependencies your router needs
]

[project.entry-points."psmcp.routers"]
my_router = "my_psmcp_router:router"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_psmcp_router"]
```

Key points:

- **`[project.entry-points."psmcp.routers"]`** — this is how the PS-MCP server discovers your router. The key (`my_router`) becomes the name shown in `psmcp router list`. The value (`my_psmcp_router:router`) is the `module:attribute` path to your `FastMCP` instance.
- **`ps-mcp`** as a dependency gives you access to `resolve_token`, `setup_logging`, and config utilities.

### 3. Write the router code

**`src/my_psmcp_router/service.py`**:

```python
"""My custom PS-MCP router."""

import logging
from typing import Optional

from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

logger = logging.getLogger(__name__)

router = FastMCP(name="My Custom Router")


@router.tool
async def my_tool(query: str, token: Optional[str] = None) -> dict:
    """
    A sample tool that does something useful.

    Args:
        query: The input query string.
        token: Optional ArcGIS token. Resolved automatically if not provided.

    Returns:
        Dict with results.
    """
    resolved_token = resolve_token(token)

    logger.info(f"my_tool called with query={query}")

    # Your implementation here
    return {
        "query": query,
        "result": "Hello from my custom router!",
        "authenticated": resolved_token is not None,
    }


@router.resource(uri="resource://my-router/info")
def my_info() -> str:
    """Provide information about this router."""
    return "This is my custom PS-MCP router plugin."


@router.prompt(name="my_prompt")
def my_prompt() -> str:
    """A prompt template for the custom router."""
    return (
        "You have access to my_tool which can process queries. "
        "Use it when the user asks about custom data."
    )
```

**`src/my_psmcp_router/__init__.py`**:

```python
"""My custom PS-MCP router plugin."""

from .service import router

__all__ = ["router"]
```

### 4. Build the wheel

```bash
cd my-psmcp-router

# Install build tool if needed
pip install build

# Build the wheel
python -m build
```

This produces a `.whl` file in `dist/`, e.g. `dist/my_psmcp_router-0.1.0-py3-none-any.whl`.

### 5. Install and register with PS-MCP

**Option A — Install manually, then enable:**

```bash
pip install dist/my_psmcp_router-0.1.0-py3-none-any.whl
psmcp router list      # should show "my_router" as discovered
psmcp router enable my_router
```

**Option B — Use the dev convenience command (installs + auto-enables):**

```bash
psmcp router install dist/my_psmcp_router-0.1.0-py3-none-any.whl
```

**Option C — Editable install for development:**

```bash
pip install -e /path/to/my-psmcp-router
psmcp router list      # my_router appears immediately
```

### 6. Verify

```bash
psmcp router list
```

Expected output:

```
Config dir: /home/user/.psmcp
Discovered 7 router(s):

  arcgis                          [enabled (all)]  (psmcp_router_arcgis:arcgis_router)
  feature_service                 [enabled (all)]  (psmcp_router_feature_service:feature_service_router)
  ...
  my_router                       [enabled (all)]  (my_psmcp_router:router)
```

Start the server and your tools, resources, and prompts are available:

```bash
psmcp serve
```

## Tips

### Token resolution

Always use `resolve_token()` from `psmcp.core.auth` instead of reading `ARCGIS_TOKEN` directly. It handles three tiers automatically:

1. Explicit `token` parameter passed to the tool
2. FastMCP auth context (per-request, when the server uses ArcGIS auth)
3. `ARCGIS_TOKEN` environment variable

### Logging

Don't call `setup_logging()` in your router — the server handles that. Just use:

```python
import logging
logger = logging.getLogger(__name__)
```

### Environment variables

Read config from `os.getenv(...)` at module level, matching the convention used by all built-in routers. Document your env vars in your router's `README.md`.

### MCP resources from files

If your router serves `.md` files as resources (common pattern for providing LLM context), read them relative to your module:

```python
import os

@router.resource(uri="resource://my-router/guide")
def my_guide() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    md_path = os.path.join(current_dir, "guide.md")
    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()
```

Include the `.md` files in your package so they're bundled in the wheel.

### HTTP clients

Use `httpx.AsyncClient` for async REST calls:

```python
import httpx

async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
    response = await client.get(url, params=params)
```

### Testing your router independently

You can test your router without the full PS-MCP server:

```python
import pytest
from my_psmcp_router import router

@pytest.mark.asyncio
async def test_my_tool():
    # FastMCP instances can be tested directly
    result = await my_tool("test query")
    assert result["query"] == "test query"
```

## Building a deployment package

Once your router is installed and enabled, use `psmcp build` to create a self-contained deployment package that includes your custom router alongside the built-in ones.

### From an editable install (development)

```bash
# Install your router in editable mode
pip install -e /path/to/my-psmcp-router

# Enable it
psmcp router enable my_router

# Build — your router's source is found automatically via package metadata
psmcp --env-file .env build
```

The build command locates your router's source directory from the editable install metadata and builds a fresh wheel from it.

### From a wheel install (no source)

```bash
# Install from a pre-built wheel
pip install my_psmcp_router-0.1.0-py3-none-any.whl

# Enable it
psmcp router enable my_router

# Build — falls back to pip wheel to rebuild from the installed package
psmcp --env-file .env build
```

### What the package contains

```
dist/ps-mcp-deploy-0.1.0-20260424/
  wheels/
    ps_mcp-0.1.0-py3-none-any.whl
    psmcp_router_arcgis-0.1.0-py3-none-any.whl
    psmcp_router_feature_service-0.1.0-py3-none-any.whl
    my_psmcp_router-0.1.0-py3-none-any.whl     ← your router
    ps_mcp-0.1.0-py3-none-any.whl
  install.sh           ← Linux/macOS installer
  install.ps1          ← Windows installer
  config/
    routers.json       ← captures which routers are enabled
  .env.sample
  ps-mcp.service
  nginx.conf

dist/ps-mcp-deploy-0.1.0-20260424.tar.gz       ← single archive to transfer
```

### Deploying to the target machine

```bash
# Transfer and extract
tar xzf ps-mcp-deploy-0.1.0-20260424.tar.gz
cd ps-mcp-deploy-0.1.0-20260424

# Install (creates venv, installs all wheels, copies config)
./install.sh /opt/ps-mcp

# Start
/opt/ps-mcp/.venv/bin/psmcp --env-file /opt/ps-mcp/.env serve
```

### Build options

```bash
psmcp build                                # build with default output to dist/
psmcp build --outdir /tmp/deploy           # custom output directory
psmcp build --include-deps                 # also download third-party deps for offline install
psmcp --env-file .env build                # load env (may set ENABLED_ROUTERS)
psmcp --config-dir /path/to/config build   # use a specific routers.json
```

The `--env-file` and `--config-dir` flags control which routers are included in the package — they determine enabled routers via the same priority chain used by `psmcp serve` (`ENABLED_ROUTERS` env → `routers.json` → all discovered).

## Docker / Kubernetes deployments

For containerized deployments, install your router wheel in the `Dockerfile`:

```dockerfile
FROM python:3.13-slim

# Install PS-MCP server (includes psmcp.core)
COPY wheels/ps_mcp-*.whl /tmp/wheels/
RUN pip install /tmp/wheels/*.whl

# Install your custom router
COPY wheels/my_psmcp_router-*.whl /tmp/wheels/
RUN pip install /tmp/wheels/my_psmcp_router-*.whl

# Enable routers via env var or mount a routers.json
ENV ENABLED_ROUTERS=feature_service,my_router

CMD ["psmcp", "serve"]
```

Or use `psmcp build` to create a deployment package containing all enabled router wheels, then copy the `wheels/` directory into your container build context.

Use `PSMCP_CONFIG_DIR` or `--config-dir` with a mounted `routers.json` for dynamic control in Kubernetes.

