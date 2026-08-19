"""Content Security Policy builder for the Dynamic App Router."""

import copy
import urllib.parse

from .schemas import CspMetadata

BASELINE_CSP: CspMetadata = {
    "connectDomains": [
        "https://js.arcgis.com",
        "https://services.arcgisonline.com",
        "https://server.arcgisonline.com",
        "https://basemaps.arcgis.com",
        "https://cdn.arcgis.com",
        "https://static.arcgis.com",
        "https://*.arcgisonline.com",
        "https://cdn.jsdelivr.net",
    ],
    "resourceDomains": [
        "https://js.arcgis.com",
        "https://cdn.arcgis.com",
        "https://static.arcgis.com",
        "https://*.arcgisonline.com",
        "https://cdn.jsdelivr.net",
    ],
    "scriptDomains": [
        "https://js.arcgis.com",
        "https://cdn.jsdelivr.net",
    ],
    "styleDomains": [
        "https://js.arcgis.com",
        "https://cdn.jsdelivr.net",
    ],
}


def _extract_origin(url: str) -> str | None:
    """Extract the origin (scheme + host) from a URL.

    Args:
        url: A URL string to extract the origin from.

    Returns:
        The origin as "scheme://host" or None if the URL cannot be parsed.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def build_csp(
    portal_url: str | None = None,
    layer_urls: list[str] | None = None,
) -> CspMetadata:
    """Build a Content Security Policy metadata object.

    Starts with the baseline ArcGIS CDN domains and dynamically adds origins
    extracted from the portal URL and layer URLs to connectDomains and
    resourceDomains.

    Args:
        portal_url: Optional ArcGIS portal URL to add to the CSP allowlists.
        layer_urls: Optional list of layer service URLs to add to the CSP allowlists.

    Returns:
        A CspMetadata dict with deduplicated domain allowlists.
    """
    csp: CspMetadata = copy.deepcopy(BASELINE_CSP)

    if portal_url:
        origin = _extract_origin(portal_url)
        if origin:
            csp["connectDomains"].append(origin)
            csp["resourceDomains"].append(origin)

    if layer_urls:
        for url in layer_urls:
            origin = _extract_origin(url)
            if origin:
                csp["connectDomains"].append(origin)
                csp["resourceDomains"].append(origin)

    # Deduplicate all arrays while preserving order
    csp["connectDomains"] = list(dict.fromkeys(csp["connectDomains"]))
    csp["resourceDomains"] = list(dict.fromkeys(csp["resourceDomains"]))
    csp["scriptDomains"] = list(dict.fromkeys(csp["scriptDomains"]))
    csp["styleDomains"] = list(dict.fromkeys(csp["styleDomains"]))

    return csp
