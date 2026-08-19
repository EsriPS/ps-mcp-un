"""Call network_device_terminals through the LIVE MCP server (exact prod path).

Run from ps-mcp-fork root while the server is up on :8888:
    uv run python scripts/probe_mcp_call.py
"""

from __future__ import annotations

import asyncio
import time

from fastmcp import Client

SAMPLE_GID = "{CBA08CEA-A8A9-4734-BC35-62F5FA47D006}"
SERVER = "http://localhost:8888/mcp"


async def main() -> None:
    async with Client(SERVER) as client:
        tools = await client.list_tools()
        print(f"tools: {[t.name for t in tools]}")

        for name, args in [
            ("network_list_named_traces", {}),
            ("network_device_terminals", {"global_id": SAMPLE_GID}),
        ]:
            t = time.perf_counter()
            try:
                res = await client.call_tool(name, args)
                dt = time.perf_counter() - t
                text = str(res.data)[:200] if hasattr(res, "data") else str(res)[:200]
                print(f"[{name}] {dt:.2f}s -> {text}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{name}] raised after {time.perf_counter() - t:.2f}s: {exc!r}")


if __name__ == "__main__":
    asyncio.run(main())
