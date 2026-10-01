"""Frozen runtime delivery contract: local/package sources and real MCP calls."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastmcp import Client, FastMCP
from psmcp_router_developer_tools import service
from psmcp_router_developer_tools.cache import TTLCache
from psmcp_router_developer_tools.capabilities import SkillPublicationMiddleware, publication_root
from psmcp_router_developer_tools.config import load_skill_sources
from psmcp_router_developer_tools.parsing import parse_skill_file
from psmcp_router_developer_tools.references import resolve_references
from psmcp_router_developer_tools.registry import SkillRegistry
from psmcp_router_developer_tools.sources.github import GitHubSkillSource
from psmcp_router_developer_tools.sources.local import LocalSkillSource
from psmcp_router_developer_tools.sources.package import PackageSkillSource


def document(name="fixture-trace", body="Use returned terminal IDs.", **metadata):
    """Make YAML from JSON-compatible metadata without scalar quoting ambiguity."""
    fields = {
        "name": name,
        "description": "Trace fixtures safely.",
        "tags": ["agent-runtime"],
        **metadata,
    }
    return (
        "---\n"
        + "\n".join(f"{key}: {json.dumps(value)}" for key, value in fields.items())
        + "\n---\n"
        + body
    )


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    monkeypatch.setattr(service, "_skill_registry", None)
    monkeypatch.delenv("DEVTOOLS_SKILL_SOURCES", raising=False)


@pytest.mark.parametrize(
    "value",
    [
        "oops",
        "{}",
        "[null]",
        '[{"type":"wrong"}]',
        '[{"type":"local"}]',
        '[{"type":"package","package":"x"}]',
        '[{"type":"github","url":2}]',
    ],
)
def test_invalid_source_configuration_is_visible(monkeypatch, value):
    monkeypatch.setenv("DEVTOOLS_SKILL_SOURCES", value)
    with pytest.raises(ValueError):
        load_skill_sources()


@pytest.mark.parametrize(
    "metadata",
    [
        {"name": "Not-Kebab"},
        {"name": "a" * 65},
        {"description": ""},
        {"description": ["wrong"]},
        {"description": "x" * 1025},
        {"tags": ["agent-runtime", "agent-system"]},
        {"requires_tools": "network_named_trace"},
        {"requires_tools": [3]},
    ],
)
def test_invalid_runtime_metadata_fails(metadata):
    with pytest.raises(ValueError):
        parse_skill_file(document(**metadata), "SKILL.md", "fixture")


async def test_references_are_transitive_normalized_and_cycle_safe(tmp_path):
    (tmp_path / "references").mkdir()
    (tmp_path / "SKILL.md").write_text(document(body="Use [rules](./references/rules.md)."))
    (tmp_path / "references" / "rules.md").write_text("[next](../details.md)")
    (tmp_path / "details.md").write_text("[root](SKILL.md) and [same](references/./rules.md)")
    source = LocalSkillSource(str(tmp_path))
    skill = (await source.load_skills())[0]
    refs = await resolve_references(skill, source)
    assert [ref["path"] for ref in refs] == ["references/rules.md", "details.md"]


async def test_nonstandard_root_filename_cycles_deliver_required_alias(tmp_path):
    (tmp_path / "workflow.md").write_text(document(body="[rules](rules.md)"))
    (tmp_path / "rules.md").write_text("[back](workflow.md)")
    source = LocalSkillSource(str(tmp_path))
    skill = (await source.load_skills())[0]
    refs = await resolve_references(skill, source)
    assert [ref["path"] for ref in refs] == ["rules.md", "workflow.md"]
    assert "name: " in refs[1]["content"]


@pytest.mark.parametrize(
    "reference",
    [
        "../escape.md",
        "/absolute.md",
        "C:/drive.md",
        r"references\bad.md",
        "%2e%2e/escape.md",
        "image.png",
        "scripts/run.mjs",
        "missing.md",
        ".hidden/rules.md",
        "file:///absolute.md",
        "rules.md?query=1",
    ],
)
async def test_unsafe_missing_or_unsupported_references_fail(tmp_path, reference):
    source = LocalSkillSource(str(tmp_path))
    skill = parse_skill_file(document(body=f"[rules]({reference})"), "SKILL.md", "fixture")
    with pytest.raises(ValueError):
        await resolve_references(skill, source)


async def test_eight_reference_edges_allowed_ninth_fails(tmp_path):
    source = LocalSkillSource(str(tmp_path))
    skill = parse_skill_file(document(body="[one](1.md)"), "SKILL.md", "fixture")
    for index in range(1, 9):
        (tmp_path / f"{index}.md").write_text(f"[next]({index + 1}.md)" if index < 8 else "end")
    assert len(await resolve_references(skill, source)) == 8
    (tmp_path / "8.md").write_text("[ninth](9.md)")
    (tmp_path / "9.md").write_text("too deep")
    with pytest.raises(ValueError, match="depth exceeds 8"):
        await resolve_references(skill, source)


async def test_https_citations_and_local_reference_definitions(tmp_path):
    (tmp_path / "rules.md").write_text("rules")
    skill = parse_skill_file(
        document(body="[site](https://example.invalid)\n[rules][r]\n[r]: rules.md"),
        "SKILL.md",
        "fixture",
    )
    refs = await resolve_references(skill, LocalSkillSource(str(tmp_path)))
    assert [ref["path"] for ref in refs] == ["rules.md"]


async def test_case_collisions_and_virtual_file_collision(tmp_path):
    (tmp_path / "rules.md").write_text("rules")
    skill = parse_skill_file(document(body="[a](rules.md) [b](RULES.md)"), "main.md", "fixture")
    with pytest.raises(ValueError, match="Case-colliding"):
        await resolve_references(skill, LocalSkillSource(str(tmp_path)))
    skill = replace(skill, content="[bad](SKILL.md)")
    with pytest.raises(ValueError, match="collides"):
        await resolve_references(skill, LocalSkillSource(str(tmp_path)))


async def test_duplicate_names_fail_before_filtering(tmp_path):
    for name, title in [("a.md", "Duplicate"), ("b.md", "duplicate")]:
        (tmp_path / name).write_text(f"---\nname: {title}\n---\nBody")
    registry = SkillRegistry([LocalSkillSource(str(tmp_path))])
    with pytest.raises(ValueError, match="Duplicate skill"):
        await registry.list_skills(tags=["agent-system"])
    (tmp_path / "b.md").unlink()
    registry = SkillRegistry([LocalSkillSource(str(tmp_path)), LocalSkillSource(str(tmp_path))])
    with pytest.raises(ValueError, match="Duplicate skill"):
        await registry.get_skill("duplicate")


async def test_local_refresh_add_edit_remove(tmp_path):
    source = LocalSkillSource(str(tmp_path))
    registry = SkillRegistry([source])
    assert await registry.list_skills() == []
    path = tmp_path / "SKILL.md"
    path.write_text(document(body="first"))
    assert (await registry.get_skill("fixture-trace"))[0].content == "first"
    path.write_text(document(body="edited"))
    assert (await registry.get_skill("fixture-trace"))[0].content == "edited"
    path.unlink()
    assert await registry.list_skills() == []


async def test_root_context_uses_actual_mounted_tools(tmp_path, monkeypatch):
    (tmp_path / "SKILL.md").write_text(document(requires_tools=["network_named_trace"]))
    monkeypatch.setenv(
        "DEVTOOLS_SKILL_SOURCES", json.dumps([{"type": "local", "path": str(tmp_path)}])
    )
    root = FastMCP("test-root")
    root.add_middleware(SkillPublicationMiddleware())
    root.mount(service.developer_tools_router)
    async with Client(root) as client:
        result = await client.call_tool("list_skills", {"tags": ["agent-runtime", "agent-system"]})
        assert result.data["skills"] == []
        assert "error" in (await client.call_tool("get_skill", {"name": "fixture-trace"})).data

    @root.tool
    def network_named_trace() -> dict:
        return {}

    async with Client(root) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert set(tools["list_skills"].inputSchema["properties"]) == {"tags"}
        assert set(tools["get_skill"].inputSchema["properties"]) == {"name"}
        listing = (await client.call_tool("list_skills", {"tags": ["agent-runtime"]})).data
        assert listing["skills"][0]["requires_tools"] == ["network_named_trace"]
        result = await client.call_tool("get_skill", {"name": "fixture-trace"})
        assert result.structured_content["name"] == "fixture-trace"
        assert json.loads(result.content[0].text)["content"] == "Use returned terminal IDs."


async def test_configured_failure_is_mcp_error(monkeypatch):
    monkeypatch.setenv("DEVTOOLS_SKILL_SOURCES", "invalid")
    async with Client(service.developer_tools_router) as client:
        result = await client.call_tool("list_skills", {}, raise_on_error=False)
        assert result.is_error


async def test_shared_router_requests_do_not_mix_root_capabilities(tmp_path, monkeypatch):
    (tmp_path / "SKILL.md").write_text(document(requires_tools=["network_named_trace"]))
    monkeypatch.setenv(
        "DEVTOOLS_SKILL_SOURCES", json.dumps([{"type": "local", "path": str(tmp_path)}])
    )
    roots = [FastMCP("client-a"), FastMCP("client-b")]
    for root in roots:
        root.mount(service.developer_tools_router)
        root.add_middleware(SkillPublicationMiddleware())

    @roots[0].tool
    def network_named_trace() -> dict:
        return {}

    async def discover(root):
        async with Client(root) as client:
            return (await client.call_tool("list_skills", {})).data["total"]

    assert await asyncio.gather(*(discover(root) for root in roots)) == [1, 0]
    assert publication_root.get() is None


async def test_transitive_untagged_developer_references_remain_compatible(tmp_path):
    (tmp_path / "first.md").write_text("[second](second.md)")
    (tmp_path / "second.md").write_text("[first](first.md)")
    skill = parse_skill_file(
        "---\nname: Developer Guide\n---\n[first](./first.md)", "main.md", "fixture"
    )
    refs = await resolve_references(skill, LocalSkillSource(str(tmp_path)))
    assert [entry["path"] for entry in refs] == ["./first.md", "second.md"]


async def test_reference_cannot_escape_nested_document_via_symlink(tmp_path, monkeypatch):
    directory = tmp_path / "nested"
    directory.mkdir()
    target = directory / "rules.md"
    target.write_text("rules")
    source = LocalSkillSource(str(tmp_path))
    original = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path, *a, **k: tmp_path / "other.md" if path == target else original(path, *a, **k),
    )
    skill = parse_skill_file(document(body="[rules](rules.md)"), "nested/SKILL.md", "fixture")
    with pytest.raises(ValueError, match="document directory"):
        await resolve_references(skill, source)


async def test_package_selection_and_successful_root_mounts(monkeypatch):
    from psmcp_router_utilitynetwork import utilitynetwork_router

    from psmcp import server

    eps = {
        "developer_tools": SimpleNamespace(
            value="psmcp_router_developer_tools:developer_tools_router",
            load=lambda: service.developer_tools_router,
        ),
        "utilitynetwork": SimpleNamespace(
            value="psmcp_router_utilitynetwork:utilitynetwork_router",
            load=lambda: utilitynetwork_router,
        ),
    }
    monkeypatch.setattr(server, "_discover_routers", lambda: eps)
    monkeypatch.setenv(
        "DEVTOOLS_SKILL_SOURCES",
        json.dumps(
            [{"type": "package", "package": "psmcp_router_utilitynetwork", "path": "skills"}]
        ),
    )
    monkeypatch.setenv("ENABLED_ROUTERS", "developer_tools")
    root = FastMCP("disabled-owner")
    server._load_and_mount_routers(root)
    async with Client(root) as client:
        assert (await client.call_tool("list_skills", {})).data["skills"] == []

    monkeypatch.setenv("ENABLED_ROUTERS", "developer_tools,utilitynetwork")
    root = FastMCP("mounted-owner")
    server._load_and_mount_routers(root)
    async with Client(root) as client:
        names = {
            skill["name"] for skill in (await client.call_tool("list_skills", {})).data["skills"]
        }
        assert "utility-network-system" in names
        assert "utility-network-named-trace" in names
        assert "utility-transformer-lookup" in names
        assert "utility-network-address-resolution" not in names  # geocoder absent
        assert "utility-service-discovery" not in names  # feature service absent

    eps["utilitynetwork"].load = lambda: (_ for _ in ()).throw(RuntimeError("mount failed"))
    root = FastMCP("failed-owner")
    server._load_and_mount_routers(root)
    async with Client(root) as client:
        assert (await client.call_tool("list_skills", {})).data["skills"] == []


@pytest.mark.parametrize(
    "path", ["../skills", "/skills", r"skills\other", "C:/skills", "%2e%2e", ".hidden"]
)
def test_package_path_rejects_unsafe_values(path):
    with pytest.raises(ValueError):
        PackageSkillSource("psmcp_router_utilitynetwork", path)


def test_missing_package_and_missing_package_directory_fail():
    with pytest.raises(ModuleNotFoundError):
        PackageSkillSource("nonexistent_fixture_package", "skills")
    with pytest.raises(FileNotFoundError):
        PackageSkillSource("psmcp_router_utilitynetwork", "nonexistent")


async def test_blue_cats_fixture_keeps_all_assets_but_never_executes_them():
    directory = Path(__file__).parent / "fixtures" / "blue-cats"
    source = LocalSkillSource(str(directory))
    skill = (await source.load_skills())[0]
    refs = await resolve_references(skill, source)
    assert len(refs) == 2
    assert (directory / "scripts" / "blue-cat-answer.mjs").is_file()
    runtime = replace(skill, metadata=replace(skill.metadata, tags=["agent-runtime"]))
    with pytest.raises(ValueError, match="Unsupported local skill asset"):
        await resolve_references(runtime, source)
    markdown_only = replace(
        runtime,
        content="\n".join(
            line for line in runtime.content.splitlines() if "[blue-cat-answer.mjs]" not in line
        ),
    )
    assert len(await resolve_references(markdown_only, source)) == 2


async def test_reference_symlink_cannot_escape_skill_source(tmp_path, monkeypatch):
    source = LocalSkillSource(str(tmp_path))
    target = tmp_path / "reference.md"
    target.write_text("inside")
    original = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path, *a, **k: (
            tmp_path.parent / "outside.md" if path == target else original(path, *a, **k)
        ),
    )
    with pytest.raises(ValueError, match="escapes"):
        await source.read_file("reference.md")


async def test_github_configured_http_failures_propagate_without_live_network(monkeypatch):
    source = GitHubSkillSource("https://github.com/fixture/skills", TTLCache(60), ref="main")
    request = httpx.Request("GET", "https://api.github.com/fixture")
    response = httpx.Response(500, request=request)
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))
    with pytest.raises(httpx.HTTPStatusError):
        await source.load_skills()
