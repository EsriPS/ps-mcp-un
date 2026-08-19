"""Integration test: list resources from a running MCP server.

Marked as ``integration`` so it is excluded from the default ``pytest`` run.
Start a server first (``psmcp serve``) and run with::

    pytest -m integration tests/test_resources.py
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_list_resources():
    """Connect to a running MCP server and enumerate resources, templates, and tools."""
    transport = StreamableHttpTransport(url="http://localhost:8888/mcp")

    async with Client(transport) as client:
        print("=== Server Info ===")
        print(f"Server: {client.initialize_result.serverInfo.name}")
        print(f"Version: {client.initialize_result.serverInfo.version}")
        print()

        print("=== Static Resources ===")
        resources = await client.list_resources()
        if resources:
            for resource in resources:
                print(f"  URI: {resource.uri}")
                print(f"  Name: {resource.name}")
                print(f"  Description: {resource.description}")
                print()
        else:
            print("  No static resources found.")
        print()

        print("=== Resource Templates ===")
        templates = await client.list_resource_templates()
        if templates:
            for template in templates:
                print(f"  URI Template: {template.uriTemplate}")
                print(f"  Name: {template.name}")
                print(f"  Description: {template.description}")
                print()
        else:
            print("  No resource templates found.")
        print()

        print("=== Tools ===")
        tools = await client.list_tools()
        if tools:
            for tool in tools:
                desc = tool.description or ""
                short = (desc[:80] + "...") if len(desc) > 80 else desc
                print(f"  Tool: {tool.name}")
                print(f"  Description: {short}")
                print()
        else:
            print("  No tools found.")


if __name__ == "__main__":
    asyncio.run(test_list_resources())
