"""LLM Customization Script Generation.

This module provides LLM-powered generation of JavaScript customization snippets
for the Dynamic Application Router's Map Viewer App. Unlike the ArcGIS router's
full HTML generation, this module generates JavaScript function body snippets that
are executed by the static viewer after the base map is initialized.

Configuration is done via environment variables:
- OPENAI_KEY: The API key for OpenAI or compatible service
- OPENAI_BASE_URL: The base URL for the API (defaults to OpenAI's API)
- OPENAI_MODEL: The model to use (defaults to gpt-4o)
- USE_ARCGIS_LLM: Set to "true" to enable LLM-based script generation

For Azure OpenAI, set these additional variables:
- AZURE_OPENAI: Set to "true" to use Azure OpenAI client
- AZURE_OPENAI_API_VERSION: The API version (defaults to "2024-02-15-preview")
- AZURE_OPENAI_DEPLOYMENT: The deployment name (if different from OPENAI_MODEL)
"""

from __future__ import annotations

import logging
import os

from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

logger = logging.getLogger(__name__)

# LLM Configuration from environment variables
USE_ARCGIS_LLM = os.getenv("USE_ARCGIS_LLM", "false").lower() == "true"
OPENAI_KEY = os.getenv("OPENAI_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Azure OpenAI specific configuration
USE_AZURE_OPENAI = os.getenv("AZURE_OPENAI", "false").lower() == "true"
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", OPENAI_MODEL)

# LLM call timeout in seconds
LLM_TIMEOUT_SECONDS = 60

# ArcGIS Maps SDK version used in documentation references
ARCGIS_SDK_VERSION = "4.34"

# System prompt for generating JavaScript customization snippets
CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT = """You are an expert ArcGIS developer. Your task is to generate \
a JavaScript function body snippet that customizes an ArcGIS map after it has been initialized.

IMPORTANT CONTEXT:
- The map is rendered using ArcGIS Maps SDK for JavaScript (v4.34).
- Your code will be executed as an async function body AFTER the map view is ready.
- You receive `mapView` (the MapView instance) and `mapElement` (the <arcgis-map> element) as parameters.
- You can use `$arcgis.import()` to import ArcGIS modules.
- Do NOT generate a full HTML page — only the JavaScript function body.
- Do NOT use document.querySelector("arcgis-map") — use the `mapElement` parameter instead.
- Access the map through `mapView` or `mapElement.map`.

CRITICAL — WEB COMPONENTS ONLY (NO DEPRECATED WIDGETS):
- As of v4.34, all classic widgets (BasemapGallery, Legend, Search, Expand, LayerList, etc.) \
are DEPRECATED.
- NEVER import or instantiate deprecated widget classes such as:
  esri/widgets/BasemapGallery, esri/widgets/Legend, esri/widgets/Search,
  esri/widgets/Expand, esri/widgets/LayerList, esri/widgets/ScaleBar,
  esri/widgets/Compass, esri/widgets/Home, esri/widgets/Zoom,
  @arcgis/core/widgets/*
- Instead, use the equivalent ArcGIS Maps SDK Web Components (custom HTML elements).
- Web components are self-registering — just create the element and set properties.

WEB COMPONENT PATTERN:
```javascript
// Web components are added as slotted children of the arcgis-map element.
// Use the slot attribute to position them in the map UI.

// Basemap Gallery in an Expand (collapsible)
const expand1 = document.createElement("arcgis-expand");
expand1.setAttribute("slot", "top-right");
expand1.mode = "floating";
const basemapGallery = document.createElement("arcgis-basemap-gallery");
expand1.appendChild(basemapGallery);
mapElement.appendChild(expand1);

// Legend in an Expand (collapsible)
const expand2 = document.createElement("arcgis-expand");
expand2.setAttribute("slot", "bottom-left");
expand2.mode = "floating";
const legend = document.createElement("arcgis-legend");
expand2.appendChild(legend);
mapElement.appendChild(expand2);

// Search (direct, no expand)
const search = document.createElement("arcgis-search");
search.setAttribute("slot", "top-left");
mapElement.appendChild(search);

// Layer List in an Expand
const expand3 = document.createElement("arcgis-expand");
expand3.setAttribute("slot", "top-right");
expand3.mode = "floating";
const layerList = document.createElement("arcgis-layer-list");
expand3.appendChild(layerList);
mapElement.appendChild(expand3);

// Zoom (direct)
const zoom = document.createElement("arcgis-zoom");
zoom.setAttribute("slot", "top-left");
mapElement.appendChild(zoom);
```

IMPORTANT: Web components get their view reference automatically from the parent
arcgis-map element. Do NOT set .view manually — just append them as children with
the correct slot attribute.

AVAILABLE VARIABLES:
- `mapView` — the MapView instance (passed as parameter)
- `mapView.map` — the Map instance
- `mapView.graphics` — the view's graphics collection
- `mapView.ui` — the UI manager for adding custom HTML elements (buttons, divs)
- `mapElement` — the <arcgis-map> DOM element (passed as parameter)
  Use mapElement.appendChild() to add web components as slotted children.

MODULE IMPORT PATTERN:
Use `$arcgis.import()` for importing ArcGIS modules (layers, renderers, geometry, etc.):
```javascript
const FeatureLayer = await $arcgis.import("@arcgis/core/layers/FeatureLayer.js");
const Layer = await $arcgis.import("@arcgis/core/layers/Layer.js");
const Graphic = await $arcgis.import("@arcgis/core/Graphic.js");
const SimpleRenderer = await $arcgis.import("@arcgis/core/renderers/SimpleRenderer.js");
const SimpleFillSymbol = await $arcgis.import("@arcgis/core/symbols/SimpleFillSymbol.js");
const SimpleLineSymbol = await $arcgis.import("@arcgis/core/symbols/SimpleLineSymbol.js");
const SimpleMarkerSymbol = await $arcgis.import("@arcgis/core/symbols/SimpleMarkerSymbol.js");
const rasterFunctionUtils = await $arcgis.import(\
"@arcgis/core/layers/support/rasterFunctionUtils.js");
const ImageryTileLayer = await $arcgis.import("@arcgis/core/layers/ImageryTileLayer.js");
```

ACCESSING THE MAP AND VIEW:
```javascript
// mapView is passed as a parameter — it's the MapView instance
const map = mapView.map;
// mapView.map is the Map instance
// mapView.graphics is the view's graphics collection
// mapView.ui is the UI manager
```

ADDING LAYERS EXAMPLE:
```javascript
const FeatureLayer = await $arcgis.import("@arcgis/core/layers/FeatureLayer.js");

const layer = new FeatureLayer({{
    url: "https://services.arcgis.com/.../FeatureServer/0",
    definitionExpression: "STATE = 'California'"
}});
mapView.map.add(layer);
```

CHANGING VIEW PROPERTIES:
```javascript
// Go to a specific location
mapView.goTo({{
    center: [-118.24, 34.05],
    zoom: 12
}});
```

ADDING GRAPHICS:
```javascript
const Graphic = await $arcgis.import("@arcgis/core/Graphic.js");

const point = {{
    type: "point",
    longitude: -118.24,
    latitude: 34.05
}};
const symbol = {{
    type: "simple-marker",
    color: [226, 119, 40],
    size: 12
}};
const graphic = new Graphic({{
    geometry: point,
    symbol: symbol
}});
mapView.graphics.add(graphic);
```

APPLYING RENDERERS:
```javascript
const layer = mapView.map.layers.getItemAt(0);
layer.renderer = {{
    type: "simple",
    symbol: {{
        type: "simple-fill",
        color: [51, 51, 204, 0.5],
        outline: {{ color: [0, 0, 0], width: 1 }}
    }}
}};
```

ADDING UI ELEMENTS (BUTTONS):
```javascript
// Add a custom button to the map UI
const btn = document.createElement("button");
btn.textContent = "My Button";
btn.style.padding = "8px 12px";
btn.style.cursor = "pointer";
btn.addEventListener("click", () => {{
    // Do something when clicked
    const layer = mapView.map.layers.getItemAt(0);
    layer.renderer = {{ type: "simple", symbol: {{ type: "simple-line", color: "pink", width: 3 }} }};
}});
mapView.ui.add(btn, "top-right");
```

IMAGE SERVICE LAYERS WITH RASTER FUNCTIONS:
```javascript
const rasterFunctionUtils = await $arcgis.import(\
"@arcgis/core/layers/support/rasterFunctionUtils.js");
const ImageryTileLayer = await $arcgis.import("@arcgis/core/layers/ImageryTileLayer.js");

const ndvi = rasterFunctionUtils.bandArithmeticNDVI({{
    nirBandId: 3,
    redBandId: 2,
    scientificOutput: false
}});
const colormap = rasterFunctionUtils.colormap({{
    colorRampName: "NDVI3",
    raster: ndvi
}});
const layer = new ImageryTileLayer({{
    url: "https://example.com/arcgis/rest/services/Imagery/ImageServer",
    rasterFunction: colormap
}});
mapView.map.add(layer);
```

RULES:
1. Generate ONLY the JavaScript function body — no HTML, no script tags, no markdown.
2. Use `$arcgis.import()` for all ArcGIS module imports (layers, renderers, geometry, symbols).
3. Use `mapView` (the parameter) to access the view and `mapView.map` for the map.
4. Use `mapElement` (the parameter) to add web components as slotted children.
5. The code will be wrapped in an async function and executed — you can use `await`.
6. Do NOT include function declarations or IIFE wrappers — just the body code.
7. Return ONLY the JavaScript code, no explanations or markdown code blocks.
8. Keep the code concise and focused on the requested customization.
9. For UI components (basemap gallery, legend, layer list, etc.), use ArcGIS web components \
appended to `mapElement` with slot attributes — NEVER use deprecated widget classes.
10. For custom HTML elements (buttons, divs), use `mapView.ui.add(element, position)`.
"""


def _get_openai_client() -> AsyncOpenAI | AsyncAzureOpenAI:
    """Create and return an OpenAI or Azure OpenAI async client.

    Returns:
        Configured async client instance.

    Raises:
        ValueError: If OPENAI_KEY is not set.
    """
    if not OPENAI_KEY:
        raise ValueError(
            "OPENAI_KEY environment variable is required for LLM-based script generation"
        )

    if USE_AZURE_OPENAI:
        logger.debug(
            "Using Azure OpenAI client - Endpoint: %s, API Version: %s, Deployment: %s",
            OPENAI_BASE_URL,
            AZURE_OPENAI_API_VERSION,
            AZURE_OPENAI_DEPLOYMENT,
        )
        return AsyncAzureOpenAI(
            api_key=OPENAI_KEY,
            azure_endpoint=OPENAI_BASE_URL,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    else:
        logger.debug(
            "Using standard OpenAI client - Base URL: %s, Model: %s",
            OPENAI_BASE_URL,
            OPENAI_MODEL,
        )
        return AsyncOpenAI(api_key=OPENAI_KEY, base_url=OPENAI_BASE_URL)


def _clean_llm_response(response: str) -> str:
    """Strip markdown code block delimiters from the LLM response.

    Removes ```html, ```javascript, ```js, or bare ``` delimiters that LLMs
    commonly wrap code responses in.

    Args:
        response: The raw response string from the LLM.

    Returns:
        Cleaned response with markdown delimiters removed and whitespace trimmed.
    """
    cleaned = response

    # Strip leading code block markers
    for prefix in ("```javascript", "```js", "```html", "```"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break

    # Strip trailing code block marker
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()


def _build_user_prompt(map_type: str, map_params: dict, additional_requirements: str) -> str:
    """Build the user prompt for the LLM based on map context.

    Args:
        map_type: The type of map being rendered (sample_map, webmap, layers_map).
        map_params: Dictionary of map parameters for context.
        additional_requirements: Natural language customization requirements.

    Returns:
        Formatted user prompt string.
    """
    context_parts = [
        f"Map type: {map_type}",
    ]

    if map_type == "webmap":
        if webmap_id := map_params.get("webmap_id"):
            context_parts.append(f"Web Map ID: {webmap_id}")
        if portal_url := map_params.get("portal_url"):
            context_parts.append(f"Portal URL: {portal_url}")
    elif map_type == "layers_map":
        if layer_urls := map_params.get("layer_urls"):
            layers_str = "\n".join(f"  - {url}" for url in layer_urls)
            context_parts.append(f"Layer URLs:\n{layers_str}")
        if where_clauses := map_params.get("layer_where_clauses"):
            clauses_str = "\n".join(f"  - {clause}" for clause in where_clauses)
            context_parts.append(f"Where Clauses:\n{clauses_str}")
    elif map_type == "sample_map":
        context_parts.append("Basemap: topo-vector, centered on USA")

    context = "\n".join(context_parts)

    return f"""Generate a JavaScript function body to customize the following map:

{context}

User Requirements:
{additional_requirements}

Generate ONLY the JavaScript code (function body). No markdown, no explanations."""


async def generate_customization_script(
    map_type: str, map_params: dict, additional_requirements: str
) -> str | None:
    """Generate a JavaScript customization script using the LLM backend.

    Calls the configured OpenAI-compatible API to generate a JavaScript function body
    snippet that customizes the map based on the provided requirements. The snippet
    is executed by the Map Viewer App after the base map is initialized.

    Args:
        map_type: The type of map being rendered (sample_map, webmap, layers_map).
        map_params: Dictionary of map parameters providing context to the LLM.
        additional_requirements: Natural language description of desired customizations.

    Returns:
        JavaScript function body string on success, or None if generation fails.
        Returns None gracefully on any error (network, timeout, missing key, etc.).
    """
    try:
        client = _get_openai_client()
    except ValueError:
        logger.warning("LLM script generation skipped: OPENAI_KEY not configured")
        return None

    user_prompt = _build_user_prompt(map_type, map_params, additional_requirements)

    messages: list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = [
        {"role": "system", "content": CUSTOMIZATION_SCRIPT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    model_or_deployment = AZURE_OPENAI_DEPLOYMENT if USE_AZURE_OPENAI else OPENAI_MODEL

    try:
        logger.info(
            "Generating customization script for map_type=%s with model=%s",
            map_type,
            model_or_deployment,
        )
        response = await client.chat.completions.create(
            model=model_or_deployment,
            messages=messages,
            temperature=0.2,
            timeout=LLM_TIMEOUT_SECONDS,
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("LLM returned empty response for customization script")
            return None

        script = _clean_llm_response(content)
        logger.debug("Generated customization script (%d chars)", len(script))
        return script

    except Exception as e:
        logger.warning(
            "LLM customization script generation failed for map_type=%s: %s", map_type, e
        )
        return None
