---
name: map-feature-pointing
description: Show or highlight referenced features on the active browser map using user context and GlobalIDs.
tags: [agent-runtime, map]
---

# Map Feature Pointing

This workflow needs generic browser tools, not server-side map effects.

1. For "this", "selected", or "the asset I added", call `getUserAddedContext({})`
   first. Prefer explicit user context over guesses from visible layers.
2. Inspect `getCurrentMapContext({})`, `getWebMapInfo`, or `getLayerInfo` as needed.
   Resolve ambiguity before choosing a specific feature. Obtain its actual GlobalID
   from context or an available feature query; do not manufacture one.
3. Call `highlightFeaturesByGlobalIds({globalIds: [...], zoom: true})` with all
   intended GlobalIDs in one call. Optional `targetGlobalId`, `layerTitle`, and
   `layerId` must refer to actual browser map discovery, not a server source/layer
   number. A new highlight call replaces the prior highlight set.
4. Check `highlightedCount` and `notFoundGlobalIds`. Report unmatched features;
   never claim a highlight succeeded simply because a lookup/trace succeeded.
5. If only a known location is available, call
   `zoomTo({latitude: ..., longitude: ..., label: ...})` with WGS84 degrees.
   Explain that a location pin is not a resolved feature.

If browser capabilities or the target layer are unavailable, retain the feature
identity and explain the presentation limitation. Keep the final answer concise
when the map already communicates the result.
