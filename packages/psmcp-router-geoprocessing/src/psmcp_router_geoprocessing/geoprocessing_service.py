"""
ArcGIS Geoprocessing Server (GPServer) Analysis Service.

This module provides a dynamic GP catalog resource and tools for discovering,
executing, and monitoring ArcGIS GPServer tasks through the REST API.

Architecture:
    - Dynamic Resource (GP Catalog): Lightweight catalog of all GP services/tasks
      accessible to the current user. Fetched once per session.
    - Tool (get_gp_task_details): Full parameter schema retrieval for a selected task.
    - Tool (execute_gp_task): Submit a GP task for execution (sync or async).
    - Tool (check_gp_job_status): Poll status of an asynchronous GP job.
    - Tool (get_gp_job_results): Retrieve output values from a completed GP job.
"""

import json
import logging
import os
import time
from enum import StrEnum
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.resources import ResourceContent, ResourceResult

from psmcp.core.auth import resolve_token

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# SSL certificate verification — set ARCGIS_VERIFY_SSL=false to disable (e.g. self-signed certs)
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"

# ArcGIS Portal Configuration (from environment)
ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")

# Default tags for filtering GP services (comma-separated, e.g., "MCP,mcp")
# If not set, no tag filtering is applied by default
_default_tags_env = os.getenv("GP_CATALOG_DEFAULT_TAGS", "")
DEFAULT_GP_TAGS: list[str] | None = [
    t.strip() for t in _default_tags_env.split(",") if t.strip()
] or None


# ============================================================================
# CONSTANTS
# ============================================================================


class JobStatus(StrEnum):
    """GPServer job status values."""

    SUBMITTED = "esriJobSubmitted"
    WAITING = "esriJobWaiting"
    EXECUTING = "esriJobExecuting"
    SUCCEEDED = "esriJobSucceeded"
    FAILED = "esriJobFailed"
    TIMED_OUT = "esriJobTimedOut"
    CANCELLING = "esriJobCancelling"
    CANCELLED = "esriJobCancelled"
    ERROR = "esriJobMessageTypeError"


# Terminal states that indicate the job is complete
TERMINAL_STATES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.TIMED_OUT,
    JobStatus.CANCELLED,
    JobStatus.ERROR,
}


# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

geoprocessing_router = FastMCP(name="Geoprocessing Service")


# ============================================================================
# region HELPER FUNCTIONS
# ============================================================================


def _ensure_gpserver_url(service_url: str) -> str:
    """
    Ensure the URL ends with /GPServer exactly once.

    Portal search results typically include /GPServer in the URL already,
    but callers may pass the base service URL without it.
    """
    base = service_url.rstrip("/")
    if base.lower().endswith("/gpserver"):
        # Normalize the GPServer suffix casing while preserving the rest of the URL
        return base[:-9] + "/GPServer"
    return f"{base}/GPServer"


async def _search_gp_services(
    client: httpx.AsyncClient,
    portal_url: str,
    token: str | None = None,
    start: int = 1,
    num: int = 100,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Search the ArcGIS Portal for Geoprocessing Service items accessible to the user.

    Only returns GP services matching the specified tags, giving users control
    over which GP services participate in the MCP workflow.

    Paginates through all results to return a complete list of GP service items.

    Args:
        client: HTTP client for making requests
        portal_url: Base URL of the ArcGIS Portal
        token: Authentication token
        start: Starting index for pagination
        num: Number of results per page
        tags: List of tags to filter GP services. Defaults to GP_CATALOG_DEFAULT_TAGS env var.
              If env var is not set, no tag filtering is applied.

    Returns:
        List of GP service item dicts with id, title, description, and url
    """
    search_url = f"{portal_url}/sharing/rest/search"
    all_items = []

    # Use provided tags, or fall back to environment default
    if tags is None:
        tags = DEFAULT_GP_TAGS

    # Build the tags query
    if tags:
        tags_query = " OR ".join(f'tags:"{tag}"' for tag in tags)
        query = f'type:"Geoprocessing Service" AND ({tags_query})'
    else:
        query = 'type:"Geoprocessing Service"'

    while True:
        params = {"q": query, "start": start, "num": min(num, 100), "f": "json"}
        if token:
            params["token"] = token

        response = await client.get(search_url, params=params)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            logger.error(f"Portal search error: {error_msg}")
            break

        results = data.get("results", [])
        for item in results:
            all_items.append(
                {
                    "item_id": item.get("id"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                    "tags": item.get("tags", []),
                }
            )

        next_start = data.get("nextStart", -1)
        if next_start == -1 or next_start <= start:
            break
        start = next_start

    return all_items


async def _crawl_gp_service(
    client: httpx.AsyncClient, service_url: str, token: str | None = None
) -> dict[str, Any]:
    """
    Crawl a GP service endpoint to extract service metadata and task names/descriptions.

    Args:
        client: HTTP client for making requests
        service_url: Base URL of the GP service
        token: Authentication token

    Returns:
        Dict containing service metadata and lightweight task info
    """
    # Portal search results may already include /GPServer in the URL
    gpserver_url = _ensure_gpserver_url(service_url)
    params = {"f": "json"}
    if token:
        params["token"] = token

    response = await client.get(gpserver_url, params=params)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        error_msg = data["error"].get("message", "Unknown error")
        logger.warning(f"Error crawling GP service {service_url}: {error_msg}")
        return {"error": error_msg}

    service_info = {
        "service_name": data.get("serviceName", ""),
        "service_description": data.get("serviceDescription", "") or data.get("description", ""),
        "service_url": service_url.rstrip("/"),
        "tasks": [],
    }

    # Extract task names from the service
    task_names = data.get("tasks", [])

    for task_name in task_names:
        # Fetch task-level metadata for description
        task_info = await _fetch_task_description(client, service_url, task_name, token)
        service_info["tasks"].append(task_info)

    return service_info


async def _fetch_task_description(
    client: httpx.AsyncClient,
    service_url: str,
    task_name: str,
    token: str | None = None,
) -> dict[str, str]:
    """
    Fetch lightweight task metadata (name and description only) from the task endpoint.

    Args:
        client: HTTP client for making requests
        service_url: Base URL of the GP service
        task_name: Name of the task
        token: Authentication token

    Returns:
        Dict with task_name and task_description
    """
    task_url = f"{_ensure_gpserver_url(service_url)}/{task_name}"
    params = {"f": "json"}
    if token:
        params["token"] = token

    try:
        response = await client.get(task_url, params=params)
        response.raise_for_status()
        data = response.json()

        return {
            "task_name": task_name,
            "task_description": data.get("description", "") or data.get("displayName", task_name),
        }
    except Exception as e:
        logger.warning(f"Could not fetch description for task {task_name}: {e}")
        return {"task_name": task_name, "task_description": ""}


async def _fetch_task_details(
    client: httpx.AsyncClient,
    service_url: str,
    task_name: str,
    token: str | None = None,
) -> dict[str, Any]:
    """
    Fetch the full parameter schema for a GP task.

    Args:
        client: HTTP client for making requests
        service_url: Base URL of the GP service
        task_name: Name of the task
        token: Authentication token

    Returns:
        Dict containing full task metadata including input/output parameters
    """
    task_url = f"{_ensure_gpserver_url(service_url)}/{task_name}"
    params = {"f": "json"}
    if token:
        params["token"] = token

    response = await client.get(task_url, params=params)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        return {"error": data["error"].get("message", "Unknown error")}

    # Parse input and output parameters
    input_parameters = []
    output_parameters = []

    for param in data.get("parameters", []):
        param_info = {
            "name": param.get("name", ""),
            "description": param.get("description", "") or param.get("displayName", ""),
            "data_type": param.get("dataType", ""),
            "default_value": param.get("defaultValue"),
            "required": param.get("parameterType", "") == "esriGPParameterTypeRequired",
            "choice_list": param.get("choiceList", []) or [],
        }

        direction = param.get("direction", "")
        if direction == "esriGPParameterDirectionInput":
            input_parameters.append(param_info)
        elif direction == "esriGPParameterDirectionOutput":
            output_parameters.append(
                {
                    "name": param_info["name"],
                    "description": param_info["description"],
                    "data_type": param_info["data_type"],
                }
            )

    return {
        "task_name": data.get("name", task_name),
        "task_description": data.get("description", ""),
        "execution_type": data.get("executionType", ""),
        "input_parameters": input_parameters,
        "output_parameters": output_parameters,
    }


async def _submit_gp_job(
    client: httpx.AsyncClient,
    gp_service_url: str,
    task_name: str,
    parameters: dict[str, Any],
    token: str | None = None,
) -> dict[str, Any]:
    """
    Submit a geoprocessing job to ArcGIS GPServer.

    Args:
        client: HTTP client for making requests
        gp_service_url: Base URL of the geoprocessing service
        task_name: Name of the geoprocessing task
        parameters: Input parameters for the task
        token: Optional authentication token

    Returns:
        Dict containing jobId and initial jobStatus

    Raises:
        httpx.HTTPError: If the request fails
    """
    submit_url = f"{_ensure_gpserver_url(gp_service_url)}/{task_name}/submitJob"

    # Add format parameter and token if provided
    submit_params = {**parameters, "f": "json"}
    if token:
        submit_params["token"] = token

    response = await client.post(submit_url, data=submit_params)
    response.raise_for_status()

    return response.json()


async def _execute_gp_task_sync(
    client: httpx.AsyncClient,
    gp_service_url: str,
    task_name: str,
    parameters: dict[str, Any],
    token: str | None = None,
) -> dict[str, Any]:
    """
    Execute a synchronous geoprocessing task and return results directly.

    Args:
        client: HTTP client for making requests
        gp_service_url: Base URL of the geoprocessing service
        task_name: Name of the geoprocessing task
        parameters: Input parameters for the task
        token: Optional authentication token

    Returns:
        Dict containing the execution results

    Raises:
        httpx.HTTPError: If the request fails
    """
    execute_url = f"{_ensure_gpserver_url(gp_service_url)}/{task_name}/execute"

    # Add format parameter and token if provided
    execute_params = {**parameters, "f": "json"}
    if token:
        execute_params["token"] = token

    response = await client.post(execute_url, data=execute_params)
    response.raise_for_status()

    return response.json()


async def _check_job_status(
    client: httpx.AsyncClient,
    gp_service_url: str,
    task_name: str,
    job_id: str,
    token: str | None = None,
) -> dict[str, Any]:
    """
    Check the status of a geoprocessing job.

    Args:
        client: HTTP client for making requests
        gp_service_url: Base URL of the geoprocessing service
        task_name: Name of the geoprocessing task
        job_id: Unique identifier for the job
        token: Optional authentication token

    Returns:
        Dict containing job status and details

    Raises:
        httpx.HTTPError: If the request fails
    """
    status_url = f"{_ensure_gpserver_url(gp_service_url)}/{task_name}/jobs/{job_id}"
    params = {"f": "json"}
    if token:
        params["token"] = token
    response = await client.get(status_url, params=params)
    response.raise_for_status()

    return response.json()


async def _get_job_results(
    client: httpx.AsyncClient,
    gp_service_url: str,
    task_name: str,
    job_id: str,
    token: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve the results of a completed geoprocessing job.

    Args:
        client: HTTP client for making requests
        gp_service_url: Base URL of the geoprocessing service
        task_name: Name of the geoprocessing task
        job_id: Unique identifier for the job
        token: Optional authentication token

    Returns:
        Dict containing output parameters and URLs to results

    Raises:
        httpx.HTTPError: If the request fails
    """
    # First get the job details to see what result parameters are available
    job_info = await _check_job_status(client, gp_service_url, task_name, job_id, token)

    results = {}

    # If the job has results, fetch them
    if "results" in job_info:
        for param_name in job_info["results"]:
            result_url = f"{_ensure_gpserver_url(gp_service_url)}/{task_name}/jobs/{job_id}/results/{param_name}"
            results[param_name] = result_url

    return {
        "jobId": job_id,
        "jobStatus": job_info.get("jobStatus"),
        "results": results,
        "messages": job_info.get("messages", []),
    }


# endregion
# ============================================================================

# ============================================================================
# region TOOLS
# ============================================================================


@geoprocessing_router.tool
async def get_gp_task_details(
    service_url: str, task_name: str, token: str | None = None
) -> dict[str, Any]:
    """
    Retrieve full parameter schema for a specific ArcGIS Geoprocessing task.

    Call this tool after selecting a task from the GP catalog resource, before
    calling execute_gp_task. Returns the complete input/output parameter schema
    needed to construct a valid execution request.

    Args:
        service_url: Base URL of the GP service (from GP catalog resource)
        task_name: Name of the task (from GP catalog resource)
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        Dict containing:
            - task_name: Name of the task
            - task_description: Description of what the task does
            - execution_type: esriExecutionTypeSynchronous or esriExecutionTypeAsynchronous
            - input_parameters: List of input parameters, each with:
                - name: Parameter name used in the execution request
                - description: Human-readable description
                - data_type: ArcGIS data type (GPString, GPFeatureRecordSetLayer, GPDouble, etc.)
                - default_value: Default value if not provided
                - required: Whether the parameter must be provided
                - choice_list: Fixed set of allowed values, if constrained
            - output_parameters: List of output parameters, each with:
                - name: Output parameter name
                - description: Human-readable description
                - data_type: ArcGIS data type of the output

    Example:
        details = await get_gp_task_details(
            service_url="https://server/arcgis/rest/services/Analysis",
            task_name="BufferPoints"
        )
    """
    start_time = time.time()

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    logger.info(
        f"from get_gp_task_details: service_url={service_url}, task_name={task_name}, "
        f"token={'<provided>' if resolved_token else None}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=VERIFY_SSL) as client:
            task_details = await _fetch_task_details(client, service_url, task_name, resolved_token)

            if "error" in task_details:
                return {
                    "status": "error",
                    "error": task_details["error"],
                    "elapsed_time": time.time() - start_time,
                }

            return {
                "status": "success",
                "data": task_details,
                "elapsed_time": time.time() - start_time,
            }

    except httpx.HTTPError as e:
        logger.error("HTTP error in get_gp_task_details", exc_info=True)
        return {
            "error": f"HTTP error occurred: {e!s}",
            "error_type": type(e).__name__,
            "elapsed_time": time.time() - start_time,
        }
    except Exception as e:
        logger.error("Unexpected error in get_gp_task_details", exc_info=True)
        return {
            "error": f"Unexpected error occurred: {e!s}",
            "error_type": type(e).__name__,
            "elapsed_time": time.time() - start_time,
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"get_gp_task_details completed in {elapsed_time:.2f} seconds.")


@geoprocessing_router.tool
async def execute_gp_task(
    gp_service_url: str,
    task_name: str,
    parameters: dict[str, Any],
    execution_type: str = "esriExecutionTypeAsynchronous",
    token: str | None = None,
) -> dict[str, Any]:
    """
    Execute an ArcGIS Geoprocessing Server task.

    This tool handles both synchronous and asynchronous GP tasks based on the
    execution_type parameter (available from get_gp_task_details).

    For synchronous tasks (esriExecutionTypeSynchronous):
        Executes the task and returns results directly.

    For asynchronous tasks (esriExecutionTypeAsynchronous):
        Submits the job and returns the job ID. Use check_gp_job_status to
        monitor progress and get_gp_job_results to retrieve output values.

    Args:
        gp_service_url: Base URL of the geoprocessing service
            (e.g., "https://server/arcgis/rest/services/ServiceName")
        task_name: Name of the specific geoprocessing task to execute
        parameters: Dictionary of input parameters for the task.
        execution_type: Execution mode from get_gp_task_details.
            "esriExecutionTypeSynchronous" or "esriExecutionTypeAsynchronous" (default).
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        For synchronous tasks:
            Dict containing:
                - results: Output parameters and their values
                - messages: Any messages from the task
                - elapsed_time: Total time elapsed in seconds

        For asynchronous tasks:
            Dict containing:
                - jobId: Unique identifier for the job (use with check_gp_job_status)
                - jobStatus: Initial status of the job
                - elapsed_time: Total time elapsed in seconds

    Example:
        # Synchronous execution
        result = await execute_gp_task(
             gp_service_url="https://server/arcgis/rest/services/Analysis",
             task_name="BufferPoints",
             parameters={"Input_Features": {"url": "..."}, "Distance": 100},
             execution_type="esriExecutionTypeSynchronous"
         )

        # Asynchronous execution
        result = await execute_gp_task(
             gp_service_url="https://server/arcgis/rest/services/Analysis",
             task_name="BufferPoints",
             parameters={"Input_Features": {"url": "..."}, "Distance": 100},
             execution_type="esriExecutionTypeAsynchronous"
         )
        # Then use check_gp_job_status with result["jobId"]
    """
    start_time = time.time()

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    is_sync = execution_type == "esriExecutionTypeSynchronous"

    logger.info(
        f"from execute_gp_task: gp_service_url={gp_service_url}, task_name={task_name}, "
        f"execution_type={execution_type}, mode={'sync' if is_sync else 'async'}, "
        f"token={'<provided>' if resolved_token else None}"
    )

    try:
        async with httpx.AsyncClient(
            timeout=300.0 if is_sync else 30.0, verify=VERIFY_SSL
        ) as client:
            if is_sync:
                # Synchronous execution: call /execute and return results directly
                exec_response = await _execute_gp_task_sync(
                    client, gp_service_url, task_name, parameters, resolved_token
                )

                # Check for errors in response
                if "error" in exec_response:
                    error_msg = exec_response["error"].get("message", "Unknown error")
                    return {
                        "error": f"Task execution failed: {error_msg}",
                        "details": exec_response["error"],
                        "elapsed_time": time.time() - start_time,
                    }

                return {
                    "results": exec_response.get("results", []),
                    "messages": exec_response.get("messages", []),
                    "elapsed_time": time.time() - start_time,
                }

            else:
                # Asynchronous execution: call /submitJob and return job ID
                submit_response = await _submit_gp_job(
                    client, gp_service_url, task_name, parameters, resolved_token
                )

                job_id = submit_response.get("jobId")
                if not job_id:
                    return {
                        "error": "Failed to submit job - no jobId returned",
                        "response": submit_response,
                        "elapsed_time": time.time() - start_time,
                    }

                return {
                    "jobId": job_id,
                    "jobStatus": submit_response.get("jobStatus", JobStatus.SUBMITTED),
                    "message": "Job submitted successfully. Use check_gp_job_status to monitor progress.",
                    "elapsed_time": time.time() - start_time,
                }

    except httpx.HTTPError as e:
        logger.error("HTTP error in execute_gp_task", exc_info=True)
        return {
            "error": f"HTTP error occurred: {e!s}",
            "error_type": type(e).__name__,
            "elapsed_time": time.time() - start_time,
        }
    except Exception as e:
        logger.error("Unexpected error in execute_gp_task", exc_info=True)
        return {
            "error": f"Unexpected error occurred: {e!s}",
            "error_type": type(e).__name__,
            "elapsed_time": time.time() - start_time,
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"execute_gp_task completed in {elapsed_time:.2f} seconds.")


@geoprocessing_router.tool
async def check_gp_job_status(
    gp_service_url: str, task_name: str, job_id: str, token: str | None = None
) -> dict[str, Any]:
    """
    Check the current status of a geoprocessing job.

    This tool queries the status of a previously submitted geoprocessing job
    without waiting for it to complete.

    Args:
        gp_service_url: Base URL of the geoprocessing service
        task_name: Name of the geoprocessing task
        job_id: Unique identifier for the job
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        Dict containing:
            - jobId: The job identifier
            - jobStatus: Current status of the job
            - messages: Any messages from the task
            - results: Result parameters (if available)

    Example:
         status = await check_gp_job_status(
             gp_service_url="https://server/arcgis/rest/services/Analysis",
             task_name="BufferPoints",
             job_id="j1234567890abcdef"
         )
    """
    start_time = time.time()

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    logger.info(
        f"from check_gp_job_status: gp_service_url={gp_service_url}, task_name={task_name}, job_id={job_id}, token={'<provided>' if resolved_token else None}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=VERIFY_SSL) as client:
            status_response = await _check_job_status(
                client, gp_service_url, task_name, job_id, resolved_token
            )
            return status_response

    except httpx.HTTPError as e:
        logger.error("HTTP error in check_gp_job_status", exc_info=True)
        return {
            "error": f"HTTP error occurred: {e!s}",
            "error_type": type(e).__name__,
        }
    except Exception as e:
        logger.error("Unexpected error in check_gp_job_status", exc_info=True)
        return {
            "error": f"Unexpected error occurred: {e!s}",
            "error_type": type(e).__name__,
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"check_gp_job_status completed in {elapsed_time:.2f} seconds.")


@geoprocessing_router.tool
async def get_gp_job_results(
    gp_service_url: str, task_name: str, job_id: str, token: str | None = None
) -> dict[str, Any]:
    """
    Retrieve the results of a completed geoprocessing job.

    This tool fetches the output parameters and results from a job that
    has already completed successfully.

    Args:
        gp_service_url: Base URL of the geoprocessing service
        task_name: Name of the geoprocessing task
        job_id: Unique identifier for the job
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        Dict containing:
            - jobId: The job identifier
            - jobStatus: Status of the job
            - results: Dictionary of output parameters and values
            - messages: Any messages from the task

    Example:
         results = await get_gp_job_results(
             gp_service_url="https://server/arcgis/rest/services/Analysis",
             task_name="BufferPoints",
             job_id="j1234567890abcdef"
         )
    """
    start_time = time.time()

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    logger.info(
        f"from get_gp_job_results: gp_service_url={gp_service_url}, task_name={task_name}, job_id={job_id}, "
        f"token={'<provided>' if resolved_token else None}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=VERIFY_SSL) as client:
            results = await _get_job_results(
                client, gp_service_url, task_name, job_id, resolved_token
            )
            return results

    except httpx.HTTPError as e:
        logger.error("HTTP error in get_gp_job_results", exc_info=True)
        return {
            "error": f"HTTP error occurred: {e!s}",
            "error_type": type(e).__name__,
        }
    except Exception as e:
        logger.error("Unexpected error in get_gp_job_results", exc_info=True)
        return {
            "error": f"Unexpected error occurred: {e!s}",
            "error_type": type(e).__name__,
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"get_gp_job_results completed in {elapsed_time:.2f} seconds.")


# endregion
# ============================================================================

# ============================================================================
# region TOOLS (continued - GP Catalog)
# ============================================================================


@geoprocessing_router.tool
async def gp_catalog(tags: list[str] | None = None, token: str | None = None) -> dict[str, Any]:
    """
    Discover all ArcGIS Geoprocessing (GP) services and tasks accessible to the
    current user. This tool provides a lightweight overview for the AI to determine
    which GP tasks are available.

    By default, GP services are filtered by tags specified in the GP_CATALOG_DEFAULT_TAGS
    environment variable (comma-separated). If that env var is not set, no tag filtering
    is applied and all GP services are returned.

    The catalog searches the portal for matching items, then crawls each service
    endpoint to extract task names and descriptions.

    Args:
        tags: Optional list of tags to filter GP services. Defaults to GP_CATALOG_DEFAULT_TAGS env var.
              Pass an empty list to explicitly return all GP services without tag filtering.
        token: Optional authentication token. If not provided, uses token from authentication context.

    Returns:
        Dict containing:
            - total_services: Number of GP services found
            - catalog: List of services, each containing:
                - service_name: Name of the GP service
                - service_description: Plain language description of the service
                - service_url: Base URL of the GP service
                - tasks: List of tasks, each with:
                    - task_name: Name of the task
                    - task_description: Description of what the task does
            - elapsed_time: Time taken to fetch the catalog

    Use the get_gp_task_details tool to retrieve full parameter schemas for a
    selected task before executing it.

    Example:
        # Use default tags from GP_CATALOG_DEFAULT_TAGS env var
        catalog = await gp_catalog()

        # Filter by custom tags
        catalog = await gp_catalog(tags=["Analysis", "Production"])

        # Get all GP services (no tag filtering)
        catalog = await gp_catalog(tags=[])
    """
    start_time = time.time()

    # Resolve portal URL
    portal_url = ARCGIS_PORTAL_URL
    if not portal_url:
        return {
            "error": "No portal URL configured. Set ARCGIS_PORTAL_URL environment variable.",
            "catalog": [],
        }

    # Resolve token from parameter or auth context
    resolved_token = resolve_token(token)

    logger.info(
        f"from gp_catalog: portal_url={portal_url}, tags={tags}, "
        f"token={'<provided>' if resolved_token else None}"
    )

    try:
        async with httpx.AsyncClient(timeout=60.0, verify=VERIFY_SSL) as client:
            # Step 1: Search portal for GP service items
            gp_items = await _search_gp_services(client, portal_url, resolved_token, tags=tags)

            if not gp_items:
                return {
                    "total_services": 0,
                    "catalog": [],
                    "message": "No Geoprocessing Services found for the current user.",
                    "elapsed_time": time.time() - start_time,
                }

            # Step 2: Crawl each GP service to extract task info
            catalog = []
            for item in gp_items:
                service_url = item.get("url", "")
                if not service_url:
                    logger.warning(f"GP service item '{item.get('title')}' has no URL, skipping.")
                    continue

                try:
                    service_info = await _crawl_gp_service(client, service_url, resolved_token)
                    if "error" not in service_info:
                        # Use item metadata to supplement service description if empty
                        if not service_info.get("service_description"):
                            service_info["service_description"] = (
                                item.get("snippet") or item.get("description") or ""
                            )
                        catalog.append(service_info)
                    else:
                        logger.warning(
                            f"Could not crawl GP service '{item.get('title')}': {service_info['error']}"
                        )
                except Exception as e:
                    logger.warning(f"Error crawling GP service '{item.get('title')}': {e}")

            return {
                "total_services": len(catalog),
                "catalog": catalog,
                "elapsed_time": time.time() - start_time,
            }

    except httpx.HTTPError as e:
        logger.error("HTTP error in gp_catalog", exc_info=True)
        return {
            "error": f"HTTP error occurred: {e!s}",
            "error_type": type(e).__name__,
            "catalog": [],
        }
    except Exception as e:
        logger.error("Unexpected error in gp_catalog", exc_info=True)
        return {
            "error": f"Unexpected error occurred: {e!s}",
            "error_type": type(e).__name__,
            "catalog": [],
        }
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"gp_catalog completed in {elapsed_time:.2f} seconds.")


# endregion
# ============================================================================

# ============================================================================
# region RESOURCES
# ============================================================================


@geoprocessing_router.resource(uri="resource://analysis/gp-job-statuses")
def gp_job_statuses() -> ResourceResult:
    """
    Provide information about GPServer job status values.

    Returns:
        Dict containing all possible job status values and their meanings
    """

    result = {
        "job_statuses": {
            JobStatus.SUBMITTED: "Job has been submitted to the server",
            JobStatus.WAITING: "Job is waiting for available resources",
            JobStatus.EXECUTING: "Job is currently being executed",
            JobStatus.SUCCEEDED: "Job completed successfully",
            JobStatus.FAILED: "Job failed during execution",
            JobStatus.TIMED_OUT: "Job exceeded the maximum execution time",
            JobStatus.CANCELLING: "Job is being cancelled",
            JobStatus.CANCELLED: "Job was cancelled",
        },
        "terminal_states": [
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.TIMED_OUT,
            JobStatus.CANCELLED,
        ],
    }
    return ResourceResult(
        contents=[ResourceContent(content=json.dumps(result), mime_type="application/json")]
    )


# endregion
# ============================================================================

# ============================================================================
# region PROMPTS
# ============================================================================


@geoprocessing_router.prompt
def gp_task_execution_prompt() -> str:
    """
    Generate a prompt for guiding the AI through GP task execution workflow.

    Returns:
        str: The generated prompt describing the GP workflow
    """
    return """
You have access to a gp_catalog tool that lists all geoprocessing services
and tasks available to the current user. GP services are filtered by tags 
specified in the GP_CATALOG_DEFAULT_TAGS environment variable. Use the tags 
parameter to filter by different tags. Call gp_catalog when the user's question 
involves spatial analysis or geoprocessing.

WORKFLOW:
1) Call gp_catalog to find the best matching task based on task descriptions.
2) Call get_gp_task_details to retrieve the full parameter schema for the
   selected task (service_url and task_name from the catalog).
3) Call execute_gp_task to submit the job. Pass the execution_type from
   get_gp_task_details so the tool knows how to execute:
   - For synchronous tasks: results are returned directly in the response.
   - For asynchronous tasks: a job ID is returned.
4) For asynchronous jobs only:
   - Call check_gp_job_status to monitor progress using the returned job ID.
   - Call get_gp_job_results to retrieve output values once the job succeeds.

Do NOT guess task names or parameter names — always use values from the
gp_catalog tool and get_gp_task_details.

Once the task completes, give the user basic information about the results
including any URLs to the results, output datasets or services.
Do not display the full results unless the user asks for them directly.
"""


# endregion
# ============================================================================
