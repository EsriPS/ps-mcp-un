"""Connectivity smoke test for the eval harness (no LLM required).

Verifies the harness can:
  1. Connect to the configured MCP server with the bearer token.
  2. Discover tools, resources, and prompts (the "discovery surface").
  3. Actually call a tool (network_initialize_session) and get a result.

This exercises everything in the pipeline except the LLM agent loop, so it can
run without an OPENAI_KEY. Use it to confirm auth + transport + tool dispatch
before doing a full model-driven run.

Usage:
    uv run python packages/psmcp-router-utilitynetwork/tests/evals/smoke_connect.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config  # noqa: E402
from runner import _make_client  # noqa: E402


async def main() -> int:
    cfg = load_config()
    if not cfg.mcp_token:
        print("ERROR: no token (set EVAL_MCP_TOKEN or ARCGIS_TOKEN)")
        return 1

    print(f"Connecting to {cfg.mcp_url} ...")
    async with _make_client(cfg) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        print(f"\nTools ({len(tools)}):")
        for t in tools:
            print(f"  - {t.name}")
        print(f"\nResources ({len(resources)}):")
        for r in resources:
            print(f"  - {r.uri}")
        print(f"\nPrompts ({len(prompts)}):")
        for p in prompts:
            print(f"  - {p.name}")

        print("\nCalling network_initialize_session ...")
        result = await client.call_tool("network_initialize_session", {})
        data = getattr(result, "data", None) or {}
        initialized = data.get("initialized") if isinstance(data, dict) else None
        guidance = data.get("guidance", "") if isinstance(data, dict) else ""
        print(f"  initialized: {initialized}")
        print(f"  guidance length: {len(guidance)} chars")

    print("\nSMOKE OK: connection, discovery, and tool call all succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
