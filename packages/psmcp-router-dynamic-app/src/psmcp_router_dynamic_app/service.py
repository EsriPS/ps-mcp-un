"""Dynamic App Router — FastMCP instance and tool/resource registration."""

import json
import logging
import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from psmcp.core.auth import resolve_token

from .csp import build_csp
from .llm import USE_ARCGIS_LLM, generate_customization_script
from .schemas import (
    MAX_ADDITIONAL_REQUIREMENTS_CHARS,
    MAX_LAYER_URLS,
    build_token_servers,
    build_tool_result_data,
)
from .viewer import get_viewer_html

logger = logging.getLogger(__name__)

RESOURCE_URI = "ui://dynamic-app/map-viewer.html"
ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")

dynamic_app_router = FastMCP(name="Dynamic App Router")


@dynamic_app_router.resource(
    "ui://dynamic-app/map-viewer.html", mime_type="text/html;profile=mcp-app"
)
def map_viewer_resource() -> str:
    """Serve the static Map Viewer App HTML.

    Returns the self-contained HTML document that uses the MCP Apps SDK to receive
    tool result data and dynamically render ArcGIS maps. The content is static and
    deterministic — all variation comes from the tool result data passed at runtime.
    """
    logger.info("Serving map viewer resource")
    return get_viewer_html()


@dynamic_app_router.tool
async def open_sample_map(additional_requirements: str | None = None) -> ToolResult:
    """Open a sample ArcGIS map with a topo-vector basemap centered on the US.

    Args:
        additional_requirements: Optional natural language customization requirements
            (max 2000 chars).

    Returns:
        ToolResult with map data and UI metadata for rendering the sample map.
    """
    logger.info("open_sample_map called")

    # Validate additional_requirements length
    if (
        additional_requirements is not None
        and len(additional_requirements) > MAX_ADDITIONAL_REQUIREMENTS_CHARS
    ):
        logger.error(
            "open_sample_map: additional_requirements exceeds %d chars",
            MAX_ADDITIONAL_REQUIREMENTS_CHARS,
        )
        raise ToolError(
            f"additional_requirements must be at most "
            f"{MAX_ADDITIONAL_REQUIREMENTS_CHARS} characters."
        )

    # Generate customization script via LLM if enabled and requirements provided
    customization_script = None
    if additional_requirements and USE_ARCGIS_LLM:
        customization_script = await generate_customization_script(
            "sample_map", {}, additional_requirements
        )

    # Build tool result data
    data = build_tool_result_data(
        "sample_map",
        customization_script=customization_script,
        additional_requirements=additional_requirements if additional_requirements else None,
    )

    csp = build_csp()

    return ToolResult(
        content=[
            TextContent(type="text", text="Opening a sample ArcGIS map with topo-vector basemap."),
            TextContent(type="text", text=json.dumps(data)),
        ],
        meta={
            "ui": {
                "resourceUri": RESOURCE_URI,
                "csp": csp,
                "prefersBorder": True,
            },
        },
    )


@dynamic_app_router.tool
async def open_webmap(
    webmap_id: str,
    portal_url: str | None = None,
    additional_requirements: str | None = None,
) -> ToolResult:
    """Open an ArcGIS web map by its item ID from a portal.

    Loads and displays a web map from an ArcGIS portal using the specified item ID.
    Falls back to the ARCGIS_PORTAL_URL environment variable if no portal_url is provided.

    Args:
        webmap_id: The web map item ID (required, non-empty).
        portal_url: The ArcGIS portal URL (e.g., "https://www.arcgis.com").
            Falls back to ARCGIS_PORTAL_URL env var if not provided.
        additional_requirements: Optional natural language customization requirements
            (max 2000 chars).

    Returns:
        ToolResult with map data and UI metadata for rendering the web map.
    """
    logger.info("open_webmap called with webmap_id=%s", webmap_id)

    # Validate webmap_id is non-empty
    if not webmap_id or not webmap_id.strip():
        logger.error("open_webmap: webmap_id is empty or whitespace")
        raise ToolError("A valid web map item ID is required. webmap_id must not be empty.")

    # Resolve portal URL: parameter > env var
    resolved_portal_url = portal_url or ARCGIS_PORTAL_URL
    if not resolved_portal_url:
        logger.error("open_webmap: no portal URL available")
        raise ToolError(
            "No portal URL available. Provide portal_url parameter "
            "or set ARCGIS_PORTAL_URL environment variable."
        )

    # Validate additional_requirements length
    if (
        additional_requirements is not None
        and len(additional_requirements) > MAX_ADDITIONAL_REQUIREMENTS_CHARS
    ):
        logger.error(
            "open_webmap: additional_requirements exceeds %d chars",
            MAX_ADDITIONAL_REQUIREMENTS_CHARS,
        )
        raise ToolError(
            f"additional_requirements must be at most "
            f"{MAX_ADDITIONAL_REQUIREMENTS_CHARS} characters."
        )

    # Resolve authentication token (non-required)
    token = resolve_token(required=False)
    logger.info(
        "open_webmap: token resolved=%s, token_length=%d",
        token is not None,
        len(token) if token else 0,
    )

    # Build token servers from portal URL
    token_servers = build_token_servers(portal_url=resolved_portal_url) if token else None
    logger.info("open_webmap: token_servers=%s", token_servers)

    # Generate customization script via LLM if enabled and requirements provided
    customization_script = None
    if additional_requirements and USE_ARCGIS_LLM:
        customization_script = await generate_customization_script(
            "webmap",
            {"webmap_id": webmap_id, "portal_url": resolved_portal_url},
            additional_requirements,
        )

    # Build tool result data
    data = build_tool_result_data(
        "webmap",
        webmap_id=webmap_id,
        portal_url=resolved_portal_url,
        token=token,
        token_servers=token_servers,
        customization_script=customization_script,
        additional_requirements=additional_requirements if additional_requirements else None,
    )

    # Build CSP with portal URL added to dynamic domains
    csp = build_csp(portal_url=resolved_portal_url)

    return ToolResult(
        content=[
            TextContent(
                type="text", text=f"Opening web map {webmap_id} from {resolved_portal_url}"
            ),
            TextContent(type="text", text=json.dumps(data)),
        ],
        meta={
            "ui": {
                "resourceUri": RESOURCE_URI,
                "csp": csp,
                "prefersBorder": True,
            },
        },
    )


@dynamic_app_router.tool
async def open_layers_map(
    layer_urls: list[str],
    layer_where_clauses: list[str] | None = None,
    additional_requirements: str | None = None,
) -> ToolResult:
    """Open a map with multiple data layers from ArcGIS Server URLs.

    Renders a map with one or more feature/map service layers loaded from the
    provided URLs. Optionally applies definition expressions (where clauses) to
    filter features on each layer.

    Args:
        layer_urls: List of ArcGIS layer service URLs to display (1-50 items).
        layer_where_clauses: Optional list of SQL where clauses corresponding to each
            layer URL by index position. Must be the same length as layer_urls if provided.
        additional_requirements: Optional natural language customization requirements
            (max 2000 chars).

    Returns:
        ToolResult with map data and UI metadata for rendering the layers map.
    """
    logger.info("open_layers_map called with %d layer URLs", len(layer_urls))
    logger.info(
        "open_layers_map: additional_requirements=%s, USE_ARCGIS_LLM=%s",
        additional_requirements[:80] if additional_requirements else None,
        USE_ARCGIS_LLM,
    )

    # Validate layer_urls is non-empty
    if not layer_urls:
        logger.error("open_layers_map: layer_urls is empty")
        raise ToolError("layer_urls must contain at least one URL.")

    # Validate layer_urls does not exceed maximum
    if len(layer_urls) > MAX_LAYER_URLS:
        logger.error(
            "open_layers_map: layer_urls contains %d items, max is %d",
            len(layer_urls),
            MAX_LAYER_URLS,
        )
        raise ToolError(
            f"layer_urls must contain at most {MAX_LAYER_URLS} items, got {len(layer_urls)}."
        )

    # Validate layer_where_clauses length matches layer_urls if provided
    if layer_where_clauses is not None and len(layer_where_clauses) != len(layer_urls):
        logger.error(
            "open_layers_map: layer_where_clauses length (%d) != layer_urls length (%d)",
            len(layer_where_clauses),
            len(layer_urls),
        )
        raise ToolError(
            f"layer_where_clauses length ({len(layer_where_clauses)}) "
            f"must match layer_urls length ({len(layer_urls)})."
        )

    # Validate additional_requirements length
    if (
        additional_requirements is not None
        and len(additional_requirements) > MAX_ADDITIONAL_REQUIREMENTS_CHARS
    ):
        logger.error(
            "open_layers_map: additional_requirements exceeds %d chars",
            MAX_ADDITIONAL_REQUIREMENTS_CHARS,
        )
        raise ToolError(
            f"additional_requirements must be at most "
            f"{MAX_ADDITIONAL_REQUIREMENTS_CHARS} characters."
        )

    # Resolve authentication token (non-required — graceful if unavailable)
    token = resolve_token(required=False)

    # Derive token servers from layer URLs
    token_servers = build_token_servers(layer_urls=layer_urls) if token else None

    # Generate customization script via LLM if enabled and requirements provided
    customization_script = None
    if additional_requirements and USE_ARCGIS_LLM:
        customization_script = await generate_customization_script(
            "layers_map",
            {"layer_urls": layer_urls, "layer_where_clauses": layer_where_clauses},
            additional_requirements,
        )

    # Build tool result data
    data = build_tool_result_data(
        "layers_map",
        layer_urls=layer_urls,
        layer_where_clauses=layer_where_clauses,
        token=token,
        token_servers=token_servers,
        customization_script=customization_script,
        additional_requirements=additional_requirements if additional_requirements else None,
    )

    # Build CSP with layer URL origins added
    csp = build_csp(layer_urls=layer_urls)

    return ToolResult(
        content=[
            TextContent(
                type="text",
                text=f"Opening map with {len(layer_urls)} layer(s).",
            ),
            TextContent(type="text", text=json.dumps(data)),
        ],
        meta={
            "ui": {
                "resourceUri": RESOURCE_URI,
                "csp": csp,
                "prefersBorder": True,
            },
        },
    )
