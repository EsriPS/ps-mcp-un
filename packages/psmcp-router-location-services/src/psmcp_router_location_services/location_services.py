"""
Location Services MCP Router

This module provides tools for geocoding and location-based services,
including address geocoding via the ArcGIS World Geocoding Service.
"""

# ============================================================================
# region CONFIGURATION
# ============================================================================

import logging
import os
import time

import httpx
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from psmcp.core.auth import resolve_token

logger = logging.getLogger(__name__)

# ============================================================================
# region CONSTANTS
# ============================================================================

# ArcGIS Portal Configuration
ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
ARCGIS_VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"
GEOCODE_URL = os.getenv("ARCGIS_GEOCODE_SERVICE_URL")
USE_ARCGIS_AUTH = os.getenv("USE_ARCGIS_AUTH", "False").lower() == "true"

# endregion CONSTANTS

# ============================================================================
# region MODULE INITIALIZATION
# ============================================================================

location_services_router = FastMCP(name="Location Services")

# endregion MODULE INITIALIZATION

# ============================================================================
# region HELPER FUNCTIONS
# ============================================================================


def _is_auth_error(data: dict) -> bool:
    """Check if an ArcGIS JSON error response indicates an authentication failure."""
    error = data.get("error", {})
    code = error.get("code", 0)
    # ArcGIS REST API uses 498 (invalid token) and 499 (token required)
    if code in (401, 403, 498, 499):
        return True
    message = (error.get("message") or "").lower()
    return any(
        keyword in message for keyword in ("token", "authentication", "unauthorized", "forbidden")
    )


async def _geocode_request(
    client: httpx.AsyncClient,
    geocode_url: str,
    single_line: str,
    out_sr: int,
    max_locations: int,
    token: str | None,
) -> dict:
    """
    Send a single geocode request and return the parsed JSON response.

    Uses "SingleLine" parameter for Portal/Enterprise geocode services.
    """
    params = {
        "SingleLine": single_line,
        "outSR": out_sr,
        "maxLocations": min(max_locations, 50),
        "f": "json",
    }
    if token:
        params["token"] = token

    response = await client.get(geocode_url, params=params)
    response.raise_for_status()
    return response.json()


# endregion HELPER FUNCTIONS

# ============================================================================
# region TOOLS
# ============================================================================


@location_services_router.tool
async def find_address_candidates(
    single_line: str,
    out_sr: int = 4326,
    max_locations: int = 5,
    token: str | None = None,
) -> ToolResult:
    """
    Find coordinate candidates for an address using the ArcGIS World Geocoding Service.

    This tool geocodes an address string and returns candidate locations with
    coordinates, scores, and address attributes.

    Args:
        single_line: The address to geocode as a single line string.
            Examples:
                - "380 New York St, Redlands, CA 92373"
                - "1600 Pennsylvania Avenue NW, Washington, DC"
                - "Eiffel Tower, Paris, France"
        out_sr: The spatial reference for the output coordinates (WKID).
            Default is 4326 (WGS84 latitude/longitude).
            Common values:
                - 4326: WGS84 (latitude/longitude)
                - 3857: Web Mercator
                - 102100: Web Mercator (alternate WKID)
        max_locations: Maximum number of candidate locations to return.
            Default is 5. Maximum is 50.
        token: Optional authentication token. If not provided, uses token from
            authentication context. Required for some geocoding operations.

    Returns:
        ToolResult containing:
            - candidates: List of address candidates sorted by decreasing score (higher is better), each with:
                - address: The matched address string
                - location: Dict with x (longitude) and y (latitude) coordinates
                - score: Match score (0-100, higher is better)
                - attributes: Additional address attributes
            - spatial_reference: The spatial reference of the coordinates
            - elapsed_time: Time taken for the request

    Example:
        result = await find_address_candidates(
            single_line="380 New York St, Redlands, CA",
            out_sr=4326
        )
    """
    start_time = time.time()

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    # Only send the token on the first request if USE_ARCGIS_AUTH is enabled.
    # If auth is not enabled, try without a token first; on an auth error,
    # retry once with the token (if available).
    send_token = resolved_token if (USE_ARCGIS_AUTH and resolved_token) else None

    logger.info(
        f"find_address_candidates called: single_line='{single_line}', "
        f"out_sr={out_sr}, max_locations={max_locations}, "
        f"USE_ARCGIS_AUTH={USE_ARCGIS_AUTH}, "
        f"token={'<provided>' if resolved_token else None}, "
        f"sending_token={'yes' if send_token else 'no'}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=ARCGIS_VERIFY_SSL) as client:
            # Build the geocode request URL
            geocode_url = f"{GEOCODE_URL}/findAddressCandidates"

            data = await _geocode_request(
                client, geocode_url, single_line, out_sr, max_locations, send_token
            )

            # If we got an auth error and didn't send a token, retry with the token
            if "error" in data and not send_token and resolved_token and _is_auth_error(data):
                logger.info(
                    "Geocode request returned auth error without token; retrying with token"
                )
                data = await _geocode_request(
                    client, geocode_url, single_line, out_sr, max_locations, resolved_token
                )

            # Check for error in response
            if "error" in data:
                error_msg = data["error"].get("message", "Unknown error")
                logger.error(f"Geocoding error: {error_msg}")
                return ToolResult(
                    structured_content={
                        "error": f"Geocoding error: {error_msg}",
                        "candidates": [],
                    }
                )

            # Extract candidates
            candidates = data.get("candidates", [])
            spatial_reference = data.get("spatialReference", {"wkid": out_sr})

            elapsed_time = time.time() - start_time

            logger.info(
                f"find_address_candidates found {len(candidates)} candidates "
                f"in {elapsed_time:.2f} seconds"
            )

            return ToolResult(
                structured_content={
                    "candidates": candidates,
                    "spatial_reference": spatial_reference,
                    "total_candidates": len(candidates),
                    "elapsed_time": elapsed_time,
                }
            )

    except httpx.HTTPError as e:
        logger.error("HTTP error in find_address_candidates", exc_info=True)
        return ToolResult(
            structured_content={
                "error": f"HTTP error occurred: {e!s}",
                "error_type": type(e).__name__,
                "candidates": [],
            }
        )
    except Exception as e:
        logger.error("Unexpected error in find_address_candidates", exc_info=True)
        return ToolResult(
            structured_content={
                "error": f"Unexpected error occurred: {e!s}",
                "error_type": type(e).__name__,
                "candidates": [],
            }
        )
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"find_address_candidates completed in {elapsed_time:.2f} seconds.")


# endregion TOOLS
# ============================================================================
