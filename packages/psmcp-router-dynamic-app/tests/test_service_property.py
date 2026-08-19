"""Property-based tests for service.py tool invocations.

Feature: dynamic-application-router
"""

from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from psmcp_router_dynamic_app.service import open_layers_map, open_sample_map, open_webmap

# --- Strategies ---

# Valid non-empty text for webmap_id
_webmap_id_strategy = st.text(
    alphabet=st.characters(categories=("L", "N"), exclude_characters="\x00"),
    min_size=1,
    max_size=40,
)

# Valid HTTP/HTTPS portal URLs
_portal_url_strategy = st.from_regex(
    r"https?://[a-z][a-z0-9\-]{0,15}\.[a-z]{2,6}(/[a-z0-9\-]{1,15}){0,3}",
    fullmatch=True,
)

# Valid layer URL lists (1-5 items for test speed)
_layer_urls_strategy = st.lists(
    st.from_regex(
        r"https://[a-z][a-z0-9]{0,10}\.[a-z]{2,6}/[a-z]+/rest/services/\w{1,10}/MapServer",
        fullmatch=True,
    ),
    min_size=1,
    max_size=5,
)

# Optional additional_requirements (short for speed, within 2000 char limit)
_additional_requirements_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(categories=("L", "N", "Z"), exclude_characters="\x00"),
        min_size=1,
        max_size=100,
    ),
)


# Optional layer_where_clauses that match layer_urls length
@st.composite
def _matching_where_clauses(draw, layer_urls):
    """Generate optional where clauses matching the length of layer_urls."""
    include = draw(st.booleans())
    if not include:
        return None
    return draw(
        st.lists(
            st.text(min_size=0, max_size=30),
            min_size=len(layer_urls),
            max_size=len(layer_urls),
        )
    )


EXPECTED_RESOURCE_URI = "ui://dynamic-app/map-viewer.html"


# Feature: dynamic-application-router, Property 1: Static Resource URI Invariant
class TestStaticResourceURIInvariant:
    """Property 1: Static Resource URI Invariant.

    For any valid tool invocation (open_sample_map, open_webmap, or open_layers_map)
    with any valid parameters, the returned ToolResult _meta.ui.resourceUri SHALL
    always equal "ui://dynamic-app/map-viewer.html".

    **Validates: Requirements 2.2, 2.4**
    """

    @settings(max_examples=100)
    @given(additional_requirements=_additional_requirements_strategy)
    @pytest.mark.asyncio
    async def test_open_sample_map_resource_uri(self, additional_requirements: str | None) -> None:
        """open_sample_map always returns resourceUri = "ui://dynamic-app/map-viewer.html".

        **Validates: Requirements 2.2**
        """
        with (
            patch("psmcp_router_dynamic_app.service.resolve_token", return_value=None),
            patch(
                "psmcp_router_dynamic_app.service.generate_customization_script",
                return_value=None,
            ),
        ):
            result = await open_sample_map(additional_requirements=additional_requirements)

        assert result.meta is not None
        assert result.meta["ui"]["resourceUri"] == EXPECTED_RESOURCE_URI

    @settings(max_examples=100)
    @given(
        webmap_id=_webmap_id_strategy,
        portal_url=_portal_url_strategy,
        additional_requirements=_additional_requirements_strategy,
    )
    @pytest.mark.asyncio
    async def test_open_webmap_resource_uri(
        self, webmap_id: str, portal_url: str, additional_requirements: str | None
    ) -> None:
        """open_webmap always returns resourceUri = "ui://dynamic-app/map-viewer.html".

        **Validates: Requirements 2.2**
        """
        with (
            patch("psmcp_router_dynamic_app.service.resolve_token", return_value=None),
            patch(
                "psmcp_router_dynamic_app.service.generate_customization_script",
                return_value=None,
            ),
        ):
            result = await open_webmap(
                webmap_id=webmap_id,
                portal_url=portal_url,
                additional_requirements=additional_requirements,
            )

        assert result.meta is not None
        assert result.meta["ui"]["resourceUri"] == EXPECTED_RESOURCE_URI

    @settings(max_examples=100)
    @given(data=st.data())
    @pytest.mark.asyncio
    async def test_open_layers_map_resource_uri(self, data: st.DataObject) -> None:
        """open_layers_map always returns resourceUri = "ui://dynamic-app/map-viewer.html".

        **Validates: Requirements 2.4**
        """
        layer_urls = data.draw(_layer_urls_strategy)
        where_clauses = data.draw(_matching_where_clauses(layer_urls))
        additional_requirements = data.draw(_additional_requirements_strategy)

        with (
            patch("psmcp_router_dynamic_app.service.resolve_token", return_value=None),
            patch(
                "psmcp_router_dynamic_app.service.generate_customization_script",
                return_value=None,
            ),
        ):
            result = await open_layers_map(
                layer_urls=layer_urls,
                layer_where_clauses=where_clauses,
                additional_requirements=additional_requirements,
            )

        assert result.meta is not None
        assert result.meta["ui"]["resourceUri"] == EXPECTED_RESOURCE_URI
