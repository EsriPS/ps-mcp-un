"""
Feature Service MCP Router

This module provides tools for making asynchronous REST requests to feature service
and feature layer endpoints with configurable parameters.
"""

import json
import logging
import os
import time
from typing import Any

import httpx
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

logger = logging.getLogger(__name__)

# ============================================================================
# region CONFIGURATION
# ============================================================================

# SSL certificate verification — set ARCGIS_VERIFY_SSL=false to disable (e.g. self-signed certs)
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"

# endregion CONFIGURATION


feature_service_router = FastMCP(name="Feature Service")

# ============================================================================
# region HELPER FUNCTIONS
# ============================================================================


def _ensure_query_url(endpoint_url: str) -> str:
    """
    Ensure the URL ends with /query exactly once.

    Feature layer query endpoints require /query at the end. This helper
    normalizes URLs so the AI doesn't need to worry about appending it.
    """
    stripped = endpoint_url.rstrip("/")
    if stripped.lower().endswith("/query"):
        return stripped[:-6] + "/query"
    return f"{stripped}/query"


def _safe_log_params(params: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of params with the token redacted for safe logging.
    """
    safe = params.copy()
    if "token" in safe:
        safe["token"] = "<redacted>"
    return safe


def _is_token_rejection(status_code: int, response_data: Any) -> bool:
    """
    Detect whether an ArcGIS response indicates the token was rejected.

    ArcGIS servers reject unrecognized tokens with:
      - HTTP 498 or 499
      - HTTP 200 with a JSON error body containing code 498 or 499

    Returns True if the response looks like a token-rejection error.
    """
    if status_code in (498, 499):
        return True
    if isinstance(response_data, dict):
        error_obj = response_data.get("error")
        if isinstance(error_obj, dict) and error_obj.get("code") in (498, 499):
            return True
    return False


# endregion HELPER FUNCTIONS


# ============================================================================
# region INTERNAL IMPLEMENTATIONS
# ============================================================================


async def _query_feature_layer(
    endpoint_url: str,
    parameters: dict[str, Any],
    timeout: int = 30,
    token: str | None = None,
    method: str | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Internal implementation for querying a feature layer via POST or GET.

    Ensures /query is appended to the URL, sets safe defaults, and prevents
    the caller from accidentally overwriting the authentication token.
    """
    start_time = time.time()

    # Ensure URL ends with /query
    endpoint_url = _ensure_query_url(endpoint_url)

    # Build parameters with safe defaults
    params = parameters.copy()
    params.pop("token", None)  # Never allow caller to override token
    if "f" not in params:
        params["f"] = "json"
    if "where" not in params:
        params["where"] = "1=1"
    if "outFields" not in params:
        params["outFields"] = "*"

    # Add resolved token
    if token:
        params["token"] = token

    request_method = (method or "POST").upper()
    if request_method not in {"GET", "POST"}:
        logger.warning("Unsupported method %r; defaulting to POST", request_method)
        request_method = "POST"

    safe_headers = list(headers.keys()) if headers else []

    logger.info(
        f"from _query_feature_layer: endpoint_url={endpoint_url}, "
        f"method={request_method}, headers={safe_headers}, "
        f"parameters={_safe_log_params(params)}"
    )

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=VERIFY_SSL) as client:
            if request_method == "GET":
                response = await client.request(
                    method="GET", url=endpoint_url, params=params, headers=headers
                )
            else:
                response = await client.request(
                    method="POST", url=endpoint_url, data=params, headers=headers
                )
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = response.text

            # Detect invalid-token errors and retry without the token.
            # ArcGIS returns HTTP 498 or a 200 with an error object containing
            # code 498 or 499 when an unrecognized/invalid token is supplied.
            if token and _is_token_rejection(response.status_code, response_data):
                logger.info(
                    "Token rejected by server; retrying without token: %s",
                    endpoint_url,
                )
                params.pop("token", None)
                if request_method == "GET":
                    response = await client.request(
                        method="GET", url=endpoint_url, params=params, headers=headers
                    )
                else:
                    response = await client.request(
                        method="POST", url=endpoint_url, data=params, headers=headers
                    )
                try:
                    response_data = response.json()
                except json.JSONDecodeError:
                    response_data = response.text

            return {
                "success": response.is_success,
                "status_code": response.status_code,
                "data": response_data,
                "error": None
                if response.is_success
                else f"HTTP {response.status_code}: {response.reason_phrase}",
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": f"Request timeout after {timeout} seconds",
            "status_code": None,
            "data": None,
        }
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Request error: {e!s}",
            "status_code": None,
            "data": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e!s}",
            "status_code": None,
            "data": None,
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"_query_feature_layer completed in {elapsed_time:.2f} seconds.")


async def _get_json_details(
    *,
    endpoint_url: str,
    timeout: int = 30,
    token: str | None = None,
) -> dict[str, Any]:
    """
    Shared helper for retrieving JSON metadata from a service or layer endpoint.

    Contract:
      - Always performs a GET request and forces f=json.
      - Returns a consistent response envelope with success/status_code/data/error.
      - Never raises; converts exceptions into an error response.
    """
    start_time = time.time()

    logger.info(
        f"from _get_json_details: endpoint_url={endpoint_url}, "
        f"token={'<provided>' if token else None}"
    )

    params: dict[str, str] = {"f": "json"}
    if token:
        params["token"] = token

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=VERIFY_SSL) as client:
            response = await client.get(endpoint_url, params=params)
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = response.text

            # Retry without token if the server rejects it (cross-server scenario)
            if token and _is_token_rejection(response.status_code, response_data):
                logger.info(
                    "Token rejected by server; retrying without token: %s",
                    endpoint_url,
                )
                params.pop("token", None)
                response = await client.get(endpoint_url, params=params)
                try:
                    response_data = response.json()
                except json.JSONDecodeError:
                    response_data = response.text

            return {
                "success": response.is_success,
                "status_code": response.status_code,
                "data": response_data,
                "error": None
                if response.is_success
                else f"HTTP {response.status_code}: {response.reason_phrase}",
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": f"Request timeout after {timeout} seconds",
            "status_code": None,
            "data": None,
        }
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Request error: {e!s}",
            "status_code": None,
            "data": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e!s}",
            "status_code": None,
            "data": None,
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"_get_json_details completed in {elapsed_time:.2f} seconds.")


# endregion INTERNAL IMPLEMENTATIONS


# ============================================================================
# region TOOLS
# ============================================================================


@feature_service_router.tool
async def query_feature_layer(
    endpoint_url: str,
    parameters: dict[str, Any],
    timeout: int = 30,
    token: str | None = None,
    method: str | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Query features from a feature layer using the ArcGIS REST API /query endpoint.

    Sends a POST request to the feature layer's query endpoint with the provided
    parameters. Automatically appends /query to the URL if not already present
    and sets safe defaults for f, where, and outFields.

    Args:
        endpoint_url: The full URL of the feature layer endpoint
            (e.g., "https://server/arcgis/rest/services/MyService/FeatureServer/0").
            /query is appended automatically if not present.
        parameters: Dictionary of query parameters to send with the request.
            Common parameters:
                - where: SQL-like filter (e.g., "status = 'active'"). Defaults to "1=1".
                - outFields: Comma-separated field names (e.g., "OBJECTID,name,status"). Defaults to "*".
                - returnGeometry: true or false. Set to false unless geometry is needed.
                - returnCountOnly: true to return only the count of matching features.
                - resultRecordCount: Maximum number of records to return (page size).
                - resultOffset: Number of records to skip (for pagination).
                - orderByFields: Fields to sort by (e.g., "OBJECTID"). Important for stable paging.
                - geometry: Spatial filter geometry object.
                - geometryType: Type of geometry filter (e.g., "esriGeometryEnvelope").
                - inSR: Spatial reference of the input geometry.
                - outSR: Spatial reference for returned geometries.
        timeout: Request timeout in seconds. Default: 30
        token: Optional authentication token. If not provided, uses token from authentication context.
        method: Optional HTTP method (GET or POST). Defaults to POST.
        headers: Optional HTTP headers to include with the request.

    Returns:
        Dict containing:
            - success: Boolean indicating if request was successful
            - status_code: HTTP status code
            - data: Response data from the service (features, count, etc.)
            - error: Error message if request failed, None otherwise

    Example:
        # Simple query with filter
        result = await query_feature_layer(
            endpoint_url="https://server/arcgis/rest/services/Parks/FeatureServer/0",
            parameters={"where": "status = 'Open'", "outFields": "OBJECTID,name,status", "returnGeometry": "false"}
        )

        # Count query
        result = await query_feature_layer(
            endpoint_url="https://server/arcgis/rest/services/Parks/FeatureServer/0",
            parameters={"where": "1=1", "returnCountOnly": "true"}
        )
    """
    start_time = time.time()
    resolved_token = resolve_token(token)

    logger.info(
        f"from query_feature_layer: endpoint_url={endpoint_url}, "
        f"token={'<provided>' if resolved_token else None}"
    )

    try:
        return await _query_feature_layer(
            endpoint_url=endpoint_url,
            parameters=parameters,
            timeout=timeout,
            token=resolved_token,
            method=method,
            headers=headers,
        )
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"query_feature_layer completed in {elapsed_time:.2f} seconds.")


@feature_service_router.tool
async def get_service_or_layer_details(
    endpoint_url: str, timeout: int = 30, token: str | None = None
) -> dict[str, Any]:
    """
    Retrieve metadata from a feature service or feature layer endpoint.

    Makes a GET request with f=json to the specified URL and returns the full
    JSON metadata response. Use this to inspect service-level details (layer list,
    capabilities, spatial reference) or layer-level details (fields, geometry type,
    drawing info, relationships).

    Works with any ArcGIS REST endpoint that returns JSON metadata, including:
        - Feature Service: .../FeatureServer (lists layers, capabilities, spatial reference)
        - Feature Layer: .../FeatureServer/0 (fields, geometry type, extent, etc.)
        - Map Service: .../MapServer (layer list, capabilities)
        - Map Layer: .../MapServer/0 (fields, geometry type, etc.)

    Args:
        endpoint_url: The full URL of the service or layer endpoint
            (e.g., "https://server/arcgis/rest/services/MyService/FeatureServer"
             or "https://server/arcgis/rest/services/MyService/FeatureServer/0")
        timeout: Request timeout in seconds. Default: 30
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        Dict containing:
            - success: Boolean indicating if request was successful
            - status_code: HTTP status code
            - data: JSON metadata from the service or layer
            - error: Error message if request failed, None otherwise

    Example:
        # Get feature service metadata (discover layers)
        result = await get_service_or_layer_details(
            endpoint_url="https://server/arcgis/rest/services/Parks/FeatureServer"
        )

        # Get layer-level metadata (fields, geometry type)
        result = await get_service_or_layer_details(
            endpoint_url="https://server/arcgis/rest/services/Parks/FeatureServer/0"
        )
    """
    resolved_token = resolve_token(token)

    logger.info(
        f"from get_service_or_layer_details: endpoint_url={endpoint_url}, "
        f"token={'<provided>' if resolved_token else None}"
    )

    return await _get_json_details(endpoint_url=endpoint_url, timeout=timeout, token=resolved_token)


@feature_service_router.tool
async def get_sample_feature_layer_data(
    endpoint_url: str, count: int = 5, timeout: int = 30, token: str | None = None
) -> dict[str, Any]:
    """
    Retrieve a small sample of features from a feature layer.

    Fetches a limited number of features to inspect field names, value formats,
    and data types before constructing a full query. Useful as a preview step
    to confirm the layer's schema matches expectations.

    Args:
        endpoint_url: The full URL of the feature layer endpoint
            (e.g., "https://server/arcgis/rest/services/MyService/FeatureServer/0").
            /query is appended automatically if not present.
        count: Number of sample features to retrieve. Default: 5
        timeout: Request timeout in seconds. Default: 30
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        Dict containing:
            - success: Boolean indicating if request was successful
            - status_code: HTTP status code
            - data: Sample features from the layer
            - error: Error message if request failed, None otherwise

    Example:
        result = await get_sample_feature_layer_data(
            endpoint_url="https://server/arcgis/rest/services/Parks/FeatureServer/0",
            count=3
        )
    """
    start_time = time.time()
    resolved_token = resolve_token(token)

    logger.info(
        f"from get_sample_feature_layer_data: endpoint_url={endpoint_url}, "
        f"count={count}, token={'<provided>' if resolved_token else None}"
    )

    try:
        params = {
            "resultRecordCount": count,
            "where": "1=1",
            "outFields": "*",
            "f": "json",
        }
        return await _query_feature_layer(
            endpoint_url=endpoint_url,
            parameters=params,
            timeout=timeout,
            token=resolved_token,
        )
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"get_sample_feature_layer_data completed in {elapsed_time:.2f} seconds.")


# endregion TOOLS


# ============================================================================
# region PROMPTS
# ============================================================================


@feature_service_router.prompt
def feature_layer_query_prompt(endpoint_url: str | None = "{endpoint_url}") -> str:
    """
    Generate a prompt for querying a feature layer.

    This prompt provides instructions for making an asynchronous REST request
    to a feature layer query endpoint with configurable parameters.

    Args:
        endpoint_url: The full URL of the feature layer query endpoint
    Returns:
        str: The generated prompt string
    """
    # Only include the endpoint line if a non-default value was provided.
    endpoint_url_value = (endpoint_url or "").strip()
    include_endpoint_line = bool(endpoint_url_value) and endpoint_url_value != "{endpoint_url}"

    lines = [
        "You are an AI agent that queries ArcGIS Feature Services.",
    ]

    if include_endpoint_line:
        lines.append(f"Feature layer URL: {endpoint_url_value}")

    lines += [
        "",
        "Goal: Answer the user's questions about feature layers by inspecting metadata and querying safely, efficiently, and with minimal data.",
        "If the user provides a URL ending in /FeatureServer or /MapServer, use get_service_or_layer_details first to discover available layers.",
        "",
        "Workflow (in order):",
        "1) Use get_service_or_layer_details to read layer schema/metadata (fields, geometry type, capabilities, etc.).",
        "2) Use get_sample_feature_layer_data (default 5) to confirm field names and value formats.",
        "3) If the request involves records, run a COUNT first using query_feature_layer with returnCountOnly=true.",
        "   - If the user only asked for a count, return the count and stop.",
        "4) If rows are needed:",
        "   - Page results in batches of 25 using resultRecordCount=25.",
        "   - Use resultOffset to fetch subsequent pages (offset = number of rows already returned).",
        "   - Use a stable orderByFields (often OBJECTID) when paging.",
        "",
        "Endpoint rules:",
        "- The query_feature_layer tool automatically appends /query to the URL if needed.",
        "- Always set f=json.",
        "",
        "Query construction rules:",
        "- Always include OBJECTID in outFields if the layer supports it.",
        "- Prefer explicit outFields over '*' when returning many records.",
        "- Use where='1=1' only when no filter is needed.",
        "- Set returnGeometry=false unless geometry is required.",
        "- If you must do distance or area calculations, request WGS84 with outSR={wkid:4326}.",
        "",
        "Common parameters:",
        "- where: SQL-like filter (e.g., status = 'active')",
        "- outFields: comma-separated fields (e.g., OBJECTID,name,status)",
        "- returnGeometry: true|false",
        "- resultRecordCount: page size",
        "- resultOffset: page offset",
        "- orderByFields: stable ordering for paging (often OBJECTID)",
        "",
        "Response expectations:",
        "- Summarize findings clearly.",
        "- If returning tabular data, return only the minimum rows needed and mention how many total records exist.",
    ]

    return "\n".join(lines)


# endregion PROMPTS


# ============================================================================
# region RESOURCES
# ============================================================================


@feature_service_router.resource(uri="resource://feature_service/query_info")
def feature_service_query_info() -> str:
    """
    Provide information about querying feature services.

    Returns:
        str: Information about the feature service query tool
    """

    # Get the directory of the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    md_file_path = os.path.join(current_dir, "query_feature_service.md")

    fallback_message = (
        "This resource provides information about querying feature services. "
        "You can use the 'query_feature_layer' tool to make asynchronous REST requests "
        "to feature service query endpoints with configurable parameters."
    )

    try:
        with open(md_file_path, encoding="utf-8") as f:
            file_contents = f.read()
            return fallback_message + "\n\n" + file_contents
    except FileNotFoundError:
        return fallback_message


# endregion RESOURCES
