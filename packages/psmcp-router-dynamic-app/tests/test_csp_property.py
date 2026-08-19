# Feature: dynamic-application-router, Property 2: CSP Baseline Domains Always Present
"""Property-based test verifying CSP baseline domains are always present.

**Validates: Requirements 2.3, 9.1, 9.2**

For any valid tool invocation with any parameters, the returned CSP object SHALL contain
all baseline ArcGIS CDN domains:
- js.arcgis.com in connectDomains, resourceDomains, scriptDomains, and styleDomains
- services.arcgisonline.com and basemaps.arcgis.com in connectDomains
- cdn.arcgis.com and static.arcgis.com in connectDomains and resourceDomains
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from psmcp_router_dynamic_app.csp import build_csp

# Strategy: generate arbitrary strings that could be passed as portal_url (including None).
# We include well-formed URLs, malformed strings, and None to exercise all code paths.
_hostname_chars = st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-.")
_path_chars = st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-._~/")

_well_formed_url = st.builds(
    lambda scheme, host, path: f"{scheme}://{host}/{path}",
    scheme=st.sampled_from(["http", "https"]),
    host=st.text(alphabet=_hostname_chars, min_size=3, max_size=30),
    path=st.text(alphabet=_path_chars, min_size=0, max_size=50),
)

_arbitrary_string = st.text(min_size=0, max_size=200)

portal_url_strategy = st.one_of(
    st.none(),
    _well_formed_url,
    _arbitrary_string,
)

# Strategy: generate random layer URL lists (including None and empty lists)
layer_urls_strategy = st.one_of(
    st.none(),
    st.lists(
        st.one_of(_well_formed_url, _arbitrary_string),
        min_size=0,
        max_size=10,
    ),
)


@settings(max_examples=200)
@given(portal_url=portal_url_strategy, layer_urls=layer_urls_strategy)
def test_csp_baseline_domains_always_present(
    portal_url: str | None,
    layer_urls: list[str] | None,
) -> None:
    """CSP baseline ArcGIS CDN domains are always present regardless of inputs.

    **Validates: Requirements 2.3, 9.1, 9.2**
    """
    csp = build_csp(portal_url=portal_url, layer_urls=layer_urls)

    # js.arcgis.com must be in all four domain lists
    assert "https://js.arcgis.com" in csp["connectDomains"]
    assert "https://js.arcgis.com" in csp["resourceDomains"]
    assert "https://js.arcgis.com" in csp["scriptDomains"]
    assert "https://js.arcgis.com" in csp["styleDomains"]

    # services.arcgisonline.com and basemaps.arcgis.com must be in connectDomains
    assert "https://services.arcgisonline.com" in csp["connectDomains"]
    assert "https://basemaps.arcgis.com" in csp["connectDomains"]

    # cdn.arcgis.com and static.arcgis.com must be in connectDomains and resourceDomains
    assert "https://cdn.arcgis.com" in csp["connectDomains"]
    assert "https://cdn.arcgis.com" in csp["resourceDomains"]
    assert "https://static.arcgis.com" in csp["connectDomains"]
    assert "https://static.arcgis.com" in csp["resourceDomains"]
