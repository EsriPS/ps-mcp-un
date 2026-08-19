"""Property-based tests for schemas.py validation logic.

Feature: dynamic-application-router
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from psmcp_router_dynamic_app.schemas import build_tool_result_data

# Strategy: generate whitespace-only or empty strings for webmap_id
whitespace_only_strings = st.from_regex(r"^\s*$", fullmatch=True)


# Strategy: generate valid layer_urls lists (1-10 items for speed)
valid_layer_urls = st.lists(
    st.from_regex(r"https://[a-z]+\.[a-z]+\.[a-z]+/[a-z]+/rest/services/\w+", fullmatch=True),
    min_size=1,
    max_size=10,
)


# Strategy: generate layer_where_clauses with length != layer_urls length
@st.composite
def mismatched_where_clauses(draw):
    """Generate layer_urls and layer_where_clauses with different lengths."""
    urls = draw(
        st.lists(
            st.from_regex(
                r"https://[a-z]+\.[a-z]+\.[a-z]+/[a-z]+/rest/services/\w+", fullmatch=True
            ),
            min_size=1,
            max_size=10,
        )
    )
    # Generate where_clauses with a different length than urls
    wrong_length = draw(st.integers(min_value=0, max_value=20).filter(lambda x: x != len(urls)))
    where_clauses = draw(
        st.lists(st.text(min_size=1, max_size=50), min_size=wrong_length, max_size=wrong_length)
    )
    return urls, where_clauses


# Feature: dynamic-application-router, Property 8: Invalid Parameters Produce Error Results
class TestInvalidParametersProduceErrors:
    """Property 8: Invalid Parameters Produce Error Results.

    For any invocation of open_webmap with an empty or whitespace-only webmap_id,
    or open_layers_map with an empty layer_urls list, or open_layers_map with
    layer_where_clauses whose length differs from layer_urls, the tool SHALL return
    a result with isError: true and a non-empty error message string.

    **Validates: Requirements 5.7, 6.6, 12.1**
    """

    @settings(max_examples=100)
    @given(webmap_id=whitespace_only_strings)
    def test_webmap_empty_or_whitespace_id_raises(self, webmap_id: str) -> None:
        """Empty or whitespace-only webmap_id raises ValueError.

        **Validates: Requirements 5.7**
        """
        with pytest.raises(ValueError, match="webmap_id"):
            build_tool_result_data(
                "webmap",
                webmap_id=webmap_id,
                portal_url="https://www.arcgis.com",
            )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_layers_map_empty_layer_urls_raises(self, data: st.DataObject) -> None:
        """Empty layer_urls list raises ValueError.

        **Validates: Requirements 6.6**
        """
        with pytest.raises(ValueError, match="layer_urls"):
            build_tool_result_data(
                "layers_map",
                layer_urls=[],
            )

    @settings(max_examples=100)
    @given(data=mismatched_where_clauses())
    def test_layers_map_mismatched_where_clauses_raises(
        self, data: tuple[list[str], list[str]]
    ) -> None:
        """layer_where_clauses with length != layer_urls raises ValueError.

        **Validates: Requirements 6.6**
        """
        layer_urls, where_clauses = data
        with pytest.raises(ValueError, match="layer_where_clauses length"):
            build_tool_result_data(
                "layers_map",
                layer_urls=layer_urls,
                layer_where_clauses=where_clauses,
            )

    @settings(max_examples=100)
    @given(
        portal_url=st.one_of(
            st.just(""),
            st.just(None),
            whitespace_only_strings,
        )
    )
    def test_webmap_empty_or_whitespace_portal_url_raises(self, portal_url: str | None) -> None:
        """Empty or whitespace-only portal_url for webmap raises ValueError.

        **Validates: Requirements 12.1**
        """
        with pytest.raises(ValueError, match=r"portal_url|webmap_id"):
            build_tool_result_data(
                "webmap",
                webmap_id="abc123",
                portal_url=portal_url,
            )


# --- Strategies for Property 4 ---

# Strategy for valid non-empty strings (used for webmap_id, etc.)
_non_empty_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S"), exclude_characters="\x00"),
    min_size=1,
    max_size=50,
)

# Strategy for valid HTTP/HTTPS URLs
_url_strategy = st.from_regex(
    r"https?://[a-z][a-z0-9\-]{0,20}\.[a-z]{2,6}(/[a-z0-9\-]{1,20}){0,4}",
    fullmatch=True,
)

# Strategy for layer URL lists (1-10 items for test speed)
_layer_urls_strategy = st.lists(_url_strategy, min_size=1, max_size=10)

# Strategy for additional_requirements (max 2000 chars per spec, capped at 200 for speed)
_additional_requirements_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z"), exclude_characters="\x00"),
    min_size=1,
    max_size=200,
)


# Feature: dynamic-application-router, Property 4: Tool Result Data Preserves Input Parameters
class TestToolResultDataPreservesInputParameters:
    """Property 4: Tool Result Data Preserves Input Parameters.

    For any valid tool invocation, the JSON-encoded Tool_Result_Data in the response
    SHALL contain the exact input values: for open_webmap, the webmap_id and portal_url
    fields match the inputs; for open_layers_map, the layer_urls field matches the input
    list; for all tools, additional_requirements (when provided) matches the input string.

    **Validates: Requirements 5.4, 6.2, 11.7**
    """

    @settings(max_examples=100)
    @given(
        webmap_id=_non_empty_text,
        portal_url=_url_strategy,
    )
    def test_webmap_preserves_webmap_id_and_portal_url(
        self, webmap_id: str, portal_url: str
    ) -> None:
        """For open_webmap, webmap_id and portal_url in output match inputs exactly.

        **Validates: Requirements 5.4**
        """
        result = build_tool_result_data(
            "webmap",
            webmap_id=webmap_id,
            portal_url=portal_url,
        )
        assert result["webmap_id"] == webmap_id
        assert result["portal_url"] == portal_url

    @settings(max_examples=100)
    @given(layer_urls=_layer_urls_strategy)
    def test_layers_map_preserves_layer_urls(self, layer_urls: list[str]) -> None:
        """For open_layers_map, layer_urls in output matches the input list exactly.

        **Validates: Requirements 6.2**
        """
        result = build_tool_result_data(
            "layers_map",
            layer_urls=layer_urls,
        )
        assert result["layer_urls"] == layer_urls

    @settings(max_examples=100)
    @given(
        webmap_id=_non_empty_text,
        portal_url=_url_strategy,
        additional_requirements=_additional_requirements_strategy,
    )
    def test_webmap_preserves_additional_requirements(
        self, webmap_id: str, portal_url: str, additional_requirements: str
    ) -> None:
        """For open_webmap with additional_requirements, the field matches input exactly.

        **Validates: Requirements 11.7**
        """
        result = build_tool_result_data(
            "webmap",
            webmap_id=webmap_id,
            portal_url=portal_url,
            additional_requirements=additional_requirements,
        )
        assert result["additional_requirements"] == additional_requirements

    @settings(max_examples=100)
    @given(
        layer_urls=_layer_urls_strategy,
        additional_requirements=_additional_requirements_strategy,
    )
    def test_layers_map_preserves_additional_requirements(
        self, layer_urls: list[str], additional_requirements: str
    ) -> None:
        """For open_layers_map with additional_requirements, the field matches input exactly.

        **Validates: Requirements 11.7**
        """
        result = build_tool_result_data(
            "layers_map",
            layer_urls=layer_urls,
            additional_requirements=additional_requirements,
        )
        assert result["additional_requirements"] == additional_requirements

    @settings(max_examples=100)
    @given(additional_requirements=_additional_requirements_strategy)
    def test_sample_map_preserves_additional_requirements(
        self, additional_requirements: str
    ) -> None:
        """For open_sample_map with additional_requirements, the field matches input exactly.

        **Validates: Requirements 11.7**
        """
        result = build_tool_result_data(
            "sample_map",
            additional_requirements=additional_requirements,
        )
        assert result["additional_requirements"] == additional_requirements
