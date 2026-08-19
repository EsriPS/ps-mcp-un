---
name: hot-spot-analysis
description: Perform spatial hot spot analysis using ArcGIS FindHotSpots to identify statistically significant clusters of high and low values within a geographic area. Use this skill when the user wants to find clusters or concentrations of features, identify hot spots or cold spots in spatial data, or analyze spatial patterns around a specific location.
---

# Hot Spot Analysis Skill

## Overview

Perform spatial hot spot analysis using ArcGIS SpatialAnalysisTools/FindHotSpots to identify statistically significant clusters of high values (hot spots) and low values (cold spots) within a geographic area.

## When to Use This Skill

Use this skill when the user wants to:
- Find clusters or concentrations of features (e.g., crime incidents, disease cases, species observations)
- Identify statistically significant hot spots or cold spots in spatial data
- Analyze spatial patterns around a specific location
- Run a FindHotSpots geoprocessing task

**Trigger phrases:**
- "Run a hot spot analysis..."
- "Find hot spots for..."
- "Where are the clusters of..."
- "Analyze spatial patterns of..."
- "Find concentrations of..."

## Required Inputs

| Input | Description | Example |
|-------|-------------|---------|
| `location` | Center point for the analysis area | "Washington, DC", "Carson City, NV" |
| `analysis_layer_search` | Search term to find the analysis layer in portal | "Smithsonian plants", "crime incidents" |

## Optional Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `search_radius_miles` | 100 | Bounding rectangle size around the location |
| `cell_size_miles` | 5 | Hexagon cell size for aggregation |
| `output_service_name` | Auto-generated | Name for the output hosted layer |

## Workflow

### Step 1: Search for Analysis Layer
```
Tool: psmcp__search_portal
Input: query based on analysis_layer_search parameter
```
- Present matching layers if multiple results
- Extract the feature layer URL from the selected item

### Step 2: Find the FindHotSpots GP Service
```
Tool: psmcp__list_system_services
Fallback: psmcp__search_portal (type: "Geoprocessing Service")
Then: psmcp__get_gp_task_details (task_name: "FindHotSpots")
```
- First check system services for SpatialAnalysisTools
- Fall back to portal search if not found
- Confirm GP task schema before execution

### Step 3: Geocode the Location
```
Tool: psmcp__find_address_candidates
Input: location parameter
```
- Extract x, y coordinates from the response

### Step 4: Build Bounding Polygon
Create a rectangular bounding polygon:
- Convert search_radius_miles to meters (1 mile ≈ 1609.34 meters)
- Calculate xmin, xmax, ymin, ymax from center point
- Format as esriGeometryPolygon featureSet

### Step 5: Execute FindHotSpots
```
Tool: psmcp__execute_gp_task
Inputs:
  - gp_service_url: <discovered service URL>
  - task_name: "FindHotSpots"
  - execution_type: "esriExecutionTypeAsynchronous"
```

**Parameters format:**
```json
{
  "analysisLayer": {
    "url": "<discovered_layer_url>"
  },
  "boundingPolygonLayer": {
    "featureSet": {
      "geometryType": "esriGeometryPolygon",
      "spatialReference": {
        "wkid": 102100
      },
      "features": [
        {
          "attributes": {
            "objectid": 1
          },
          "geometry": {
            "rings": [
              [
                [<xmin>, <ymin>],
                [<xmax>, <ymin>],
                [<xmax>, <ymax>],
                [<xmin>, <ymax>],
                [<xmin>, <ymin>]
              ]
            ]
          }
        }
      ]
    },
    "layerDefinition": {
      "name": "<location>_bounding_rect",
      "geometryType": "esriGeometryPolygon",
      "fields": [
        {
          "name": "objectid",
          "type": "esriFieldTypeOID",
          "alias": "objectid"
        }
      ]
    }
  },
  "shapeType": "Hexagon",
  "cellSize": <cell_size_miles>,
  "cellSizeUnits": "Miles",
  "outputName": "{\"serviceProperties\":{\"name\":\"<output_service_name>\"},\"itemProperties\":{\"title\":\"<output_title>\"}}"
}
```

### Step 6: Poll Job Status
```
Tool: psmcp__check_gp_job_status
Input: job URL from execute response
```
- Poll until job completes (success or failure)
- On success, use `psmcp__get_gp_job_results` to retrieve outputs

### Step 7: Display Results
```
Tool: psmcp__open_layers_map
```
- Center map on the geocoded location
- Add the analysis layer and result hot spots layer
- Set result layer transparency to 50%
- Filter result layer to show only `gi_bin > 0` (statistically significant hot spots)
- Enable popups on both layers

## Expected Output

| Field | Description |
|-------|-------------|
| `analysis_layer_url` | URL of the input analysis layer |
| `job_id` | GP job identifier |
| `status` | Job completion status |
| `hotspots_layer_url` | URL of the output hot spots layer |
| `hotspots_item_id` | Portal item ID of the output layer |
| `messages` | Any warnings or messages from the job |

## Important Notes

- **GPMultiValue parameters**: Pass as arrays (e.g., `["value1", "value2"]`)
- **Bounding polygon**: Prefer rectangle method over CreateBuffers
- **Output naming**: If not provided, auto-generate based on analysis layer name and location (e.g., "plants_hotspots_dc_hex5mi")
- **Spatial reference**: Use wkid 102100 for the bounding polygon

## Example Usage

**User request:**
> "Run a hot spot analysis for Smithsonian plants around Carson City, NV"

**Parsed inputs:**
- `location`: "Carson City, NV"
- `analysis_layer_search`: "Smithsonian plants"
- `search_radius_miles`: 100 (default)
- `cell_size_miles`: 5 (default)

**Generated output name:**
- Service name: `plants_hotspots_carson_city_nv_hex5mi`
- Title: `Plants hotspots (Carson City NV) hex 5mi`


