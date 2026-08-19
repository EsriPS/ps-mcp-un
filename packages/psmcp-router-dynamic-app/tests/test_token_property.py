"""Property-based tests for token server derivation logic.

Feature: dynamic-application-router
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from psmcp_router_dynamic_app.schemas import _derive_token_registration_server

# --- Strategies ---

# Valid schemes for ArcGIS URLs
_schemes = st.sampled_from(["http", "https"])

# Valid hostnames (simple alphanumeric with dots)
_hosts = st.from_regex(r"[a-z][a-z0-9\-]{0,15}\.[a-z]{2,6}", fullmatch=True)

# First path segment (the web adaptor context, e.g., "portal", "server", "arcgis")
_first_segments = st.from_regex(r"[a-z][a-z0-9\-]{0,15}", fullmatch=True)

# Additional path segments after /rest (e.g., "services/MyService/MapServer")
_rest_suffix_segments = st.lists(
    st.from_regex(r"[a-zA-Z0-9_\-]{1,20}", fullmatch=True),
    min_size=0,
    max_size=5,
)

# Path segments for URLs without /rest
_non_rest_segments = st.lists(
    st.from_regex(r"[a-zA-Z0-9_\-]{1,20}", fullmatch=True).filter(lambda s: s != "rest"),
    min_size=1,
    max_size=5,
)


@st.composite
def url_with_rest(draw: st.DrawFn) -> str:
    """Generate a URL containing /rest with a valid scheme, host, and at least one path segment."""
    scheme = draw(_schemes)
    host = draw(_hosts)
    first_segment = draw(_first_segments)
    rest_suffix = draw(_rest_suffix_segments)

    # Build path: /first_segment/.../rest/...
    # Optionally add segments between first_segment and rest
    middle_segments = draw(
        st.lists(
            st.from_regex(r"[a-z][a-z0-9]{0,10}", fullmatch=True).filter(lambda s: s != "rest"),
            min_size=0,
            max_size=3,
        )
    )

    path_parts = [first_segment, *middle_segments, "rest", *rest_suffix]
    path = "/" + "/".join(path_parts)

    return f"{scheme}://{host}{path}"


@st.composite
def url_without_rest(draw: st.DrawFn) -> str:
    """Generate a URL that does NOT contain /rest anywhere in the path."""
    scheme = draw(_schemes)
    host = draw(_hosts)
    segments = draw(_non_rest_segments)

    path = "/" + "/".join(segments)
    return f"{scheme}://{host}{path}"


# Feature: dynamic-application-router, Property 6: Token Server Derivation
class TestTokenServerDerivation:
    """Property 6: Token Server Derivation.

    For any URL string with a valid scheme, host, and at least one path segment,
    _derive_token_registration_server SHALL return scheme://host/first_path_segment.
    For URLs without a valid scheme, host, or path segment, it SHALL return None.

    **Validates: Requirements 8.2**
    """

    @settings(max_examples=100)
    @given(url=url_with_rest())
    def test_urls_with_rest_return_scheme_host_first_segment(self, url: str) -> None:
        """URLs containing /rest return scheme://host/first_path_segment.

        **Validates: Requirements 8.2**
        """
        result = _derive_token_registration_server(url)

        assert result is not None, f"Expected non-None for URL with /rest: {url}"

        # Parse the URL to verify the result matches scheme://host/first_path_segment
        from urllib.parse import urlparse

        parsed = urlparse(url)
        first_segment = next(seg for seg in parsed.path.split("/") if seg)
        expected = f"{parsed.scheme}://{parsed.netloc}/{first_segment}"

        assert result == expected, f"Expected {expected!r} but got {result!r} for URL: {url}"

    @settings(max_examples=100)
    @given(url=url_without_rest())
    def test_urls_without_rest_return_first_segment(self, url: str) -> None:
        """URLs not containing /rest still return scheme://host/first_path_segment.

        Portal URLs often lack /rest but still represent valid token registration
        servers (e.g., https://portal.example.com/portal).

        **Validates: Requirements 8.2**
        """
        from urllib.parse import urlparse

        result = _derive_token_registration_server(url)

        parsed = urlparse(url)
        first_segment = next(seg for seg in parsed.path.split("/") if seg)
        expected = f"{parsed.scheme}://{parsed.netloc}/{first_segment}"

        assert result == expected, (
            f"Expected {expected!r} for URL without /rest: {url}, got {result!r}"
        )
