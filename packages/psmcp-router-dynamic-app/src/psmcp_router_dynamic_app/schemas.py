"""Tool result data schemas and validation for the Dynamic App Router."""

from typing import NotRequired, TypedDict
from urllib.parse import urlparse

VALID_MAP_TYPES = ("sample_map", "webmap", "layers_map")

MAX_LAYER_URLS = 50
MAX_CUSTOMIZATION_SCRIPT_CHARS = 50_000
MAX_ADDITIONAL_REQUIREMENTS_CHARS = 2_000


class ToolResultData(TypedDict):
    """Structured content returned by a tool containing map parameters.

    The Map Viewer App uses this data to render the appropriate map type.
    """

    type: str
    webmap_id: NotRequired[str]
    portal_url: NotRequired[str]
    layer_urls: NotRequired[list[str]]
    layer_where_clauses: NotRequired[list[str]]
    token: NotRequired[str]
    token_servers: NotRequired[list[str]]
    customization_script: NotRequired[str]
    additional_requirements: NotRequired[str]


class CspMetadata(TypedDict):
    """Content Security Policy metadata included in tool result _meta.ui.csp."""

    connectDomains: list[str]
    resourceDomains: list[str]
    scriptDomains: list[str]
    styleDomains: list[str]


def validate_webmap_params(webmap_id: str | None, portal_url: str | None) -> None:
    """Validate parameters required for a webmap type tool result.

    Args:
        webmap_id: The web map item ID. Must be a non-empty string.
        portal_url: The portal URL. Must be a non-empty string.

    Raises:
        ValueError: If webmap_id or portal_url is missing or empty.
    """
    if not webmap_id or not webmap_id.strip():
        raise ValueError("webmap_id must be a non-empty string for type 'webmap'")
    if not portal_url or not portal_url.strip():
        raise ValueError("portal_url must be a non-empty string for type 'webmap'")


def validate_layers_params(
    layer_urls: list[str] | None,
    layer_where_clauses: list[str] | None,
) -> None:
    """Validate parameters required for a layers_map type tool result.

    Args:
        layer_urls: List of layer URLs. Must contain 1-50 non-empty strings.
        layer_where_clauses: Optional list of where clauses. If provided, must match
            the length of layer_urls.

    Raises:
        ValueError: If layer_urls is invalid or layer_where_clauses length mismatches.
    """
    if not layer_urls:
        raise ValueError("layer_urls must be a non-empty list for type 'layers_map'")
    if len(layer_urls) > MAX_LAYER_URLS:
        raise ValueError(
            f"layer_urls must contain at most {MAX_LAYER_URLS} items, got {len(layer_urls)}"
        )
    for i, url in enumerate(layer_urls):
        if not url or not url.strip():
            raise ValueError(f"layer_urls[{i}] must be a non-empty string")
    if layer_where_clauses is not None and len(layer_where_clauses) != len(layer_urls):
        raise ValueError(
            f"layer_where_clauses length ({len(layer_where_clauses)}) must match "
            f"layer_urls length ({len(layer_urls)})"
        )


def build_tool_result_data(
    map_type: str,
    *,
    webmap_id: str | None = None,
    portal_url: str | None = None,
    layer_urls: list[str] | None = None,
    layer_where_clauses: list[str] | None = None,
    token: str | None = None,
    token_servers: list[str] | None = None,
    customization_script: str | None = None,
    additional_requirements: str | None = None,
) -> dict:
    """Construct and validate a Tool Result Data dictionary.

    Builds the structured content that the Map Viewer App uses to render maps.
    Always includes the ``type`` field; optional fields are only included when
    their values are not None.

    Args:
        map_type: The map type. Must be one of "sample_map", "webmap", or "layers_map".
        webmap_id: Web map item ID (required for type "webmap").
        portal_url: Portal URL (required for type "webmap").
        layer_urls: List of layer service URLs (required for type "layers_map").
        layer_where_clauses: Optional where clauses matching layer_urls by index.
        token: ArcGIS authentication token.
        token_servers: Server URLs to register the token with.
        customization_script: JavaScript code to execute after map init (max 50,000 chars).
        additional_requirements: Natural language requirements text (max 2,000 chars).

    Returns:
        A dictionary conforming to the ToolResultData schema.

    Raises:
        ValueError: If any validation check fails.
    """
    if map_type not in VALID_MAP_TYPES:
        raise ValueError(f"type must be one of {VALID_MAP_TYPES!r}, got {map_type!r}")

    if map_type == "webmap":
        validate_webmap_params(webmap_id, portal_url)

    if map_type == "layers_map":
        validate_layers_params(layer_urls, layer_where_clauses)

    if token is not None and (not token_servers or len(token_servers) == 0):
        raise ValueError("token_servers must be present and non-empty when token is provided")

    if (
        customization_script is not None
        and len(customization_script) > MAX_CUSTOMIZATION_SCRIPT_CHARS
    ):
        raise ValueError(
            f"customization_script must be at most {MAX_CUSTOMIZATION_SCRIPT_CHARS} characters, "
            f"got {len(customization_script)}"
        )

    if (
        additional_requirements is not None
        and len(additional_requirements) > MAX_ADDITIONAL_REQUIREMENTS_CHARS
    ):
        raise ValueError(
            f"additional_requirements must be at most {MAX_ADDITIONAL_REQUIREMENTS_CHARS} "
            f"characters, got {len(additional_requirements)}"
        )

    data: dict = {"type": map_type}

    if webmap_id is not None:
        data["webmap_id"] = webmap_id
    if portal_url is not None:
        data["portal_url"] = portal_url
    if layer_urls is not None:
        data["layer_urls"] = layer_urls
    if layer_where_clauses is not None:
        data["layer_where_clauses"] = layer_where_clauses
    if token is not None:
        data["token"] = token
    if token_servers is not None:
        data["token_servers"] = token_servers
    if customization_script is not None:
        data["customization_script"] = customization_script
    if additional_requirements is not None:
        data["additional_requirements"] = additional_requirements

    return data


def _derive_token_registration_server(url: str) -> str | None:
    """Return the web adaptor base URL for token registration.

    Tokens should be scoped to the portal or server web adaptor context. The web
    adaptor context is the first path segment in the URL.

    For ArcGIS Enterprise URLs with a web adaptor path (e.g., ``/portal``,
    ``/server``), returns ``scheme://host/first_path_segment``.

    For ArcGIS Online URLs (no path segments, e.g., ``https://www.arcgis.com``
    or ``https://org.maps.arcgis.com``), returns the origin
    (``scheme://host``) since ArcGIS Online does not use a web adaptor context.

    Args:
        url: An ArcGIS endpoint URL (e.g., a portal URL or a map service URL).

    Returns:
        The base URL for token registration, or None if the URL lacks a valid
        scheme or host.

    Examples:
        >>> _derive_token_registration_server(
        ...     "https://portal.example.com/portal/sharing/rest/content/items/abc"
        ... )
        'https://portal.example.com/portal'
        >>> _derive_token_registration_server(
        ...     "https://maps.example.com/server/rest/services/MyService/MapServer"
        ... )
        'https://maps.example.com/server'
        >>> _derive_token_registration_server(
        ...     "https://portal.example.com/portal"
        ... )
        'https://portal.example.com/portal'
        >>> _derive_token_registration_server("https://www.arcgis.com")
        'https://www.arcgis.com'
        >>> _derive_token_registration_server("https://org.maps.arcgis.com")
        'https://org.maps.arcgis.com'
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None

    path = parsed.path.rstrip("/")

    # Extract the first non-empty path segment (the web adaptor context)
    path_segments = [seg for seg in path.split("/") if seg]
    if not path_segments:
        # ArcGIS Online URLs have no web adaptor context — use the origin
        return f"{parsed.scheme}://{parsed.netloc}"

    web_adaptor_context = path_segments[0]
    return f"{parsed.scheme}://{parsed.netloc}/{web_adaptor_context}"


def build_token_servers(
    portal_url: str | None = None,
    layer_urls: list[str] | None = None,
) -> list[str] | None:
    """Build a deduplicated list of token registration server URLs.

    Derives token registration servers from the portal URL and all layer URLs by
    extracting the web adaptor base path from each. Results are deduplicated while
    preserving insertion order.

    Args:
        portal_url: Optional portal URL to derive a token server from.
        layer_urls: Optional list of layer service URLs to derive token servers from.

    Returns:
        A list of unique server base URLs if any are derived, or None if no valid
        servers can be determined from the inputs.

    Examples:
        >>> build_token_servers(
        ...     portal_url="https://portal.example.com/portal/sharing/rest/info",
        ...     layer_urls=["https://maps.example.com/server/rest/services/Svc/MapServer"],
        ... )
        ['https://portal.example.com/portal', 'https://maps.example.com/server']
        >>> build_token_servers(portal_url="https://portal.example.com/portal")
        ['https://portal.example.com/portal']
        >>> build_token_servers(portal_url="https://www.arcgis.com")
        ['https://www.arcgis.com']
    """
    servers: list[str] = []
    seen: set[str] = set()

    urls_to_check: list[str] = []
    if portal_url is not None:
        urls_to_check.append(portal_url)
    if layer_urls is not None:
        urls_to_check.extend(layer_urls)

    for url in urls_to_check:
        server = _derive_token_registration_server(url)
        if server is None:
            continue
        if server in seen:
            continue
        seen.add(server)
        servers.append(server)

    return servers if servers else None
