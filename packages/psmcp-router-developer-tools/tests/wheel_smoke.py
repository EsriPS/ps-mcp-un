"""Run with Python -I -S and wheel-install/dependency site directories as arguments.

Using a dependency directory directly (not site.addsitedir) deliberately avoids
editable-install .pth files. Run from outside the server repository.
"""

import asyncio
import json
import os
import sys
from pathlib import Path


async def main() -> None:
    """Retrieve packaged instructions through the actual mounted MCP server."""
    installed, dependencies = (Path(argument).resolve() for argument in sys.argv[1:])
    sys.path[:0] = [str(installed), str(dependencies)]
    if sys.platform == "win32":
        sys.path.extend(
            str(dependencies / relative) for relative in ("win32", "win32/lib", "Pythonwin")
        )
        __import__("pywin32_bootstrap")
    import psmcp_router_developer_tools
    import psmcp_router_utilitynetwork
    from fastmcp import Client, FastMCP
    from psmcp_router_developer_tools.sources.package import PackageSkillSource

    import psmcp
    from psmcp import server

    for module in (psmcp, psmcp_router_developer_tools, psmcp_router_utilitynetwork):
        assert Path(module.__file__).is_relative_to(installed), module.__file__
    assert not any(Path(path).name == "src" for path in sys.path)
    source = PackageSkillSource("psmcp_router_utilitynetwork", "skills")
    documents = await source.load_skills()
    assert len(documents) == 11
    os.environ["DEVTOOLS_SKILL_SOURCES"] = json.dumps(
        [{"type": "package", "package": "psmcp_router_utilitynetwork", "path": "skills"}]
    )
    os.environ["ENABLED_ROUTERS"] = "developer_tools,utilitynetwork"
    root = FastMCP("wheel-smoke")
    assert server._load_and_mount_routers(root) == ["developer_tools", "utilitynetwork"]
    async with Client(root) as client:
        listing = (
            await client.call_tool("list_skills", {"tags": ["agent-runtime", "agent-system"]})
        ).data
        names = {entry["name"] for entry in listing["skills"]}
        assert "utility-network-system" in names
        assert "utility-network-named-trace" in names
        assert "utility-transformer-lookup" in names
        assert "blue-cats" not in names
        for name in names:
            result = (await client.call_tool("get_skill", {"name": name})).data
            assert result["content"] and "error" not in result
        trace = (await client.call_tool("get_skill", {"name": "utility-network-named-trace"})).data
        assert trace["references"][0]["path"] == "references/trace_terminals.md"
        prompts = await client.list_prompts()
        assert len(prompts) == 8
        for prompt in prompts:
            assert (await client.get_prompt(prompt.name)).messages[0].content.text
    print(
        f"WHEEL SMOKE PASSED: {len(documents)} packaged documents, {len(names)} published, 8 prompts; no editable imports."
    )


if __name__ == "__main__":
    asyncio.run(main())
