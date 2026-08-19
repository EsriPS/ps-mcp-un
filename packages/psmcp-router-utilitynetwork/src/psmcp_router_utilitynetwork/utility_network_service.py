"""ArcGIS Utility Network router plugin for PS-MCP.

This module provides async utility network trace tools and follows the same
FastMCP router pattern used by other PS-MCP routers.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from psmcp.core.auth import resolve_token
from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier
# from arcgis.gis import GIS
# import arcpy


logger = logging.getLogger(__name__)

utilitynetwork_router = FastMCP(name="Utility Network Service")

UN_ITEM_ID = "<unitemid>"





@utilitynetwork_router.tool(
    name="network_downstream_trace",
    description="Perform an asynchronous downstream trace on an ArcGIS Utility Network.",
)
async def network_downstream_trace(
    network_service_url: str,
    starting_feature_id: int,
    token: str | None = None,
) -> dict[str, Any]:
    """Trace flow downstream from a starting utility network feature."""

    token = resolve_token(token)
    logger.info(
        "Starting downstream trace on %s from feature %s",
        network_service_url,
        starting_feature_id,
    )

    """
    Executes a downstream utility network trace.
    
    Parameters:
    - utility_network (str): Path to the Utility Network layer or feature dataset.
    - starting_points (str): Path to the feature class containing trace flags/starting points.
    - domain_network (str): The name of the specific domain network (e.g., 'Water', 'Electric').
    - tier_name (str): The tier name within the domain network (e.g., 'Distribution').
    - out_layer_name (str): Name of the output group layer containing the selection results.
    """
    # try:
        # Overwrite existing layers with the same name if they exist
        # arcpy.env.overwriteOutput = True
        
        # print(f"Starting downstream trace on: {utility_network}...")

        # un_url = "https://psutilities.esri.com/server/rest/services/GasUN/GasUtilityNetwork/FeatureServer"
        # domain_network = "Pipeline"
        # tier_name = "system"
        # starting_points = "test"

        

        # # Execute the Utility Network Trace tool
        # # Source: https://pro.arcgis.com/en/pro-app/latest/tool-reference/utility-networks/trace.htm
        # result = arcpy.un.Trace(
        #     in_utility_network=un_url,
        #     trace_type="DOWNSTREAM",                    # Sets the trace direction
        #     starting_points=starting_points,             # Features defining where trace begins
        #     barriers=None,                               # Optional: Feature class for trace barriers
        #     domain_network=domain_network,               # Limits trace to specified domain
        #     tier=tier_name,                              # Subnetwork tier to target
        #     target_tier=None,
        #     subnetwork_name=None,
        #     shortest_path_network_attribute_name=None,
        #     include_containers="EXCLUDE_CONTAINERS",
        #     include_content="EXCLUDE_CONTENT",
        #     include_structures="EXCLUDE_STRUCTURES",
        #     validate_consistency="DO_NOT_VALIDATE_CONSISTENCY", # Skip dirty area check if editing
        #     condition_barriers=None,
        #     function_barriers=None,
        #     traversability_scope="BOTH_JUNCTIONS_AND_EDGES", # Trace lines and point devices
        #     filter_barriers=None,
        #     filter_function_barriers=None,
        #     filter_scope=None,
        #     filter_bitset_network_attribute_name=None,
        #     filter_nearest=None,
        #     nearest_count=None,
        #     nearest_cost_network_attribute_name=None,
        #     nearest_categories=None,
        #     nearest_assets=None,
        #     out_network_layer=out_layer_name,           # Output group layer name
        #     result_types="SELECTION"                     # Options: SELECTION, ELEMENTS, AGGREGATED_GEOMETRY
        # )

        # print(f"Trace completed successfully! Group selection layer created: {out_layer_name}")
        # return result
    #     return "Trace Successful"

    # except arcpy.ExecuteError:
    #     print(arcpy.GetMessages(2))
    # except Exception as e:
    #     print(f"An unexpected error occurred: {str(e)}")


    return {
        "traceType": "downstream",
        "networkServiceUrl": network_service_url,
        "startingFeatureId": starting_feature_id,
        "tokenProvided": token is not None,
        "traceResults": [],
    }


@utilitynetwork_router.tool(
    name="network_upstream_trace",
    description="Perform an asynchronous upstream trace on an ArcGIS Utility Network.",
)
async def network_upstream_trace(
    network_service_url: str,
    starting_feature_id: int,
    token: str | None = None,
) -> dict[str, Any]:
    """Trace flow upstream from a starting utility network feature."""

    token = resolve_token(token)
    logger.info(
        "Starting upstream trace on %s from feature %s",
        network_service_url,
        starting_feature_id,
    )

    return {
        "traceType": "upstream",
        "networkServiceUrl": network_service_url,
        "startingFeatureId": starting_feature_id,
        "tokenProvided": token is not None,
        "traceResults": [],
    }
