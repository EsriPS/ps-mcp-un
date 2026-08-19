"""Map Viewer App HTML generation.

This module provides the static, self-contained HTML document that serves as the
Map Viewer App resource. The HTML includes inline JavaScript that uses the MCP Apps
SDK to receive tool result data and dynamically render ArcGIS maps. It also registers
app-side tools for incremental map updates and pushes state back to the model via
updateModelContext().
"""


def get_viewer_html() -> str:
    """Return the complete self-contained HTML document for the Map Viewer App.

    The returned HTML includes:
    - MCP Apps SDK import from CDN for host communication
    - ArcGIS Maps SDK for JavaScript v4.34 with Map Components from CDN
    - Calcite Design System v3.3.3 from CDN
    - Web components (arcgis-basemap-gallery, arcgis-legend, etc.) via map-components
    - $arcgis.import() API for LLM-generated customization scripts
    - Tool result handling (ontoolinput/ontoolresult) with type dispatch
    - App-side tool registration (add_layer, remove_layer, change_basemap,
      update_symbology, get_current_view)
    - Token registration with IdentityManager for secured services
    - Customization script execution after map initialization
    - Model context updates after each state change
    - Error display for malformed/unrecognized tool result data

    Returns:
        A static, deterministic HTML string that is identical on every call.
    """
    return _VIEWER_HTML


_VIEWER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light dark" />
    <title>ArcGIS Map Viewer</title>
    <!-- Load the JavaScript Maps SDK CSS -->
    <link rel="stylesheet" href="https://js.arcgis.com/4.34/esri/themes/light/main.css" />
    <!-- Load Calcite Design System -->
    <script type="module"
            src="https://js.arcgis.com/calcite-components/3.3.3/calcite.esm.js"></script>
    <!-- Load the JavaScript Maps SDK core API -->
    <script src="https://js.arcgis.com/4.34/"></script>
    <!-- Load the JavaScript Maps SDK Map components (registers arcgis-* elements) -->
    <script type="module" src="https://js.arcgis.com/4.34/map-components/"></script>
    <style>
        html, body {
            padding: 0;
            margin: 0;
            height: 600px;
            width: 100%;
            overflow: hidden;
        }
        #viewDiv {
            padding: 0;
            margin: 0;
            height: 600px;
            width: 100%;
        }
        arcgis-map {
            display: block;
            height: 600px;
            width: 100%;
        }
        #errorDiv {
            display: none;
            padding: 20px;
            margin: 20px;
            background: #fee;
            border: 1px solid #c00;
            border-radius: 4px;
            color: #900;
            font-family: system-ui, sans-serif;
        }
    </style>
</head>
<body>
    <div id="viewDiv"></div>
    <div id="errorDiv"></div>
    <script type="module">
import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@latest/dist/src/app-with-deps.js";

// --- State ---
let mapView = null;
let mapElement = null;
let currentData = null;

// --- Error display ---
function showError(message) {
    const errorDiv = document.getElementById("errorDiv");
    const viewDiv = document.getElementById("viewDiv");
    errorDiv.textContent = message;
    errorDiv.style.display = "block";
    viewDiv.style.display = "none";
}

// --- Model context update ---
async function updateModelContext(app) {
    if (!mapView || !app) return;
    try {
        const extent = mapView.extent;
        const center = mapView.center;
        const zoom = mapView.zoom;
        const basemap = mapView.map.basemap?.title || mapView.map.basemap?.id || "unknown";
        const layers = [];
        if (mapView.map.layers) {
            mapView.map.layers.forEach(function(layer) {
                layers.push({
                    title: layer.title || layer.url || "Untitled",
                    url: layer.url || null,
                    visible: layer.visible,
                    type: layer.type || "unknown"
                });
            });
        }
        const contextText = [
            "Current map state:",
            "Basemap: " + basemap,
            "Center: " + (center ? center.longitude.toFixed(4) + ", " + center.latitude.toFixed(4) : "unknown"),
            "Zoom: " + (zoom != null ? zoom : "unknown"),
            "Layers (" + layers.length + "):"
        ];
        for (const l of layers) {
            contextText.push("  - " + l.title + (l.url ? " (" + l.url + ")" : "") + " [visible=" + l.visible + "]");
        }
        await app.updateModelContext({
            content: [{ type: "text", text: contextText.join("\\n") }]
        });
    } catch (e) {
        // Goose host may return non-standard response keys that fail SDK validation.
        // This is non-fatal — the map still renders correctly.
        console.warn("[MapViewer] updateModelContext failed (non-fatal):", e.message || e);
    }
}

// --- Map initialization ---
async function initializeMap(data, app) {
    const type = data.type;

    if (!type) {
        showError("Error: Tool result data is missing the required 'type' field.");
        return;
    }

    // Request a fixed height from the host so the map is visible
    try {
        window.parent.postMessage({
            jsonrpc: "2.0",
            method: "ui/notifications/size-changed",
            params: { height: 600 }
        }, "*");
    } catch (e) {
        // Non-fatal if postMessage is blocked
    }

    if (type === "sample_map") {
        await initSampleMap(data, app);
    } else if (type === "webmap") {
        if (!data.webmap_id) {
            showError("Error: 'webmap' type requires a 'webmap_id' field.");
            return;
        }
        if (!data.portal_url) {
            showError("Error: 'webmap' type requires a 'portal_url' field.");
            return;
        }
        await initWebMap(data, app);
    } else if (type === "layers_map") {
        if (!data.layer_urls || !data.layer_urls.length) {
            showError("Error: 'layers_map' type requires a non-empty 'layer_urls' field.");
            return;
        }
        await initLayersMap(data, app);
    } else {
        showError("Error: Unrecognized map type '" + type + "'. Supported types: sample_map, webmap, layers_map.");
        return;
    }
}

// --- Helper: create arcgis-map element and wait for view ready ---
async function createMapElement(attrs) {
    const viewDiv = document.getElementById("viewDiv");
    viewDiv.innerHTML = "";

    mapElement = document.createElement("arcgis-map");
    for (const [key, value] of Object.entries(attrs)) {
        mapElement.setAttribute(key, value);
    }
    viewDiv.appendChild(mapElement);

    // Wait for the view to be ready
    await new Promise((resolve, reject) => {
        mapElement.addEventListener("arcgisViewReadyChange", () => {
            mapView = mapElement.view;
            resolve();
        }, { once: true });
        // Timeout fallback
        setTimeout(() => reject(new Error("Map view ready timeout")), 30000);
    });
    return mapElement;
}

async function initSampleMap(data, app) {
    try {
        await createMapElement({
            basemap: "topo-vector",
            center: "-98,39",
            zoom: "4"
        });
        executeCustomizationScript(data);
        updateModelContext(app);
    } catch (error) {
        showError("Error initializing sample map: " + error.message);
    }
}

async function initWebMap(data, app) {
    console.log("[MapViewer] initWebMap starting...");
    try {
        const esriConfig = await $arcgis.import("@arcgis/core/config.js");
        const esriId = await $arcgis.import("@arcgis/core/identity/IdentityManager.js");

        esriConfig.portalUrl = data.portal_url;

        // Register tokens before creating the map
        if (data.token && data.token_servers && data.token_servers.length) {
            for (const server of data.token_servers) {
                if (!server) continue;
                esriId.registerToken({
                    server: server + "/sharing/rest",
                    token: data.token
                });
            }
        } else {
            esriConfig.request.useIdentity = false;
        }

        await createMapElement({ "item-id": data.webmap_id });
        console.log("[MapViewer] WebMap loaded successfully");
        executeCustomizationScript(data);
        updateModelContext(app);
    } catch (error) {
        console.error("[MapViewer] WebMap load failed:", error.message);
        showError("Error loading web map '" + data.webmap_id + "': " + error.message);
    }
}

async function initLayersMap(data, app) {
    try {
        const esriId = await $arcgis.import("@arcgis/core/identity/IdentityManager.js");
        const esriConfig = await $arcgis.import("@arcgis/core/config.js");
        const Layer = await $arcgis.import("@arcgis/core/layers/Layer.js");
        const FeatureLayer = await $arcgis.import("@arcgis/core/layers/FeatureLayer.js");

        // Register tokens before loading secured layers
        if (data.token && data.token_servers && data.token_servers.length) {
            for (const server of data.token_servers) {
                if (!server) continue;
                esriId.registerToken({
                    server: server,
                    token: data.token
                });
            }
        } else {
            esriConfig.request.useIdentity = false;
        }

        await createMapElement({
            basemap: "topo-vector",
            center: "-98,39",
            zoom: "4"
        });

        // Helper: load a single layer URL, expanding FeatureServer roots into sublayers
        async function loadLayer(url, whereClause) {
            const isServiceRoot = /\\/(FeatureServer|MapServer)\\/?$/i.test(url.replace(/\\?.*$/, ""));
            if (isServiceRoot) {
                try {
                    const infoUrl = url.replace(/\\/$/, "") + "?f=json";
                    const tokenParam = data.token ? "&token=" + encodeURIComponent(data.token) : "";
                    const resp = await fetch(infoUrl + tokenParam);
                    const info = await resp.json();
                    if (info.layers && info.layers.length > 0) {
                        const sublayers = [];
                        for (const sublayerInfo of info.layers) {
                            try {
                                const sublayerUrl = url.replace(/\\/$/, "") + "/" + sublayerInfo.id;
                                const layer = new FeatureLayer({
                                    url: sublayerUrl,
                                    definitionExpression: whereClause || undefined
                                });
                                mapElement.map.add(layer);
                                sublayers.push(layer);
                            } catch (subErr) {
                                console.warn("Skipping sublayer " + sublayerInfo.id + " from " + url + ":", subErr);
                            }
                        }
                        if (sublayers.length > 0) return sublayers;
                    }
                } catch (e) {
                    console.warn("Could not enumerate sublayers for " + url + ", falling back to direct load:", e);
                }
            }
            const opts = { url: url };
            if (whereClause) {
                opts.properties = { definitionExpression: whereClause };
            }
            const layer = await Layer.fromArcGISServerUrl(opts);
            mapElement.map.add(layer);
            return layer;
        }

        const layerResults = await Promise.all(
            data.layer_urls.map(function(url, i) {
                const whereClause = (data.layer_where_clauses && data.layer_where_clauses[i]) ? data.layer_where_clauses[i] : null;
                return loadLayer(url, whereClause).catch(function(error) {
                    console.error("Error adding layer " + url + ":", error);
                    return null;
                });
            })
        );

        const anyLoaded = layerResults.some(function(r) { return r != null; });
        if (!anyLoaded && data.layer_urls.length > 0) {
            showError("Error: Could not load any of the provided layers. Check that the URLs are accessible and the service is running.");
        }
        executeCustomizationScript(data);
        updateModelContext(app);
    } catch (error) {
        showError("Error initializing layers map: " + error.message);
    }
}

// --- Customization script execution ---
function executeCustomizationScript(data) {
    if (!data.customization_script) return;
    if (!mapView) {
        console.warn("[MapViewer] Skipping customization script: mapView is not initialized");
        return;
    }
    try {
        // The script receives mapView and mapElement as parameters.
        // $arcgis.import() is available globally from the ArcGIS Maps SDK.
        const fn = new Function("mapView", "mapElement", "return (async function() {\\n" + data.customization_script + "\\n})()");
        const result = fn(mapView, mapElement);
        if (result && typeof result.catch === "function") {
            result.catch(function(e) {
                console.error("[MapViewer] Customization script async error:", e);
            });
        }
    } catch (e) {
        console.error("[MapViewer] Customization script error:", e);
    }
}

// --- App-side tools ---
function registerAppTools(app) {
    // add_layer: adds a layer to the existing map
    app.registerTool("add_layer", {
        description: "Add a layer to the existing map by URL",
        inputSchema: {
            type: "object",
            properties: {
                url: { type: "string", description: "Layer service URL" },
                where_clause: { type: "string", description: "Optional definition expression to filter features" }
            },
            required: ["url"]
        }
    }, async function(params) {
        const args = params.arguments || params;
        const url = args.url;
        if (!url || !mapView) {
            return { content: [{ type: "text", text: "Error: No URL provided or map not initialized" }], isError: true };
        }
        try {
            const Layer = await $arcgis.import("@arcgis/core/layers/Layer.js");
            const opts = { url: url };
            if (args.where_clause) {
                opts.properties = { definitionExpression: args.where_clause };
            }
            const layer = await Layer.fromArcGISServerUrl(opts);
            mapView.map.add(layer);
            await updateModelContext(app);
            return { content: [{ type: "text", text: "Layer added: " + url }] };
        } catch (e) {
            return { content: [{ type: "text", text: "Error adding layer: " + e.message }], isError: true };
        }
    });

    // remove_layer: removes a layer by URL or index
    app.registerTool("remove_layer", {
        description: "Remove a layer from the map by URL or index",
        inputSchema: {
            type: "object",
            properties: {
                url_or_index: { type: "string", description: "Layer URL or numeric index to remove" }
            },
            required: ["url_or_index"]
        }
    }, async function(params) {
        const args = params.arguments || params;
        const urlOrIndex = args.url_or_index;
        if (!mapView) {
            return { content: [{ type: "text", text: "Error: Map not initialized" }], isError: true };
        }
        try {
            let layer = null;
            const idx = parseInt(urlOrIndex, 10);
            if (!isNaN(idx) && String(idx) === String(urlOrIndex).trim()) {
                layer = mapView.map.layers.getItemAt(idx);
            } else {
                layer = mapView.map.layers.find(function(l) { return l.url === urlOrIndex; });
            }
            if (!layer) {
                return { content: [{ type: "text", text: "Error: Layer not found: " + urlOrIndex }], isError: true };
            }
            mapView.map.remove(layer);
            await updateModelContext(app);
            return { content: [{ type: "text", text: "Layer removed: " + urlOrIndex }] };
        } catch (e) {
            return { content: [{ type: "text", text: "Error removing layer: " + e.message }], isError: true };
        }
    });

    // change_basemap: switches the basemap
    app.registerTool("change_basemap", {
        description: "Change the map basemap",
        inputSchema: {
            type: "object",
            properties: {
                basemap: { type: "string", description: "Basemap name (e.g., satellite, topo-vector, streets)" }
            },
            required: ["basemap"]
        }
    }, async function(params) {
        const args = params.arguments || params;
        const basemapName = args.basemap;
        if (!mapView) {
            return { content: [{ type: "text", text: "Error: Map not initialized" }], isError: true };
        }
        try {
            mapView.map.basemap = basemapName;
            await updateModelContext(app);
            return { content: [{ type: "text", text: "Basemap changed to: " + basemapName }] };
        } catch (e) {
            return { content: [{ type: "text", text: "Error changing basemap: " + e.message }], isError: true };
        }
    });

    // update_symbology: applies a renderer JSON to a layer
    app.registerTool("update_symbology", {
        description: "Apply a renderer definition to a layer",
        inputSchema: {
            type: "object",
            properties: {
                url_or_index: { type: "string", description: "Layer URL or numeric index" },
                renderer: { type: "object", description: "Renderer definition as JSON" }
            },
            required: ["url_or_index", "renderer"]
        }
    }, async function(params) {
        const args = params.arguments || params;
        const urlOrIndex = args.url_or_index;
        const rendererDef = args.renderer;
        if (!mapView) {
            return { content: [{ type: "text", text: "Error: Map not initialized" }], isError: true };
        }
        try {
            let layer = null;
            const idx = parseInt(urlOrIndex, 10);
            if (!isNaN(idx) && String(idx) === String(urlOrIndex).trim()) {
                layer = mapView.map.layers.getItemAt(idx);
            } else {
                layer = mapView.map.layers.find(function(l) { return l.url === urlOrIndex; });
            }
            if (!layer) {
                return { content: [{ type: "text", text: "Error: Layer not found: " + urlOrIndex }], isError: true };
            }
            const rendererUtils = await $arcgis.import("@arcgis/core/renderers/support/jsonUtils.js");
            layer.renderer = rendererUtils.fromJSON(rendererDef);
            await updateModelContext(app);
            return { content: [{ type: "text", text: "Symbology updated for layer: " + urlOrIndex }] };
        } catch (e) {
            return { content: [{ type: "text", text: "Error updating symbology: " + e.message }], isError: true };
        }
    });

    // get_current_view: returns current map state
    app.registerTool("get_current_view", {
        description: "Get the current map extent, center, zoom, layers, and basemap",
        inputSchema: {
            type: "object",
            properties: {}
        }
    }, async function() {
        if (!mapView) {
            return { content: [{ type: "text", text: "Error: Map not initialized" }], isError: true };
        }
        try {
            const extent = mapView.extent;
            const center = mapView.center;
            const zoom = mapView.zoom;
            const basemap = mapView.map.basemap?.title || mapView.map.basemap?.id || "unknown";
            const layers = [];
            if (mapView.map.layers) {
                mapView.map.layers.forEach(function(layer) {
                    layers.push({
                        title: layer.title || "Untitled",
                        url: layer.url || null,
                        visible: layer.visible,
                        type: layer.type || "unknown"
                    });
                });
            }
            const result = {
                extent: extent ? { xmin: extent.xmin, ymin: extent.ymin, xmax: extent.xmax, ymax: extent.ymax, spatialReference: extent.spatialReference?.wkid } : null,
                center: center ? { longitude: center.longitude, latitude: center.latitude } : null,
                zoom: zoom,
                basemap: basemap,
                layers: layers
            };
            return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
        } catch (e) {
            return { content: [{ type: "text", text: "Error getting current view: " + e.message }], isError: true };
        }
    });
}

// --- Main ---
(async function() {
    const app = new App({ name: "ArcGIS Map Viewer", version: "1.0.0" }, { tools: { listChanged: true } });

    // Register handlers BEFORE connecting
    app.ontoolinput = function(params) {
        if (params.arguments) {
            currentData = params.arguments;
        }
    };

    app.ontoolresult = function(result) {
        let data = null;
        if (result.structuredContent) {
            data = result.structuredContent;
        } else if (result.content) {
            for (const block of result.content) {
                if (block.type === "text" && block.text) {
                    try {
                        const parsed = JSON.parse(block.text);
                        if (parsed && typeof parsed === "object" && parsed.type) {
                            data = parsed;
                            break;
                        }
                    } catch (e) {
                        // Not JSON, skip
                    }
                }
            }
        }
        console.log("[MapViewer] Parsed tool result data:", JSON.stringify(data ? { type: data.type, hasToken: !!data.token, tokenServers: data.token_servers } : null));
        if (data) {
            currentData = data;
            initializeMap(data, app);
        } else {
            showError("Error: Could not parse tool result data. No valid map configuration found.");
        }
    };

    app.onteardown = async function() {
        if (mapView) {
            mapView.destroy();
            mapView = null;
        }
        return {};
    };

    app.onerror = function(error) {
        console.error("MCP App error:", error);
    };

    // Register app-side tools
    registerAppTools(app);

    // Connect to host
    await app.connect();
})();
    </script>
</body>
</html>
"""
