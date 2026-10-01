"""Canonical migration inventory, tool contracts, and public prompt compatibility."""

import re

import pytest
from fastmcp import Client, FastMCP
from psmcp_router_developer_tools.parsing import parse_front_matter
from psmcp_router_developer_tools.references import resolve_references
from psmcp_router_developer_tools.sources.package import PackageSkillSource
from psmcp_router_feature_service import feature_service_router
from psmcp_router_location_services import location_services_router
from psmcp_router_utilitynetwork import utility_network_service as utility

PROMPTS = {
    "utility_network_metadata_discovery": "metadata_discovery.md",
    "utility_network_downstream_customer_impact": "downstream_customer_impact.md",
    "utility_network_isolation_analysis": "isolation_analysis.md",
    "utility_network_spatial_impact": "spatial_impact_assessment.md",
    "utility_network_named_trace_execution": "named_trace_execution.md",
    "utility_network_customer_data_discovery": "customer_data_discovery.md",
    "utility_network_address_resolution": "address_to_network_element.md",
    "utility_network_trace_interpretation": "trace_interpretation.md",
}
MIGRATION = {
    "utility-network-named-trace": "named_trace_execution.md",
    "utility-network-trace": "downstream_customer_impact.md",
    "utility-network-trace-terminals": "named_trace_execution.md",
    "utility-network-trace-tier-gate": "named_trace_execution.md",
    "trace-error-handling": "trace_interpretation.md",
    "utility-feature-service-options": "metadata_discovery.md",
    "utility-service-discovery": "metadata_discovery.md",
    "utility-transformer-lookup": "transformer_lookup.md",
    "hurricane-utility-impact": "spatial_impact_assessment.md",
    "map-feature-pointing": "map_feature_pointing.md",
}


async def test_complete_canonical_inventory_and_real_tool_dependencies():
    source = PackageSkillSource("psmcp_router_utilitynetwork", "skills")
    skills = await source.load_skills()
    assert len(skills) == 11
    assert set(MIGRATION.values()).issubset({skill.file_path for skill in skills})
    assert {skill.file_path for skill in skills} == set(PROMPTS.values()) | {
        "transformer_lookup.md",
        "map_feature_pointing.md",
        "agent_system.md",
    }
    assert "blue-cats" not in {skill.metadata.name for skill in skills}
    system = [skill for skill in skills if "agent-system" in skill.metadata.tags]
    assert len(system) == 1 and system[0].file_path == "agent_system.md"
    root = FastMCP("contract-tools")
    root.mount(utility.utilitynetwork_router)
    root.mount(feature_service_router)
    root.mount(location_services_router)
    available = {tool.name for tool in await root.list_tools()}
    for skill in skills:
        assert set(skill.metadata.requires_tools).issubset(available)
        assert len({"agent-runtime", "agent-system"} & set(skill.metadata.tags)) == 1
        refs = await resolve_references(skill, source)
        for ref in refs:
            assert "content" in ref and "error" not in ref
        body = skill.content + "".join(ref["content"] for ref in refs)
        executable_mentions = set(
            re.findall(
                r"\b(network_[a-z_]+|query_feature_layer|get_service_or_layer_details|find_address_candidates|get_sample_feature_layer_data)\s*\(",
                body,
            )
        )
        assert executable_mentions.issubset(set(skill.metadata.requires_tools))
        assert "util-ent01" not in body and "mcp_une" not in body
        assert "findNearestTransformer" not in body
        assert "_validate_start_in_tier" not in body


@pytest.mark.parametrize(("prompt", "filename"), PROMPTS.items())
async def test_existing_public_prompts_use_same_canonical_content(prompt, filename):
    source = PackageSkillSource("psmcp_router_utilitynetwork", "skills")
    text = await source.read_file(filename)
    _, body = parse_front_matter(text)
    expected = utility._read_skill(filename)
    assert expected.startswith(body)
    assert not expected.startswith("---")
    async with Client(utility.utilitynetwork_router) as client:
        result = await client.get_prompt(prompt)
        assert result.messages[0].content.text == expected
    if "trace_terminals.md" in body:
        assert await source.read_file("references/trace_terminals.md") in expected


async def test_canonical_map_and_transformer_browser_boundary():
    source = PackageSkillSource("psmcp_router_utilitynetwork", "skills")
    map_text = await source.read_file("map_feature_pointing.md")
    for tool in (
        "getUserAddedContext",
        "getCurrentMapContext",
        "zoomTo",
        "highlightFeaturesByGlobalIds",
    ):
        assert tool in map_text
    transformer = await source.read_file("transformer_lookup.md")
    assert "network_find_nearest_transformers" in transformer
    assert "radius_meters=1609.344" in transformer
    assert "distanceMeters" in transformer
    assert "/3" not in transformer


def test_prompt_reference_containment():
    with pytest.raises(ValueError, match="escapes"):
        utility._read_skill("../utility-network-data-model.md")
