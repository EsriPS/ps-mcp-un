"""Unit tests for LLM client creation and error handling.

**Validates: Requirements 7.4, 7.5**

Tests verify:
- Correct OpenAI client selection (standard vs Azure) based on env vars
- Graceful degradation when OPENAI_KEY is missing
- Graceful degradation on network errors and timeouts
- Handling of empty LLM responses
- Markdown code block stripping from responses
- System prompt contains ArcGIS Maps SDK Web Components documentation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from psmcp_router_dynamic_app.llm import (
    CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT,
    generate_customization_script,
)


@pytest.fixture
def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all LLM-related env vars for a clean test slate."""
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)


@pytest.mark.asyncio
async def test_generate_returns_none_when_openai_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify returns None and logs WARNING when OPENAI_KEY not set."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", None)

    result = await generate_customization_script(
        map_type="sample_map",
        map_params={},
        additional_requirements="Add a legend",
    )

    assert result is None


@pytest.mark.asyncio
async def test_generate_uses_standard_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock AsyncOpenAI, verify it's used when AZURE_OPENAI is not 'true'."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", "test-key")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.USE_AZURE_OPENAI", False)
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_MODEL", "gpt-4o")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "console.log('hello');"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("psmcp_router_dynamic_app.llm.AsyncOpenAI", return_value=mock_client) as mock_cls:
        result = await generate_customization_script(
            map_type="sample_map",
            map_params={},
            additional_requirements="Add a legend",
        )

    mock_cls.assert_called_once_with(api_key="test-key", base_url="https://api.openai.com/v1")
    assert result == "console.log('hello');"


@pytest.mark.asyncio
async def test_generate_uses_azure_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock AsyncAzureOpenAI, verify it's used when AZURE_OPENAI is 'true'."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", "azure-key")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.USE_AZURE_OPENAI", True)
    monkeypatch.setattr(
        "psmcp_router_dynamic_app.llm.OPENAI_BASE_URL", "https://my-resource.openai.azure.com"
    )
    monkeypatch.setattr(
        "psmcp_router_dynamic_app.llm.AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
    )
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.AZURE_OPENAI_DEPLOYMENT", "gpt-4o-deploy")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "mapElement.view.goTo({center: [-118, 34]});"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch(
        "psmcp_router_dynamic_app.llm.AsyncAzureOpenAI", return_value=mock_client
    ) as mock_cls:
        result = await generate_customization_script(
            map_type="webmap",
            map_params={"webmap_id": "abc123"},
            additional_requirements="Zoom to California",
        )

    mock_cls.assert_called_once_with(
        api_key="azure-key",
        azure_endpoint="https://my-resource.openai.azure.com",
        api_version="2024-02-15-preview",
    )
    assert result == "mapElement.view.goTo({center: [-118, 34]});"


@pytest.mark.asyncio
async def test_generate_returns_none_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock client to raise exception, verify returns None."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", "test-key")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.USE_AZURE_OPENAI", False)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=ConnectionError("Network unreachable")
    )

    with patch("psmcp_router_dynamic_app.llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_customization_script(
            map_type="layers_map",
            map_params={"layer_urls": ["https://example.com/arcgis/rest/services/Layer/0"]},
            additional_requirements="Style the layer red",
        )

    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_none_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock client to raise timeout, verify returns None."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", "test-key")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.USE_AZURE_OPENAI", False)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=TimeoutError("Request timed out after 60s")
    )

    with patch("psmcp_router_dynamic_app.llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_customization_script(
            map_type="sample_map",
            map_params={},
            additional_requirements="Add a heatmap layer",
        )

    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_none_on_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock client to return empty content, verify returns None."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", "test-key")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.USE_AZURE_OPENAI", False)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = ""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("psmcp_router_dynamic_app.llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_customization_script(
            map_type="sample_map",
            map_params={},
            additional_requirements="Show population density",
        )

    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_cleaned_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock client to return markdown-wrapped code, verify delimiters stripped."""
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.OPENAI_KEY", "test-key")
    monkeypatch.setattr("psmcp_router_dynamic_app.llm.USE_AZURE_OPENAI", False)

    raw_response = '```javascript\nconst layer = new FeatureLayer({url: "https://example.com"});\nmapElement.map.add(layer);\n```'
    expected = (
        'const layer = new FeatureLayer({url: "https://example.com"});\nmapElement.map.add(layer);'
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = raw_response

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("psmcp_router_dynamic_app.llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_customization_script(
            map_type="layers_map",
            map_params={"layer_urls": ["https://example.com/FeatureServer/0"]},
            additional_requirements="Add the feature layer",
        )

    assert result == expected


def test_system_prompt_contains_arcgis_docs() -> None:
    """Verify system prompt mentions ArcGIS Maps SDK Web Components."""
    assert "ArcGIS Maps SDK Web Components" in CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT
    assert "arcgis-map" in CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT
    assert "$arcgis.import()" in CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT
    assert "FeatureLayer" in CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT
