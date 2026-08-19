"""Unit tests verifying ArcGIS router cleanup after map tool extraction.

These tests confirm that the map-opening tools, LLM modules, resources, and the
openai dependency have been removed from psmcp-router-arcgis, while the retained
portal/search/info tools remain registered and functional.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import asyncio
from pathlib import Path

ARCGIS_PACKAGE_DIR = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "psmcp-router-arcgis"
    / "src"
    / "psmcp_router_arcgis"
)

ARCGIS_PYPROJECT = (
    Path(__file__).resolve().parent.parent / "packages" / "psmcp-router-arcgis" / "pyproject.toml"
)


class TestRemovedTools:
    """Verify map-opening tools are NOT registered on the arcgis_router."""

    REMOVED_TOOLS = ("open_sample_map", "open_webmap", "open_layers_map")

    def test_removed_tools_not_registered(self):
        """Requirements 10.1: open_sample_map, open_webmap, open_layers_map must not exist."""
        from psmcp_router_arcgis import arcgis_router

        tool_names = [t.name for t in asyncio.run(arcgis_router.list_tools())]
        for tool_name in self.REMOVED_TOOLS:
            assert tool_name not in tool_names, (
                f"Tool '{tool_name}' should have been removed from arcgis_router"
            )


class TestRemovedModules:
    """Verify arcgis_llm.py and arcgis_resources.py no longer exist."""

    def test_arcgis_llm_does_not_exist(self):
        """Requirements 10.3: arcgis_llm.py must not exist."""
        llm_path = ARCGIS_PACKAGE_DIR / "arcgis_llm.py"
        assert not llm_path.exists(), f"{llm_path} should have been deleted"

    def test_arcgis_resources_does_not_exist(self):
        """Requirements 10.3: arcgis_resources.py must not exist."""
        resources_path = ARCGIS_PACKAGE_DIR / "arcgis_resources.py"
        assert not resources_path.exists(), f"{resources_path} should have been deleted"


class TestRemovedDependency:
    """Verify openai is NOT in the arcgis router's dependencies."""

    def test_openai_not_in_pyproject_dependencies(self):
        """Requirements 10.4: openai must not be a dependency of psmcp-router-arcgis."""
        content = ARCGIS_PYPROJECT.read_text(encoding="utf-8")
        # Check the dependencies section does not contain openai
        assert "openai" not in content, (
            "openai should have been removed from psmcp-router-arcgis/pyproject.toml"
        )


class TestRetainedTools:
    """Verify retained tools are still registered and callable."""

    RETAINED_TOOLS = (
        "get_user_info",
        "search_portal",
        "list_user_groups",
        "get_item_info",
        "list_system_services",
    )

    def test_retained_tools_are_registered(self):
        """Requirements 10.5: All portal/search/info tools must remain registered."""
        from psmcp_router_arcgis import arcgis_router

        tool_names = [t.name for t in asyncio.run(arcgis_router.list_tools())]
        for tool_name in self.RETAINED_TOOLS:
            assert tool_name in tool_names, (
                f"Tool '{tool_name}' should still be registered on arcgis_router"
            )
