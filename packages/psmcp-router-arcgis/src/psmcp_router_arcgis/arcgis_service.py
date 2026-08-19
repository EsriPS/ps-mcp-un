"""
ArcGIS Service MCP Router

This module provides tools for interacting with ArcGIS Enterprise, including
authentication, user management, and content discovery.
"""

# ============================================================================
# region CONFIGURATION
# ============================================================================

import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import requests
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from requests.exceptions import HTTPError

from psmcp.core.auth import resolve_token
from psmcp_router_arcgis.arcgis_auth import AuthenticationError, ServiceUnavailableError

logger = logging.getLogger(__name__)

# endregion CONFIGURATION

# ============================================================================
# region CONSTANTS
# ============================================================================

# ArcGIS Portal Configuration
ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
ARCGIS_VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"
# ArcGIS Server base URL — defaults to {portal_host}/server if not set.
# Override when the server web adaptor uses a non-default context (e.g., /arcgisserver).
ARCGIS_SERVER_URL = os.getenv("ARCGIS_SERVER_URL")

# endregion CONSTANTS

# ============================================================================
# region MODULE INITIALIZATION
# ============================================================================

arcgis_router = FastMCP(name="ArcGIS Service Router")


# endregion MODULE INITIALIZATION

# ============================================================================
# region HELPER FUNCTIONS
# ============================================================================


async def get_user_info_from_token(token: str) -> dict[str, Any]:
    """
    Get user information for a token by calling the ArcGIS Portal API.

    Args:
        token: Valid ArcGIS token

    Returns:
        Dict containing user information

    Raises:
        AuthenticationError: If token is invalid
        ServiceUnavailableError: If portal is unavailable
    """
    if not ARCGIS_PORTAL_URL:
        raise ValueError("ARCGIS_PORTAL_URL is required")

    response = None
    try:
        url = f"{ARCGIS_PORTAL_URL}/sharing/rest/community/self"
        params = {"token": token, "f": "json"}

        response = requests.get(url, params=params, verify=ARCGIS_VERIFY_SSL)

        if response.status_code != 200:
            raise AuthenticationError(
                message="Invalid token or unable to connect to ArcGIS Enterprise",
                status_code=401,
            )

        user_data = response.json()

        if "error" in user_data:
            raise AuthenticationError(
                message=f"Token validation failed: {user_data['error'].get('message', 'Unknown error')}",
                status_code=401,
            )

        return {
            "username": user_data.get("username"),
            "fullName": user_data.get("fullName"),
            "email": user_data.get("email"),
            "role": user_data.get("role"),
            "orgId": user_data.get("orgId"),
            "privileges": user_data.get("privileges", []),
        }

    except requests.RequestException as e:
        raise ServiceUnavailableError(
            message=f"Unable to connect to ArcGIS Enterprise: {e!s}",
            status_code=response.status_code if response else 503,
        ) from e


async def authenticate_token(token: str | None = None) -> dict[str, Any]:
    """
    Helper function to authenticate an ArcGIS token and retrieve user info.
    Args:
        token (str, optional): ArcGIS Enterprise authentication token. If not provided,
            will attempt to get token from the authentication context.
    Returns:
        Dict[str, Any]: User information if token is valid.
    Raises:
        AuthenticationError: If token is invalid or expired.
        ServiceUnavailableError: If unable to connect to ArcGIS Enterprise.
        ValueError: If no token is available.
    """
    try:
        resolved_token = resolve_token(token, required=True)
        user_info = await get_user_info_from_token(resolved_token)
        logger.info(f"Retrieved user info for: {user_info.get('username')}")
        return user_info

    except AuthenticationError as e:
        logger.error(f"Authentication error in authenticate_token: {e.message}")
        return {"error": e.message, "status_code": e.status_code}
    except ServiceUnavailableError as e:
        logger.error(f"Service unavailable in authenticate_token: {e.message}")
        return {"error": e.message, "status_code": e.status_code}


# endregion HELPER FUNCTIONS
# ============================================================================

# ============================================================================
# region TOOLS
# ============================================================================


@arcgis_router.tool
async def get_user_info(token: str | None = None) -> dict[str, Any]:
    """
    Get detailed information about the authenticated user.

    This tool validates the provided ArcGIS Enterprise token and returns
    comprehensive user information including username, full name, email,
    role, organization ID, and privileges.

    Args:
        token: Valid ArcGIS Enterprise authentication token (optional, uses auth context if not provided)

    Returns:
        Dict containing user information:
            - username: User's username
            - fullName: User's full display name
            - email: User's email address
            - role: User's role in the organization
            - orgId: Organization ID
            - privileges: List of user privileges

    Raises:
        AuthenticationError: If token is invalid or expired
        ServiceUnavailableError: If unable to connect to ArcGIS Enterprise
    """
    start_time = time.time()

    logger.info("get_user_info called")
    try:
        user_info = await authenticate_token(token)
        return user_info
    except Exception as e:
        logger.error(f"Unexpected error in get_user_info: {e!s}")
        return {"error": f"Unexpected error: {e!s}", "status_code": 500}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"get_user_info completed in {elapsed_time:.2f} seconds.")


@arcgis_router.tool
async def list_system_services(
    portal_url: str | None = None, token: str | None = None
) -> ToolResult:
    """
    List available system services (GPServers) for the configured portal.

    This tool queries the ArcGIS Portal/Server to retrieve System GP Services. GP Services published by users will not be included in this list.
    Find user published GP services with the search_portal tool if available.

    Args:
        portal_url: Optional custom portal URL. If not provided, uses ARCGIS_PORTAL_URL from environment.
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        ToolResult with a list of available GPServer services including name, url, and type.
    """
    start_time = time.time()

    # Resolve portal URL
    resolved_portal_url = portal_url or ARCGIS_PORTAL_URL
    if not resolved_portal_url:
        return ToolResult(
            structured_content={
                "error": "No portal URL configured. Provide portal_url parameter or set ARCGIS_PORTAL_URL environment variable.",
                "services": [],
            }
        )

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    # Normalize portal URL - extract base URL (scheme + host) removing any path like /portal
    parsed = urlparse(resolved_portal_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Resolve server URL. When portal_url is explicitly provided, derive the server
    # from that portal to avoid mixing a per-call portal override with a process-wide
    # ARCGIS_SERVER_URL that may point at a different host/context. Otherwise, keep
    # existing environment-based behavior.
    server_base = f"{base_url}/server" if portal_url else ARCGIS_SERVER_URL or f"{base_url}/server"
    server_base = server_base.rstrip("/")

    logger.info(
        "from list_system_services: portal_url=%s, server_base=%s, token=%s",
        resolved_portal_url,
        server_base,
        "<provided>" if resolved_token else None,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=ARCGIS_VERIFY_SSL) as client:
            # Build request URL using the resolved server base URL
            services_url = f"{server_base}/rest/services/System"
            params = {"f": "json"}
            if resolved_token:
                params["token"] = resolved_token

            response = await client.get(services_url, params=params)
            response.raise_for_status()

            data = response.json()

            # Check for error in response
            if "error" in data:
                error_msg = data["error"].get("message", "Unknown error")
                return ToolResult(
                    structured_content={
                        "error": f"ArcGIS API error: {error_msg}",
                        "services": [],
                    }
                )

            # Extract services and filter to GPServer types
            raw_services = data.get("services", [])
            services = []

            for svc in raw_services:
                svc_name = svc.get("name", "")
                svc_type = svc.get("type", "")

                # Only include GPServer services
                if svc_type == "GPServer":
                    services.append(
                        {
                            "name": svc_name,
                            "type": svc_type,
                            "url": f"{server_base}/rest/services/{svc_name}",
                        }
                    )

            elapsed_time = time.time() - start_time

            return ToolResult(
                structured_content={
                    "portal_url": base_url,
                    "total_services": len(services),
                    "services": services,
                    "elapsed_time": elapsed_time,
                }
            )

    except httpx.HTTPError as e:
        logger.error("HTTP error in list_system_services", exc_info=True)
        return ToolResult(
            structured_content={
                "error": f"HTTP error occurred: {e!s}",
                "error_type": type(e).__name__,
                "services": [],
            }
        )
    except Exception as e:
        logger.error("Unexpected error in list_system_services", exc_info=True)
        return ToolResult(
            structured_content={
                "error": f"Unexpected error occurred: {e!s}",
                "error_type": type(e).__name__,
                "services": [],
            }
        )
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"list_system_services completed in {elapsed_time:.2f} seconds.")


@arcgis_router.tool
async def get_item_info(
    item_id: str, include_data: bool = False, token: str | None = None
) -> dict[str, Any]:
    """
    Get detailed information about a specific content item.

    This tool retrieves comprehensive metadata about an ArcGIS Enterprise
    content item, including its type, description, tags, sharing settings,
    and other properties.

    Args:
        item_id: Unique identifier of the item
        include_data: If true, include detailed information about item from the /data endpoint
        token: Valid ArcGIS Enterprise authentication token (optional, uses auth context if not provided)

    Returns:
        Dict containing item information:
            - id: Item ID
            - owner: Item owner username
            - title: Item title
            - type: Item type (e.g., 'Web Map', 'Feature Service')
            - description: Item description
            - tags: List of tags
            - url: Item URL (if applicable)
            - access: Sharing level (private, org, public)
            - created: Creation timestamp
            - modified: Last modified timestamp
            - Other item-specific properties

    Raises:
        AuthenticationError: If token is invalid or expired
        ServiceUnavailableError: If unable to connect to ArcGIS Enterprise
        HTTPError: If the ArcGIS REST API returns an error response
    """
    start_time = time.time()

    logger.info(f"get_item_info called for item_id: {item_id}")

    try:
        # Resolve and authenticate token first
        resolved_token = resolve_token(token, required=True)
        # Authenticate for its side effect: raises if the token is invalid.
        await authenticate_token(resolved_token)

        # Make REST API call to get item info
        url = f"{ARCGIS_PORTAL_URL}/sharing/rest/content/items/{item_id}"
        params = {"token": resolved_token, "f": "json"}

        response = requests.get(url, params=params, verify=ARCGIS_VERIFY_SSL)
        if response.status_code != 200:
            raise HTTPError(f"Unexpected status code: {response.status_code}")

        data = response.json()

        # Check if the response indicates an error
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            logger.error(f"ArcGIS API error: {error_msg}")
            return {"error": error_msg, "status_code": data["error"].get("code", 500)}

        # If include_data is True, fetch the item data from /data endpoint
        if include_data:
            data_url = f"{ARCGIS_PORTAL_URL}/sharing/rest/content/items/{item_id}/data"
            data_params = {"token": resolved_token, "f": "json"}

            logger.info(f"Fetching item data from /data endpoint for item_id: {item_id}")
            data_response = requests.get(data_url, params=data_params, verify=ARCGIS_VERIFY_SSL)

            if data_response.status_code == 200:
                try:
                    item_data = data_response.json()
                    # Check if the data response indicates an error
                    if "error" not in item_data:
                        data["itemData"] = item_data
                        logger.info(f"Successfully retrieved item data for item_id: {item_id}")
                    else:
                        logger.warning(
                            f"Item data endpoint returned error for item_id {item_id}: {item_data.get('error')}"
                        )
                except Exception as e:
                    # If the response is not JSON (e.g., file download), log it but don't fail
                    logger.warning(
                        f"Could not parse item data as JSON for item_id {item_id}: {e!s}"
                    )
                    data["itemDataNote"] = (
                        "Item data is not in JSON format or could not be retrieved"
                    )
            else:
                logger.warning(
                    f"Failed to fetch item data for item_id {item_id}, status code: {data_response.status_code}"
                )

        return data

    except Exception as e:
        logger.error(f"Error in get_item_info: {e!s}")
        return {"error": f"Error: {e!s}", "status_code": 500}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"get_item_info completed in {elapsed_time:.2f} seconds.")


@arcgis_router.tool
async def search_portal(
    q: str,
    filter: str | None = None,
    start: int = 1,
    num: int = 10,
    sortField: str | None = None,
    sortOrder: str = "asc",
    token: str | None = None,
) -> dict[str, Any]:
    """
    Search for items in the ArcGIS Enterprise portal.

    This tool searches for content items (maps, layers, apps, services, etc.)
    in the ArcGIS Enterprise portal using the REST API search endpoint.
    It supports full-text search, structured filtering, pagination, and sorting.

    Args:
        q: The query string used to search. Supports keyword searches and field-specific queries.
            Examples:
                - "redlands" - Simple keyword search
                - "title:California AND type:Web Map" - Search by title and type
                - "owner:jsmith" - Search by owner
                - "tags:transportation" - Search by tags
                - "modified:[2024-01-01 TO 2024-12-31]" - Search by date range
                - "access:public" - Search by access level (private, org, public)

        filter: Structured filtering using field:value syntax with double quotes.
            Examples:
                - 'type:"Web Map"' - Filter by Web Maps only
                - 'type:"Feature Service"' - Filter by Feature Services
                - 'type:"Web Mapping Application"' - Filter by Web Apps
                - 'owner:"admin"' - Filter by specific owner
                - 'orgid:"0123456789ABCDEF"' - Filter by organization ID
                - 'group:"1652a410f59c4d8f98fb87b25e0a2669"' - Filter by group ID
                - 'type:"Web Map" AND owner:"admin"' - Combine multiple filters

        start: The result number of the first entry in the response (1-based index).
            Default is 1. Use with 'num' for pagination.
            Examples:
                - 1 - First page of results
                - 11 - Second page (if num=10)

        num: Maximum number of results to return. Default is 10, maximum is 100.

        sortField: Field to sort results by. Can sort by multiple fields (comma-separated).
            Supported fields: title, created, type, owner, modified, avgrating,
            numratings, numcomments, numviews, scorecompleteness.
            Examples:
                - "title" - Sort by title
                - "modified" - Sort by last modified date
                - "numviews" - Sort by view count
                - "created" - Sort by creation date
                - "avgrating" - Sort by average rating

        sortOrder: Sort order for results. Values: "asc" (ascending) or "desc" (descending).
            Default is "asc".
            Examples:
                - "asc" - Ascending order (A-Z, oldest first)
                - "desc" - Descending order (Z-A, newest first)

        token: Valid ArcGIS Enterprise authentication token (optional, uses auth context if not provided)

    Returns:
        Dict containing:
            - results: Array of search result items with metadata (id, title, type, owner, snippet, tags, etc.)
            - total: Total number of results matching the query
            - start: Starting index of returned results
            - num: Number of items returned
            - nextStart: Starting index for next page of results (-1 if no more results)
            - query: The query string that was executed

    Raises:
        AuthenticationError: If token is invalid or expired
        ServiceUnavailableError: If unable to connect to ArcGIS Enterprise
        HTTPError: If the ArcGIS REST API returns an error response

    Example Usage:
        # Search for all web maps
        search_portal(q="*", filter='type:"Web Map"')

        # Search for items owned by a specific user, sorted by modification date
        search_portal(q="owner:jsmith", sortField="modified", sortOrder="desc")

        # Paginate through results
        search_portal(q="transportation", start=1, num=25)  # First 25 results
        search_portal(q="transportation", start=26, num=25)  # Next 25 results

        # Search for public feature services with high view counts
        search_portal(q="access:public", filter='type:"Feature Service"', sortField="numviews", sortOrder="desc")
    """
    start_time = time.time()

    logger.info(
        f"search_portal called with q='{q}', filter='{filter}', start={start}, num={num}, sortField='{sortField}'"
    )

    try:
        resolved_token = resolve_token(token, required=True)
        await authenticate_token(resolved_token)

        # Build the request URL and parameters
        url = f"{ARCGIS_PORTAL_URL}/sharing/rest/search"
        params = {
            "q": q,
            "start": start,
            "num": min(num, 100),  # Cap at maximum allowed value
            "f": "json",
            "token": resolved_token,
        }

        # Add optional parameters if provided
        if filter:
            params["filter"] = filter
        if sortField:
            params["sortField"] = sortField
            params["sortOrder"] = sortOrder

        response = requests.get(url, params=params, verify=ARCGIS_VERIFY_SSL)

        if response.status_code != 200:
            raise HTTPError(f"Unexpected status code: {response.status_code}")

        data = response.json()

        # Check if the response indicates an error
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            logger.error(f"ArcGIS API error in search_portal: {error_msg}")
            return {"error": error_msg, "status_code": data["error"].get("code", 500)}

        logger.info(
            "search_portal found %d total results, returning %d items",
            data.get("total", 0),
            len(data.get("results", [])),
        )

        # Include the portal URL so clients know which portal these results came from
        data["portal_url"] = ARCGIS_PORTAL_URL

        return data

    except Exception as e:
        logger.error(f"Error in search_portal: {e!s}")
        return {"error": f"Error: {e!s}", "status_code": 500}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"search_portal completed in {elapsed_time:.2f} seconds.")


@arcgis_router.tool
async def list_user_groups(
    num: int = 10, start: int = 1, token: str | None = None
) -> dict[str, Any]:
    """
    List groups that the authenticated user is a member of in ArcGIS Enterprise.

    This tool retrieves a list of groups where the authenticated user has membership.

    Args:
        num: Maximum number of groups to return (default: 10, max: 100)
        start: Starting index for pagination (default: 1)
        token: Valid ArcGIS Enterprise authentication token (optional, uses auth context if not provided)

    Returns:
        Dict containing:
            - results: List of group objects with metadata (id, title, owner, description, etc.)
            - total: Total number of groups the user is a member of
            - start: Starting index of returned results
            - num: Number of groups returned
            - nextStart: Starting index for next page of results

    Raises:
        AuthenticationError: If token is invalid or expired
        ServiceUnavailableError: If unable to connect to ArcGIS Enterprise
        HTTPError: If the ArcGIS REST API returns an error response
    """
    start_time = time.time()

    logger.info("list_user_groups called")

    try:
        # Resolve and authenticate token first
        resolved_token = resolve_token(token, required=True)
        user_info = await authenticate_token(resolved_token)

        # Make REST API call to get user's groups
        url = f"{ARCGIS_PORTAL_URL}/sharing/rest/community/groups"
        params = {
            "token": resolved_token,
            "f": "json",
            "num": min(num, 100),
            "start": start,
            "searchUserAccess": "groupMember",
        }

        response = requests.get(url, params=params, verify=ARCGIS_VERIFY_SSL)
        if response.status_code != 200:
            raise HTTPError(f"Unexpected status code: {response.status_code}")

        data = response.json()

        # Check if the response indicates an error
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            logger.error(f"ArcGIS API error: {error_msg}")
            return {"error": error_msg, "status_code": data["error"].get("code", 500)}

        logger.info(
            f"Retrieved {len(data.get('results', []))} groups for user {user_info.get('username')}"
        )
        return data

    except Exception as e:
        logger.error(f"Error in list_user_groups: {e!s}")
        return {"error": f"Error: {e!s}", "status_code": 500}
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"list_user_groups completed in {elapsed_time:.2f} seconds.")


# endregion TOOLS
# ============================================================================

# ============================================================================
# region PROMPTS
# ============================================================================


@arcgis_router.prompt(name="arcgis_enterprise_prompt")
def arcgis_enterprise_prompt(token: str | None = "{token}") -> str:
    """
    Prompt template for ArcGIS Enterprise operations.

    This prompt provides instructions for interacting with ArcGIS Enterprise,
    including authentication, user management, and content discovery.

    Args:
        token: The ArcGIS Enterprise authentication token

    Returns:
        A string prompt template.
    """
    return (
        f"You are a helpful assistant that interacts with ArcGIS Enterprise. "
        f"You have access to tools for authentication, user management, and content discovery.\n\n"
        f"### Portal Configuration:\n"
        f"- Portal URL: {ARCGIS_PORTAL_URL}\n"
        f"- Authentication Token: {token}\n\n"
        f"### Available Tools:\n"
        f"- 'get_user_info': Validate the authentication token and retrieve user information\n"
        f"- 'search_portal': Search for items in the portal with flexible filtering "
        f"(q, filter, sortField, etc.)\n"
        f"- 'list_user_groups': List groups that the authenticated user is a member of\n"
        f"- 'get_item_info': Get detailed information about a specific content item\n"
        f"- 'list_system_services': List available system GP services\n\n"
        f"### Instructions:\n"
        f"Answer user questions about content found within ArcGIS Enterprise.\n"
        f"Use 'search_portal' with q='owner:username' to list content owned by a user.\n"
        f"Use 'list_user_groups' to discover groups the user belongs to, then use "
        f"'search_portal' with filter='group:\"group_id\"' to explore content shared "
        f"within those groups.\n"
        f"When calling search_portal or list_user_groups, make use of pagination parameters "
        f"(start, num) to get up to 100 items at a time, informing the user if more items "
        f"are available.\n"
        f"Use 'get_item_info' to provide detailed information about specific items "
        f"when requested.\n\n"
        f"### Response Guidelines:\n"
        f"- Provide accurate information based on the API responses\n"
        f"- If an error occurs, explain it clearly to the user\n"
        f"- Respect user permissions and access levels\n"
        f"- When listing content, provide meaningful summaries\n"
    )


# endregion PROMPTS
# ============================================================================
