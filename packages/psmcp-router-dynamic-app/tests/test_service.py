"""Unit tests for tool happy paths and error paths in service.py.

**Validates: Requirements 4.1, 4.2, 5.1, 5.3, 5.7, 6.1, 6.6, 12.1, 12.2, 12.3**

Tests verify:
- open_sample_map returns correct ToolResult structure
- open_sample_map includes additional_requirements in data
- open_webmap with valid params returns correct data
- open_webmap with empty/whitespace webmap_id raises ToolError
- open_webmap with missing portal_url raises ToolError
- open_webmap falls back to ARCGIS_PORTAL_URL env var
- open_layers_map with valid params returns correct data
- open_layers_map with empty list raises ToolError
- open_layers_map with mismatched where clauses raises ToolError
- open_layers_map with matching where clauses includes both in data
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError
from psmcp_router_dynamic_app.service import (
    open_layers_map,
    open_sample_map,
    open_webmap,
)


@pytest.fixture(autouse=True)
def _mock_resolve_token():
    """Mock resolve_token to return None by default for all tests."""
    with patch("psmcp_router_dynamic_app.service.resolve_token", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _mock_generate_customization_script():
    """Mock generate_customization_script to return None by default for all tests."""
    with patch("psmcp_router_dynamic_app.service.generate_customization_script", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _clear_portal_env(monkeypatch: pytest.MonkeyPatch):
    """Clear ARCGIS_PORTAL_URL so tests control it explicitly."""
    monkeypatch.setattr("psmcp_router_dynamic_app.service.ARCGIS_PORTAL_URL", None)


@pytest.mark.asyncio
async def test_open_sample_map_basic() -> None:
    """Call open_sample_map with no args, verify ToolResult has text + JSON content and meta."""
    result = await open_sample_map()

    assert len(result.content) == 2

    # First content block is human-readable text
    assert result.content[0].type == "text"
    assert "sample" in result.content[0].text.lower()

    # Second content block is JSON data
    assert result.content[1].type == "text"
    data = json.loads(result.content[1].text)
    assert data["type"] == "sample_map"

    # Meta contains resourceUri
    assert result.meta is not None
    assert result.meta["ui"]["resourceUri"] == "ui://dynamic-app/map-viewer.html"


@pytest.mark.asyncio
async def test_open_sample_map_with_additional_requirements() -> None:
    """Verify additional_requirements is included in the tool result data."""
    result = await open_sample_map(additional_requirements="Add a legend and scale bar")

    data = json.loads(result.content[1].text)
    assert data["type"] == "sample_map"
    assert data["additional_requirements"] == "Add a legend and scale bar"


@pytest.mark.asyncio
async def test_open_webmap_valid_params() -> None:
    """Call open_webmap with webmap_id + portal_url, verify data contains both."""
    result = await open_webmap(
        webmap_id="abc123def456",
        portal_url="https://www.arcgis.com",
    )

    assert len(result.content) == 2

    data = json.loads(result.content[1].text)
    assert data["type"] == "webmap"
    assert data["webmap_id"] == "abc123def456"
    assert data["portal_url"] == "https://www.arcgis.com"

    # Meta contains resourceUri
    assert result.meta is not None
    assert result.meta["ui"]["resourceUri"] == "ui://dynamic-app/map-viewer.html"


@pytest.mark.asyncio
async def test_open_webmap_empty_webmap_id_returns_error() -> None:
    """Empty string webmap_id raises ToolError."""
    with pytest.raises(ToolError, match="webmap_id must not be empty"):
        await open_webmap(
            webmap_id="",
            portal_url="https://www.arcgis.com",
        )


@pytest.mark.asyncio
async def test_open_webmap_whitespace_webmap_id_returns_error() -> None:
    """Whitespace-only webmap_id raises ToolError."""
    with pytest.raises(ToolError, match="webmap_id must not be empty"):
        await open_webmap(
            webmap_id="   \t  ",
            portal_url="https://www.arcgis.com",
        )


@pytest.mark.asyncio
async def test_open_webmap_missing_portal_url_returns_error() -> None:
    """No portal_url param and no env var raises ToolError."""
    with pytest.raises(ToolError, match=r"[Nn]o portal URL available"):
        await open_webmap(
            webmap_id="abc123",
            portal_url=None,
        )


@pytest.mark.asyncio
async def test_open_webmap_falls_back_to_env_portal_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set ARCGIS_PORTAL_URL via module attr, verify it's used when portal_url not provided."""
    monkeypatch.setattr(
        "psmcp_router_dynamic_app.service.ARCGIS_PORTAL_URL",
        "https://portal.example.com/portal",
    )

    result = await open_webmap(
        webmap_id="xyz789",
        portal_url=None,
    )

    data = json.loads(result.content[1].text)
    assert data["portal_url"] == "https://portal.example.com/portal"
    assert data["webmap_id"] == "xyz789"


@pytest.mark.asyncio
async def test_open_layers_map_valid_params() -> None:
    """Call open_layers_map with layer_urls, verify data contains them."""
    layer_urls = [
        "https://services.arcgis.com/rest/services/Parcels/FeatureServer/0",
        "https://services.arcgis.com/rest/services/Roads/MapServer/1",
    ]

    result = await open_layers_map(layer_urls=layer_urls)

    assert len(result.content) == 2

    data = json.loads(result.content[1].text)
    assert data["type"] == "layers_map"
    assert data["layer_urls"] == layer_urls

    # Meta contains resourceUri
    assert result.meta is not None
    assert result.meta["ui"]["resourceUri"] == "ui://dynamic-app/map-viewer.html"


@pytest.mark.asyncio
async def test_open_layers_map_empty_list_returns_error() -> None:
    """Empty layer_urls list raises ToolError."""
    with pytest.raises(ToolError, match="at least one URL"):
        await open_layers_map(layer_urls=[])


@pytest.mark.asyncio
async def test_open_layers_map_mismatched_where_clauses_returns_error() -> None:
    """layer_where_clauses with different length than layer_urls raises ToolError."""
    with pytest.raises(ToolError, match="must match layer_urls length"):
        await open_layers_map(
            layer_urls=[
                "https://services.arcgis.com/rest/services/Parcels/FeatureServer/0",
                "https://services.arcgis.com/rest/services/Roads/MapServer/1",
            ],
            layer_where_clauses=["ZONE='R1'"],  # Only 1 clause for 2 URLs
        )


@pytest.mark.asyncio
async def test_open_layers_map_with_where_clauses() -> None:
    """Matching lengths of layer_urls and layer_where_clauses, verify both in data."""
    layer_urls = [
        "https://services.arcgis.com/rest/services/Parcels/FeatureServer/0",
        "https://services.arcgis.com/rest/services/Roads/MapServer/1",
    ]
    where_clauses = ["ZONE='R1'", "TYPE='Highway'"]

    result = await open_layers_map(
        layer_urls=layer_urls,
        layer_where_clauses=where_clauses,
    )

    data = json.loads(result.content[1].text)
    assert data["type"] == "layers_map"
    assert data["layer_urls"] == layer_urls
    assert data["layer_where_clauses"] == where_clauses
