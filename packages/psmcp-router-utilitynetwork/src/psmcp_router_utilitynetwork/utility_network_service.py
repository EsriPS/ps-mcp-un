"""ArcGIS Utility Network router plugin for PS-MCP."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any
from dotenv import load_dotenv

load_dotenv()

from arcgis.features import FeatureLayer, FeatureLayerCollection
from arcgis.features._utility import UtilityNetworkManager
from arcgis.gis import GIS
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

logger = logging.getLogger(__name__)

utilitynetwork_router = FastMCP(name="Utility Network Service")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"

_PII_FIELDS = {"full_name", "phone_number", "billing_address"}


def _read_value(value: Any, key: str) -> Any:
    """Read a key from either dict-like or attribute-style ArcGIS objects."""
    if isinstance(value, dict):
        return value.get(key)
    getter = getattr(value, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            pass
    return getattr(value, key, None)






def _utility_network_url(network_service_url: str) -> str:
    """FeatureServer URL -> UtilityNetworkServer URL (manager REST endpoint)."""
    base = network_service_url.rstrip("/")
    if base.lower().endswith("/utilitynetworkserver"):
        return base
    if base.lower().endswith("/featureserver"):
        parent, _ = base.rsplit("/", 1)
        return f"{parent}/UtilityNetworkServer"
    return f"{base}/UtilityNetworkServer"

def get_network_source_name(utility_network, search_name: str):
    """Match a layer/alias name to the registered UN source name."""
    sources = utility_network.properties.networkSources
    for src in sources:
        if search_name.lower() in src["name"].lower():
            print(f"  Matched source: '{src['name']}'  "
                  f"(sourceId={src['sourceId']}, type={src['sourceType']})")
            return src["name"]
    # print all available if no match
    print("No match found. Available network sources:")
    for src in sources:
        print(f"  sourceId={src['sourceId']}  name={src['name']}")
    return None

def _connect_gis(token: str | None) -> GIS:
    token = resolve_token(token)
    if not token and not ARCGIS_PORTAL_URL:
        raise ValueError("Set ARCGIS_TOKEN or ARCGIS_PORTAL_URL.")
    kwargs: dict[str, Any] = {"verify_cert": VERIFY_SSL}
    if token:
        kwargs["token"] = token
    started = time.perf_counter()
    if ARCGIS_PORTAL_URL:
        gis = GIS(url=ARCGIS_PORTAL_URL, **kwargs)
    else:
        gis = GIS(**kwargs)
    logger.info(
        "_connect_gis: GIS connection established in %.2f seconds.",
        time.perf_counter() - started,
    )
    return gis


def _starting_point(
    global_id: str,
    terminal_id: int | None = None,
    percent_along: float | None = None,
) -> list[dict[str, Any]]:
    """Build a traceLocations starting-point entry.

    For junction features supply ``terminal_id``.
    For edge features supply ``percent_along`` (0.0–1.0).
    Omitting both lets the server use its own defaults.
    """
    loc: dict[str, Any] = {
        "traceLocationType": "startingPoint",
        "globalId": global_id,
    }
    if terminal_id is not None:
        loc["terminalId"] = terminal_id
    if percent_along is not None:
        loc["percentAlong"] = percent_along
    return [loc]





def _named_trace_config(un_manager: UtilityNetworkManager, named_trace_name: str) -> dict[str, Any]:
    """Look up a named trace configuration by name and return its full record.

    Matching is case-insensitive against the configuration title/name. If no name
    matches exactly, the lookup falls back to a forgiving match so a paraphrased
    request (e.g. ``"Subnetwork"`` or ``"Distribution Isolation"``) still resolves
    to the saved configuration (``"Subnetwork Trace"`` / ``"Distribution Isolation
    Trace"``) as long as exactly one configuration fits. When nothing matches, or
    a paraphrase is ambiguous, raises a ``ValueError`` that lists the available
    names so the caller (agent) can pick a real one instead of guessing.

    The returned record carries the persisted ``globalId`` and ``traceType`` (the
    trace algorithm the configuration was saved with), so callers do not have to
    guess the direction.
    """
    result = un_manager.trace_configurations().query()
    configs = result.get("traceConfigurations", []) or []
    target = named_trace_name.strip().lower()

    named = [(str(cfg.get("title") or cfg.get("name") or ""), cfg) for cfg in configs]
    named = [(name, cfg) for name, cfg in named if name]

    # 1. Exact case-insensitive match on the saved title/name.
    for name, cfg in named:
        if name.strip().lower() == target:
            return cfg

    # 2. Forgiving match: the agent often drops or adds the word "trace" (asking
    #    for "Subnetwork" instead of the saved "Subnetwork Trace"). Compare the
    #    names with the trailing "trace" word removed so those paraphrases resolve.
    fuzzy = [(name, cfg) for name, cfg in named if _strip_trace_suffix(name) == _strip_trace_suffix(named_trace_name)]

    # 3. Substring containment as a last resort (e.g. "Distribution Isolation"
    #    inside "Distribution Isolation Trace"), still requiring a single fit.
    if not fuzzy:
        fuzzy = [
            (name, cfg)
            for name, cfg in named
            if _strip_trace_suffix(named_trace_name) and _strip_trace_suffix(named_trace_name) in _strip_trace_suffix(name)
        ]

    # Only accept a paraphrase when it is unambiguous — one configuration fits.
    unique = {id(cfg): (name, cfg) for name, cfg in fuzzy}
    if len(unique) == 1:
        return next(iter(unique.values()))[1]

    available = sorted(name for name, _ in named)
    raise ValueError(
        f"Named trace configuration '{named_trace_name}' not found. "
        f"Available named traces ({len(available)}): {', '.join(available) or '(none)'}"
    )


def _strip_trace_suffix(name: str) -> str:
    """Normalize a named-trace name for forgiving comparison.

    Lower-cases, collapses whitespace, and drops a trailing ``"trace"`` word so
    ``"Subnetwork Trace"`` and ``"Subnetwork"`` compare equal.
    """
    normalized = " ".join(name.strip().lower().split())
    if normalized.endswith(" trace"):
        normalized = normalized[: -len(" trace")]
    elif normalized == "trace":
        normalized = ""
    return normalized


def _named_trace_global_id(un_manager: UtilityNetworkManager, named_trace_name: str) -> str:
    """Look up the global ID for a named trace configuration by name."""
    config = _named_trace_config(un_manager, named_trace_name)
    global_id = config.get("globalId")
    if not global_id:
        raise ValueError(f"Named trace '{named_trace_name}' has no globalId.")
    return str(global_id)


def run_named_trace(
    gis: GIS,
    network_service_url: str,
    named_trace_name: str,
    global_id: str,
    trace_type: str | None = None,
    terminal_id: int | None = None,
) -> dict[str, Any]:
    """Run a named trace from a starting feature global ID.

    Args:
        trace_type: The trace algorithm to execute (e.g. 'connected', 'upstream',
            'downstream', 'subnetwork', 'subnetworkController', 'loops',
            'shortestPath', 'isolation').  When omitted (``None``) the value is
            taken from the named trace configuration's persisted ``traceType`` so
            the trace runs with the algorithm it was saved with.  Pass an explicit
            value only to override that persisted type.
        terminal_id: For junction features with multiple terminals, the terminal
            from which to start the trace.  Omit for edge features or single-
            terminal junctions.
    """
    un_manager = UtilityNetworkManager(_utility_network_url(network_service_url), gis=gis)
    lookup_started = time.perf_counter()
    config = _named_trace_config(un_manager, named_trace_name)
    logger.info(
        "run_named_trace: resolved named trace config '%s' in %.2f seconds.",
        named_trace_name, time.perf_counter() - lookup_started,
    )
    trace_config_id = config.get("globalId")
    if not trace_config_id:
        raise ValueError(f"Named trace '{named_trace_name}' has no globalId.")
    # Fall back to the configuration's persisted type; only default to 'connected'
    # when neither the caller nor the server config provides one.
    resolved_trace_type = trace_type or config.get("traceType") or "connected"
    # --- DISABLED (2026-07-09): custom start-feature validation moved to the
    # frontend skill. The MCP is now a thin passthrough for named-trace calls.
    # Re-enable if we decide to enforce tier / terminal rules server-side again.
    #
    # # Reject start features that are not in the tier this named trace targets.
    # invalid_start = _validate_start_in_tier(gis, network_service_url, global_id, config)
    # if invalid_start is not None:
    #     logger.info(
    #         "run_named_trace: start feature %s is not in the '%s' tier required by "
    #         "'%s'; returning invalid_start_point.",
    #         global_id, invalid_start.get("requiredTier"), named_trace_name,
    #     )
    #     return invalid_start
    # # Multi-terminal devices: surface terminal options instead of guessing.
    # if terminal_id is None:
    #     prompt = _terminal_selection_prompt(
    #         gis, network_service_url, global_id, named_trace_name, resolved_trace_type
    #     )
    #     if prompt is not None:
    #         logger.info(
    #             "run_named_trace: '%s' start feature %s has multiple terminals; "
    #             "returning terminal-selection prompt.",
    #             named_trace_name, global_id,
    #         )
    #         return prompt
    logger.info(
        "Running named trace '%s' (type=%s) from %s (terminalId=%s)",
        named_trace_name, resolved_trace_type, global_id, terminal_id,
    )
    start_pnt = _starting_point(global_id=global_id, terminal_id=terminal_id)
    trace_started = time.perf_counter()
    result = un_manager.trace(
        locations=start_pnt,
        trace_type=resolved_trace_type,
        trace_config_global_id=str(trace_config_id),
    )
    logger.info(
        "run_named_trace: un_manager.trace('%s') completed in %.2f seconds.",
        named_trace_name, time.perf_counter() - trace_started,
    )
    return result


_NO_STARTING_POINTS = -2147208614  # extendedCode for "No starting points found."


def _validate_topology(un_manager: UtilityNetworkManager, feature_service_url: str, gis: GIS) -> None:
    """Attempt a topology validation over the service extent.

    Called automatically when a trace returns 'No starting points found' to
    recover from a stale topology (e.g. after a network definition modification
    that was never followed by a validate).

    Tries ``normal`` first (validates dirty areas).  If that returns 'no dirty
    areas', tries ``forceRebuild`` to rebuild the full topology index.
    Logs a warning but does not raise — the trace will retry regardless.
    """
    try:
        flc = FeatureLayerCollection(feature_service_url.rstrip("/"), gis=gis)
        extent = dict(flc.properties.get("fullExtent", {}))
        if not extent:
            logger.warning("validate_topology: could not determine service extent; skipping.")
            return
        result = un_manager.validate_topology(envelope=extent)
        if result.get("success"):
            logger.info("validate_topology (normal) succeeded: %s", result)
            return
        msg = result.get("error", {}).get("message", "")
        logger.warning("validate_topology (normal) non-success: %s", msg)
        # If no dirty areas exist the topology index may be entirely stale —
        # force a full rebuild.
        logger.info("Retrying topology validation with forceRebuild ...")
        result2 = un_manager.validate_topology(envelope=extent, validation_type="forceRebuild")
        if result2.get("success"):
            logger.info("validate_topology (forceRebuild) succeeded.")
        else:
            logger.warning(
                "validate_topology (forceRebuild) non-success: %s",
                result2.get("error", {}).get("message", str(result2)),
            )
    except Exception as exc:
        logger.warning("validate_topology raised an exception: %s", exc)


def run_trace(
    gis: GIS,
    network_service_url: str,
    trace_type: str,
    global_id: str,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    terminal_id: int | None = None,
    percent_along: float | None = None,
    feature_service_url: str | None = None,
) -> dict[str, Any]:
    """Execute a direct upstream or downstream trace on the utility network.

    This calls the UN trace REST endpoint with ``traceType`` set to
    ``trace_type`` ("upstream" or "downstream") without referencing any
    named/persisted trace configuration.

    Starting-point resolution order:
    1. ``terminal_id`` or ``percent_along`` — use the caller-supplied value.
    2. ``feature_service_url`` provided — query the feature's assetgroup/
       assettype and look up its terminals from the UN network definition;
       one starting point is created per terminal so the trace engine can
       choose the correct one.
    3. Neither — omit terminal/percent fields and let the server decide
       (works only for single-terminal junctions).
    """
    un_manager = UtilityNetworkManager(_utility_network_url(network_service_url), gis=gis)

    # --- resolve starting locations ---
    if terminal_id is not None or percent_along is not None:
        # Explicit value supplied by the caller.
        locations = _starting_point(global_id, terminal_id=terminal_id, percent_along=percent_along)
    elif feature_service_url:
        # Auto-detect terminals from the feature's asset type definition.
        # terminal_ids = _terminal_ids_for_feature(gis, feature_service_url, global_id, un_manager)
        # if terminal_ids:
        #     logger.debug("Auto-detected terminals %s for %s", terminal_ids, global_id)
        #     locations = [
        #         {"traceLocationType": "startingPoint", "globalId": global_id, "terminalId": tid}
        #         for tid in terminal_ids
        #     ]
        # else:
        locations = _starting_point(global_id)
    else:
        locations = _starting_point(global_id)

    # --- trace configuration ---
    configuration: dict[str, Any] = {}
    if domain_network_name:
        configuration["domainNetworkName"] = domain_network_name
    if tier_name:
        configuration["tierName"] = tier_name

    logger.info("Running %s trace from %s", trace_type, global_id)

    def _do_trace() -> dict[str, Any]:
        # Do NOT pass trace_config_global_id — that would invoke a named trace.
        return un_manager.trace(
            locations=locations,
            trace_type=trace_type,
            configuration=configuration if configuration else None,
            result_types=[{"type": "elements"}],
        )

    raw = _do_trace()

    # If the topology is stale (e.g. after a definition modification that was
    # never followed by a validate), validate it and retry once.
    if raw.get("error", {}).get("extendedCode") == _NO_STARTING_POINTS and feature_service_url:
        logger.warning(
            "Trace returned 'No starting points found'; attempting topology "
            "validation and retrying."
        )
        _validate_topology(un_manager, feature_service_url, gis)
        raw = _do_trace()

    return raw


def _find_layer(gis: GIS, service_url: str, name: str) -> FeatureLayer:
    flc = FeatureLayerCollection(service_url.rstrip("/"), gis=gis)
    target = name.lower()
    for group in (flc.layers, flc.tables):
        for layer in group:
            if layer.properties.name.lower() == target:
                return layer
    raise ValueError(f"Layer or table '{name}' not found.")


def _quote(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def get_customer_data(
    gis: GIS,
    service_url: str,
    global_ids: list[str],
    meter_ids: list[str] | None = None,
) -> dict[str, Any]:
    meter_ids = list(dict.fromkeys(meter_ids or []))
    global_map: list[dict[str, str]] = []

    if not meter_ids:
        if not global_ids:
            raise ValueError("Provide meter_ids or global_ids.")
        device_layer = _find_layer(gis, service_url, "Electric Device")
        for feature in device_layer.query(
            where=f"globalid IN ({_quote(global_ids)})",
            out_fields="globalid,meter_id",
            return_geometry=False,
        ).features:
            mid = feature.attributes.get("meter_id")
            gid = feature.attributes.get("globalid")
            if mid:
                meter_ids.append(str(mid))
                global_map.append({"globalId": str(gid), "meterId": str(mid)})
        meter_ids = list(dict.fromkeys(meter_ids))

    if not meter_ids:
        return {"meterIds": [], "globalIdMeterMap": global_map, "customers": [], "customerCount": 0}

    cust_layer = _find_layer(gis, service_url, "CIS_CUST_VIEW")
    out_fields = ",".join(
        f["name"] for f in cust_layer.properties.fields if f["name"].lower() not in _PII_FIELDS
    ) or "*"
    customers = [
        {k: v for k, v in f.attributes.items() if k.lower() not in _PII_FIELDS}
        for f in cust_layer.query(
            where=f"meter_id IN ({_quote(meter_ids)})",
            out_fields=out_fields,
            return_geometry=False,
        ).features
    ]
    return {
        "meterIds": meter_ids,
        "globalIdMeterMap": global_map,
        "customers": customers,
        "customerCount": len(customers),
    }


def _terminal_recommended_for(is_upstream_terminal: bool | None) -> str | None:
    """Map a terminal's ``isUpstreamTerminal`` flag to the trace direction it suits.

    Upstream terminals (primary / high side / source side) start upstream and
    isolation traces; downstream terminals (secondary / low side / line side)
    start downstream traces.  Returns ``None`` when the flag is unknown.
    """
    if is_upstream_terminal is True:
        return "upstream"
    if is_upstream_terminal is False:
        return "downstream"
    return None


# Maps a trace's persisted ``traceType`` to the terminal direction a device should
# start from. Used only to flag the *recommended* terminal in a selection prompt;
# the user still chooses. Trace types not listed have no directional preference.
_TRACE_TYPE_TERMINAL_DIRECTION = {
    "downstream": "downstream",
    "upstream": "upstream",
    "isolation": "upstream",
}


def _recommended_terminal_direction(trace_type: str | None) -> str | None:
    """Return the terminal direction ('upstream'/'downstream') a trace prefers."""
    return _TRACE_TYPE_TERMINAL_DIRECTION.get((trace_type or "").strip().lower())


def _un_data_element(flc: FeatureLayerCollection) -> dict[str, Any]:
    """Return the utility network data element (schema) from a FeatureServer.

    The data element carries the full network model: domain networks, their
    junction/edge sources, the asset groups/types within each source, and the
    terminal configurations that asset types reference.
    """
    props_started = time.perf_counter()
    controller = dict(flc.properties.get("controllerDatasetLayers", {}) or {})
    logger.info(
        "_un_data_element: FeatureServer properties loaded in %.2f seconds.",
        time.perf_counter() - props_started,
    )
    un_layer_id = controller.get("utilityNetworkLayerId")
    if un_layer_id is None:
        raise ValueError(
            "Service is not a utility network "
            "(no utilityNetworkLayerId in controllerDatasetLayers)."
        )
    started = time.perf_counter()
    result = flc.query_data_elements([un_layer_id])
    logger.info(
        "_un_data_element: query_data_elements(layer=%s) completed in %.2f seconds.",
        un_layer_id, time.perf_counter() - started,
    )
    elements = result.get("layerDataElements") if isinstance(result, dict) else None
    if not elements:
        raise ValueError("queryDataElements returned no utility network data element.")
    data_element = elements[0].get("dataElement", {})
    if not data_element:
        raise ValueError("Utility network data element is empty.")
    return data_element


def _feature_tier_info(
    flc: FeatureLayerCollection,
    domain: dict[str, Any],
    attrs: dict[str, Any],
) -> dict[str, Any]:
    """Return everything needed to decide which tier a feature belongs to.

    A feature does not store its tier directly. What it does store is its
    subnetwork membership (the SUBNETWORKNAME field). This helper returns three
    things so the model can determine the tier:

    1. ``tiers`` — the domain's full tier catalog (every tier's name, rank, and
       group). ``rank`` is what separates higher tiers (e.g. transmission) from
       lower ones (e.g. distribution).
    2. ``subnetworkName`` / ``subnetworkNames`` — the feature's raw and split
       subnetwork membership, the bridge between the feature and a tier.
    3. ``featureTierNames`` / ``featureTierRanks`` — the tier(s) the feature
       actually participates in, resolved by looking each subnetwork name up in
       the domain's subnetwork line layer (its TIERNAME column holds the tier
       rank) and mapping that rank back to the catalog.

    The layer is found by role (``subnetworkLayerId``), not by name, so it works
    regardless of how the service names its layers. Resolution is best-effort: if
    the subnetwork membership can't be joined, the catalog and subnetwork names
    are still returned so the model has what it needs to reason.
    """
    # The domain's ordered tier catalog. rank tells higher tiers (transmission)
    # from lower ones (distribution); the model uses this to pick or verify a tier.
    tiers = domain.get("tiers", []) or []
    tier_catalog = [
        {
            "tierId": t.get("tierId"),
            "name": t.get("name"),
            "rank": t.get("rank"),
            "tierGroupName": t.get("tierGroupName"),
        }
        for t in tiers
    ]
    name_by_rank = {t.get("rank"): t.get("name") for t in tiers if t.get("rank") is not None}

    # The feature's subnetwork membership is the only link it carries to a tier.
    subnetwork_names = _split_subnetwork_names(attrs.get("subnetworkname"))

    info: dict[str, Any] = {
        "subnetworkName": attrs.get("subnetworkname"),
        "subnetworkNames": subnetwork_names,
        "tiers": tier_catalog,
        "featureTierNames": [],
        "featureTierRanks": [],
    }

    # Join subnetwork names -> tier ranks via the subnetwork line layer, then map
    # those ranks back to tier names. Bail out quietly on any gap.
    subnetwork_layer_id = domain.get("subnetworkLayerId")
    if not subnetwork_names or subnetwork_layer_id is None or subnetwork_layer_id < 0:
        return info
    try:
        layers_by_id = {int(lyr.properties.id): lyr for lyr in flc.layers}
        subnet_layer = layers_by_id.get(int(subnetwork_layer_id))
        if subnet_layer is None:
            return info
        rows = subnet_layer.query(
            where=f"SUBNETWORKNAME IN ({_quote(subnetwork_names)})",
            out_fields="SUBNETWORKNAME,TIERNAME",
            return_geometry=False,
        ).features
        ranks = sorted(
            {r.attributes.get("TIERNAME") for r in rows if r.attributes.get("TIERNAME") is not None}
        )
        info["featureTierRanks"] = ranks
        info["featureTierNames"] = [name_by_rank.get(r, f"rank {r}") for r in ranks]
    except Exception as exc:  # noqa: BLE001 - tier resolution must never break the tool
        logger.warning(
            "Tier resolution for subnetworks %s failed: %s", subnetwork_names, exc
        )
    return info


def get_device_terminals(
    gis: GIS,
    feature_service_url: str,
    global_id: str,
) -> dict[str, Any]:
    """Resolve the terminal(s) of a network feature identified by its GlobalID.

    Loads the utility network data element, locates the feature across the
    network's junction/edge source layers to read its asset group/type, then
    maps that asset type to its terminal configuration and returns the terminals.

    It also returns the data needed to determine the feature's tier: the domain's
    tier catalog, the feature's subnetwork membership, and — when it can join the
    two — the resolved tier(s) the feature participates in.
    """
    flc = FeatureLayerCollection(feature_service_url.rstrip("/"), gis=gis)
    flc_started = time.perf_counter()
    data_element = _un_data_element(flc)
    terminal_configs = {
        cfg.get("terminalConfigurationId"): cfg
        for cfg in data_element.get("terminalConfigurations", []) or []
    }
    layers_by_id = {int(lyr.properties.id): lyr for lyr in flc.layers}
    logger.info(
        "get_device_terminals: loaded data element + %d layers in %.2f seconds.",
        len(layers_by_id), time.perf_counter() - flc_started,
    )

    gid = global_id.strip()
    where = f"globalid = {_quote([gid])}"

    scan_started = time.perf_counter()
    queries = 0
    for domain in data_element.get("domainNetworks", []) or []:
        junction_sources = domain.get("junctionSources", []) or []
        edge_sources = domain.get("edgeSources", []) or []
        for source_type, source in (
            [("junction", s) for s in junction_sources]
            + [("edge", s) for s in edge_sources]
        ):
            layer = layers_by_id.get(source.get("layerId"))
            if layer is None:
                continue
            queries += 1
            features = layer.query(
                where=where, out_fields="*", return_geometry=False
            ).features
            if not features:
                continue
            logger.info(
                "get_device_terminals: found feature after %d source-layer queries in %.2f seconds.",
                queries, time.perf_counter() - scan_started,
            )

            # Field casing varies by service, so read asset codes case-insensitively.
            attrs = {k.lower(): v for k, v in features[0].attributes.items()}
            assetgroup_code = attrs.get("assetgroup")
            assettype_code = attrs.get("assettype")

            grp = next(
                (
                    g for g in source.get("assetGroups", []) or []
                    if g.get("assetGroupCode") == assetgroup_code
                ),
                None,
            )
            asset_type = next(
                (
                    a for a in (grp or {}).get("assetTypes", []) or []
                    if a.get("assetTypeCode") == assettype_code
                ),
                None,
            )
            cfg = terminal_configs.get(
                asset_type.get("terminalConfigurationId") if asset_type else None, {}
            )
            terminals = [
                {
                    "terminalId": t.get("terminalId"),
                    "terminalName": t.get("terminalName"),
                    "isUpstreamTerminal": t.get("isUpstreamTerminal"),
                    # Trace-direction hint: upstream terminals (primary / high side /
                    # source side) are the correct start for upstream/isolation traces;
                    # downstream terminals (secondary / low side / line side) are the
                    # correct start for downstream traces.
                    "recommendedFor": _terminal_recommended_for(t.get("isUpstreamTerminal")),
                }
                for t in cfg.get("terminals", []) or []
            ]
            # The source's usage type tells the caller what "role" this layer plays in the
            # utility network (device, junction, line, assembly, ...).  Distribution /
            # isolation trace start points must be devices (``esriUNFCUTDevice``).
            usage_type = source.get("utilityNetworkFeatureClassUsageType")
            # Everything the model needs to determine the feature's tier: the domain's
            # tier catalog, the feature's subnetwork membership, and the resolved tier.
            tier_info = _feature_tier_info(flc, domain, attrs)
            return {
                "globalId": gid,
                "domainNetworkName": domain.get("domainNetworkName"),
                "sourceType": source_type,
                "layerId": source.get("layerId"),
                "usageType": usage_type,
                "isDevice": usage_type == "esriUNFCUTDevice",
                "assetGroupCode": assetgroup_code,
                "assetGroupName": grp.get("assetGroupName") if grp else None,
                "assetTypeCode": assettype_code,
                "assetTypeName": asset_type.get("assetTypeName") if asset_type else None,
                "terminalConfigurationId": cfg.get("terminalConfigurationId"),
                "terminalConfigurationName": cfg.get("terminalConfigurationName"),
                "terminals": terminals,
                "terminalCount": len(terminals),
                "subnetworkName": tier_info["subnetworkName"],
                "subnetworkNames": tier_info["subnetworkNames"],
                "tiers": tier_info["tiers"],
                "featureTierNames": tier_info["featureTierNames"],
                "featureTierRanks": tier_info["featureTierRanks"],
            }

    raise ValueError(f"No network feature found with GlobalID {gid}.")


# Status marker returned to the agent when a multi-terminal start feature needs a
# terminal_id before the trace can run. The agent must relay the options to the
# user, then call network_named_trace again with the chosen terminal_id.
NEEDS_TERMINAL_SELECTION = "needs_terminal_selection"


def _terminal_selection_prompt(
    gis: GIS,
    feature_service_url: str,
    global_id: str,
    named_trace_name: str,
    trace_type: str | None,
) -> dict[str, Any] | None:
    """Return a structured 'choose a terminal' response for multi-terminal devices.

    Multi-terminal devices (e.g. two-winding transformers, switches) REQUIRE a
    terminal_id — without one the trace engine returns an opaque
    "No starting points found." Rather than guess, this inspects the start
    feature's terminals and, when there is more than one, returns a structured
    prompt listing the options so the agent can ask the user to pick.

    Returns ``None`` when the feature has zero or one terminal (no choice needed)
    or when terminal inspection fails, so the caller proceeds with the server
    default.
    """
    try:
        info = get_device_terminals(gis, feature_service_url, global_id)
    except Exception as exc:  # noqa: BLE001 - never block a trace on a precheck failure
        logger.warning(
            "Terminal precheck for %s failed (%s); proceeding without a terminal.",
            global_id, exc,
        )
        return None

    terminals = info.get("terminals", []) or []
    if len(terminals) <= 1:
        return None

    preferred_direction = _recommended_terminal_direction(trace_type)
    recommended_terminal_id = next(
        (
            term.get("terminalId")
            for term in terminals
            if preferred_direction and term.get("recommendedFor") == preferred_direction
        ),
        None,
    )
    options = [
        {
            "terminalId": term.get("terminalId"),
            "terminalName": term.get("terminalName"),
            "recommendedFor": term.get("recommendedFor"),
        }
        for term in terminals
    ]
    asset = info.get("assetTypeName") or info.get("assetGroupName") or "device"
    message = (
        f"The starting feature ({asset}) has {len(terminals)} terminals, so a "
        f"terminal_id is required to run '{named_trace_name}'. Ask the user which "
        f"terminal to start the trace from, then call network_named_trace again "
        f"with that terminal_id."
    )
    if recommended_terminal_id is not None:
        message += (
            f" For this {trace_type} trace the '{preferred_direction}' terminal "
            f"(terminalId {recommended_terminal_id}) is the usual choice, but "
            f"confirm with the user."
        )
    return {
        "status": NEEDS_TERMINAL_SELECTION,
        "needs": "terminal_id",
        "namedTraceName": named_trace_name,
        "traceType": trace_type,
        "startingGlobalId": global_id,
        "device": {
            "assetGroupName": info.get("assetGroupName"),
            "assetTypeName": info.get("assetTypeName"),
            "usageType": info.get("usageType"),
        },
        "terminalOptions": options,
        "recommendedTerminalId": recommended_terminal_id,
        "message": message,
    }


# Status marker returned when the start feature does not belong to the tier the
# named trace is configured for (e.g. an HV/transmission device fed into a
# distribution trace). The agent should pick a start feature in the required tier.
INVALID_START_POINT = "invalid_start_point"


def _split_subnetwork_names(raw: Any) -> list[str]:
    """Split a SUBNETWORKNAME field value into individual subnetwork names.

    The field may hold one name, or several separated by commas / newlines when a
    feature participates in multiple subnetworks. 'Unknown' and blanks are dropped.
    """
    if not raw:
        return []
    parts = re.split(r"[,\n]", str(raw))
    return [p.strip() for p in parts if p.strip() and p.strip().lower() != "unknown"]


def _locate_feature_attrs(
    flc: FeatureLayerCollection,
    data_element: dict[str, Any],
    global_id: str,
    domain_network_name: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find a network feature by GlobalID by scanning the domain's sources by role.

    Rather than assume a layer name, this walks the utility network's
    ``junctionSources``/``edgeSources`` (each carries a ``layerId`` and a
    ``utilityNetworkFeatureClassUsageType`` role) and queries each source layer for
    the GlobalID. Works for devices, assemblies, junctions, and edges alike.

    Returns ``(domain, attrs)`` for the first source that contains the feature, or
    ``(None, None)`` when it is not found.
    """
    layers_by_id = {int(lyr.properties.id): lyr for lyr in flc.layers}
    where = f"globalid = {_quote([global_id.strip()])}"
    for domain in data_element.get("domainNetworks", []) or []:
        if domain_network_name and str(domain.get("domainNetworkName", "")).strip().lower() != str(domain_network_name).strip().lower():
            continue
        sources = (domain.get("junctionSources", []) or []) + (domain.get("edgeSources", []) or [])
        for source in sources:
            layer = layers_by_id.get(source.get("layerId"))
            if layer is None:
                continue
            feats = layer.query(where=where, out_fields="*", return_geometry=False).features
            if feats:
                return domain, {k.lower(): v for k, v in feats[0].attributes.items()}
    return None, None


def _validate_start_in_tier(
    gis: GIS,
    feature_service_url: str,
    global_id: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Verify the start feature belongs to the tier the named trace targets.

    A named trace's ``traceConfiguration`` declares the domain network and source
    tier it runs on (e.g. domain 'Electric', tier 'Electric Distribution'). A start
    feature only produces results when it participates in that tier's subnetworks;
    starting a distribution trace from a transmission device fails on the server
    with an opaque tier / subnetwork-controller error.

    The feature's own TIERNAME field is not populated, but its SUBNETWORKNAME maps
    to a tier via the domain's subnetwork line layer (identified by role through the
    domain's ``subnetworkLayerId``), whose TIERNAME is a tier rank. This resolves
    the start feature's tier rank(s) and compares them to the trace's target rank.

    Feature and layer discovery are role-based (utility network sources +
    ``subnetworkLayerId``), not name-based, so the check works regardless of how the
    layers are named.

    Returns ``None`` when the feature is valid for the tier OR when membership
    cannot be determined (fail-open, so the trace still runs and the server has the
    final say). Returns a structured ``invalid_start_point`` response when the
    feature's subnetwork(s) are all in a different tier than the trace requires.
    """
    trace_cfg = config.get("traceConfiguration") or {}
    domain_name = trace_cfg.get("domainNetworkName")
    tier_name = trace_cfg.get("sourceTierName") or trace_cfg.get("tierName")
    if not tier_name:
        return None  # trace is not tier-scoped; nothing to validate

    try:
        flc = FeatureLayerCollection(feature_service_url.rstrip("/"), gis=gis)
        data_element = _un_data_element(flc)

        # Resolve the trace's target domain network (by name) and its tiers.
        target_domain = next(
            (
                d for d in data_element.get("domainNetworks", []) or []
                if not domain_name
                or str(d.get("domainNetworkName", "")).strip().lower() == str(domain_name).strip().lower()
            ),
            None,
        )
        if target_domain is None:
            return None  # can't resolve target domain; don't block
        rank_by_name: dict[str, int] = {}
        name_by_rank: dict[int, str] = {}
        for tier in target_domain.get("tiers", []) or []:
            rank, name = tier.get("rank"), tier.get("name")
            if rank is None or name is None:
                continue
            rank_by_name[str(name).strip().lower()] = rank
            name_by_rank[rank] = name
        target_rank = rank_by_name.get(str(tier_name).strip().lower())
        if target_rank is None:
            return None  # can't resolve target tier rank; don't block

        # Locate the start feature across the domain's sources (role-based) and read
        # its subnetwork membership. If it is not found, skip (fail-open).
        _, attrs = _locate_feature_attrs(
            flc, data_element, global_id, target_domain.get("domainNetworkName")
        )
        if not attrs:
            return None
        subnetwork_names = _split_subnetwork_names(attrs.get("subnetworkname"))
        if not subnetwork_names:
            return None  # membership unknown; don't block

        # The subnetwork line layer is identified by the domain's subnetworkLayerId
        # (its role), not by a hardcoded layer name.
        subnetwork_layer_id = target_domain.get("subnetworkLayerId")
        if subnetwork_layer_id is None or subnetwork_layer_id < 0:
            return None
        layers_by_id = {int(lyr.properties.id): lyr for lyr in flc.layers}
        subnet_layer = layers_by_id.get(int(subnetwork_layer_id))
        if subnet_layer is None:
            return None
        rows = subnet_layer.query(
            where=f"SUBNETWORKNAME IN ({_quote(subnetwork_names)})",
            out_fields="SUBNETWORKNAME,TIERNAME",
            return_geometry=False,
        ).features
        feature_ranks = {
            r.attributes.get("TIERNAME")
            for r in rows
            if r.attributes.get("TIERNAME") is not None
        }
        if not feature_ranks:
            return None  # no subnetwork rows resolved; don't block
        if target_rank in feature_ranks:
            return None  # valid: feature participates in the trace's tier

        feature_tier_names = sorted(
            name_by_rank.get(r, f"rank {r}") for r in feature_ranks
        )
        asset_id = attrs.get("assetid") or global_id
        return {
            "status": INVALID_START_POINT,
            "reason": "tier_mismatch",
            "namedTraceName": config.get("title") or config.get("name"),
            "startingGlobalId": global_id,
            "requiredTier": tier_name,
            "featureSubnetworks": subnetwork_names,
            "featureTiers": feature_tier_names,
            "message": (
                f"Start feature {asset_id} is in subnetwork(s) {subnetwork_names}, "
                f"which belong to tier {feature_tier_names}, but the named trace "
                f"'{config.get('title') or config.get('name')}' runs on the "
                f"'{tier_name}' tier. Pick a start feature that participates in the "
                f"'{tier_name}' tier (for a distribution trace, a medium-voltage "
                f"distribution device such as an MV transformer — not a high-voltage "
                f"station transformer)."
            ),
        }
    except Exception as exc:  # noqa: BLE001 - never block a trace on a precheck failure
        logger.warning(
            "Tier precheck for %s failed (%s); proceeding without validation.",
            global_id, exc,
        )
        return None


def _trace_response(
    trace_type: str,
    network_service_url: str,
    global_id: str,
    raw: dict[str, Any],
    *,
    named_trace_name: str | None = None,
) -> dict[str, Any]:
    if raw.get("success") is False:
        raise RuntimeError(f"Trace failed: {raw.get('error', raw)}")
    response: dict[str, Any] = {
        "traceType": trace_type,
        "networkServiceUrl": network_service_url,
        "startingGlobalId": global_id,
        "traceResults": raw.get("traceResults", raw),
    }
    if named_trace_name:
        response["namedTraceName"] = named_trace_name
    return response





@utilitynetwork_router.tool(name="network_downstream_trace")
async def network_downstream_trace(
    starting_global_id: str,
    network_service_url: str | None = None,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    terminal_id: int | None = None,
    percent_along: float | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Execute a downstream trace on the utility network from a starting feature global ID.

    Calls the UN trace REST endpoint directly with traceType="downstream".
    No named/persisted trace configuration is used.

    - For junction features, supply terminal_id to identify the correct terminal.
    - For edge features, supply percent_along (0.0–1.0) to locate the starting
      point along the edge.
    - Omitting both works when the feature has a single terminal.
    - Provide domain_network_name and tier_name to scope the trace to a specific
      domain network and tier; omitting them uses the server defaults.
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    gis = _connect_gis(token)
    raw = await asyncio.to_thread(
        run_trace,
        gis,
        service_url,
        "downstream",
        starting_global_id,
        domain_network_name,
        tier_name,
        terminal_id,
        percent_along,
        service_url,  # feature_service_url for terminal auto-detection
    )
    return _trace_response("downstream", service_url, starting_global_id, raw)


@utilitynetwork_router.tool(name="network_upstream_trace")
async def network_upstream_trace(
    starting_global_id: str,
    network_service_url: str | None = None,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    terminal_id: int | None = None,
    percent_along: float | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Execute an upstream trace on the utility network from a starting feature global ID.

    Calls the UN trace REST endpoint directly with traceType="upstream".
    No named/persisted trace configuration is used.

    - For junction features, supply terminal_id to identify the correct terminal.
    - For edge features, supply percent_along (0.0–1.0) to locate the starting
      point along the edge.
    - Omitting both works when the feature has a single terminal.
    - Provide domain_network_name and tier_name to scope the trace to a specific
      domain network and tier; omitting them uses the server defaults.
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    gis = _connect_gis(token)
    raw = await asyncio.to_thread(
        run_trace,
        gis,
        service_url,
        "upstream",
        starting_global_id,
        domain_network_name,
        tier_name,
        terminal_id,
        percent_along,
        service_url,  # feature_service_url for terminal auto-detection
    )
    return _trace_response("upstream", service_url, starting_global_id, raw)


@utilitynetwork_router.tool(name="network_named_trace")
async def network_named_trace(
    named_trace_name: str,
    starting_global_id: str,
    trace_type: str | None = None,
    terminal_id: int | None = None,
) -> dict[str, Any]:
    """Run a named (persisted) trace configuration on the utility network.

    A named trace is a pre-configured trace saved on the server that encapsulates
    a specific trace algorithm along with its barriers, conditions, output filters,
    and result types. This tool executes that saved configuration from a starting
    feature and returns the raw trace results.

    This is a thin passthrough to the ArcGIS Utility Network trace endpoint. It
    resolves the named trace configuration by name, builds a starting point from
    ``starting_global_id`` (plus ``terminal_id`` when provided), runs the trace, and
    returns the result. It applies no domain rules of its own — start-feature
    selection, tier/terminal decisions, and any workflow logic are the caller's
    responsibility. Use ``network_list_named_traces`` to discover valid names.

    Returns a dict with keys:
    - ``traceType``          — the trace type that was executed.
    - ``networkServiceUrl``  — the utility network service URL.
    - ``startingGlobalId``   — the GlobalID of the starting feature.
    - ``namedTraceName``     — the name of the persisted trace configuration used.
    - ``traceResults``       — the raw trace output from the server. On a successful
      run this is a dict whose most useful keys are:
        - ``elements``: list of the features the trace returned. Each element is a
          dict with ``networkSourceId`` (int), ``globalId`` (GUID str), ``objectId``
          (int), ``terminalId`` (int), ``assetGroupCode`` (int), and
          ``assetTypeCode`` (int). This is the primary result the caller consumes.
        - ``sourceMapping``: dict mapping the string form of each ``networkSourceId``
          to its layer/source name (e.g. ``"9" -> "ElectricDevice"``). Use it to turn
          an element's ``networkSourceId`` into a layer so it can be looked up or shown.
        - ``globalFunctionResults``: list of aggregated function outputs (e.g. sums or
          counts the named trace was configured to compute), each with
          ``functionType``, ``networkAttributeName``, ``result``, and ``conditions``.
        - ``warnings``: list of server warnings (empty when none).
      An empty ``elements`` list means the trace ran but found nothing to return.

    Args:
        named_trace_name: Exact name of the persisted trace configuration to run.
            Case-sensitive; must match a name returned by ``network_list_named_traces``.
        starting_global_id: GlobalID (GUID) of the network feature to start from,
            e.g. ``'{12345678-ABCD-...}'``. Any traceable network feature is accepted.
        trace_type: Optional trace algorithm override. Leave unset (``None``) to use
            the direction saved on the named trace configuration. Accepted values
            include ``'connected'``, ``'upstream'``, ``'downstream'``, ``'subnetwork'``,
            ``'subnetworkController'``, ``'loops'``, ``'shortestPath'``, ``'isolation'``.
        terminal_id: Integer terminal ID of the starting feature's terminal to
            trace from.
    """
    network_service_url = os.getenv("UTILITY_NETWORK_URL")
    token = os.getenv("ARCGIS_TOKEN")
    gis = _connect_gis(token)
    raw = await asyncio.to_thread(
        run_named_trace,
        gis,
        network_service_url,
        named_trace_name,
        starting_global_id,
        trace_type,
        terminal_id,
    )
    # A multi-terminal start feature returns a structured terminal-selection prompt
    # instead of trace results; pass it through untouched so the agent can ask the
    # user which terminal to use.
    # --- DISABLED (2026-07-09): structured status passthrough. The MCP is now a
    # thin passthrough; start-feature/terminal handling lives in the frontend skill.
    # if isinstance(raw, dict) and raw.get("status") in (
    #     NEEDS_TERMINAL_SELECTION,
    #     INVALID_START_POINT,
    # ):
    #     return raw
    return _trace_response(
        "named",
        network_service_url,
        starting_global_id,
        raw,
        named_trace_name=named_trace_name,
    )


@utilitynetwork_router.tool(name="network_list_named_traces")
async def network_list_named_traces(
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """List all named (persisted) trace configurations available on the utility network.

    Returns each configuration's name, globalId, description, trace type, and creator.
    Use this tool to discover which named traces exist before running one with
    ``network_named_trace``.

    The ``traceType`` field is important: it is the direction/algorithm the named
    trace was saved with (e.g. ``'downstream'``, ``'upstream'``, ``'subnetwork'``).
    You normally do NOT need to pass ``trace_type`` to ``network_named_trace`` — it
    reuses this persisted value — but the direction tells you which terminal to
    start from on a multi-terminal device (downstream → downstream/low-side terminal,
    upstream → upstream/high-side terminal).  See ``network_device_terminals``.
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    resolved_token = token or os.getenv("ARCGIS_TOKEN")
    gis = _connect_gis(resolved_token)

    def _query() -> dict[str, Any]:
        un_manager = UtilityNetworkManager(_utility_network_url(service_url), gis=gis)
        result = un_manager.trace_configurations().query()
        configs = result.get("traceConfigurations", [])
        traces = [
            {
                "name": cfg.get("title") or cfg.get("name", ""),
                "globalId": cfg.get("globalId", ""),
                "description": cfg.get("description", ""),
                "traceType": cfg.get("traceType", ""),
                "createdBy": cfg.get("createdBy", ""),
            }
            for cfg in configs
        ]
        return {"namedTraces": traces, "count": len(traces)}

    return await asyncio.to_thread(_query)


@utilitynetwork_router.tool(name="query_customer_data")
async def query_customer_data(
    global_ids: list[str],
    meter_ids: list[str] | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Query CIS_CUST_VIEW by meter_ids, or resolve meter_ids from ElectricDevice global_ids."""
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    gis = _connect_gis(token)
    return await asyncio.to_thread(get_customer_data, gis, service_url, global_ids, meter_ids)


@utilitynetwork_router.tool(name="network_device_terminals")
async def network_device_terminals(
    global_id: str,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Get the terminal ID(s) and their names for a network feature by GlobalID.

    Utility network junction features (e.g. transformers, switches, fuses) can
    have multiple terminals — distinct connection points such as a high-side and
    a low-side.  Direction-sensitive traces started from such features require a
    ``terminal_id`` to know which side to begin from.  This tool resolves the valid
    terminals for a given feature so you can pick the correct ``terminal_id`` before
    calling ``network_named_trace`` (or another trace tool).

    Choosing the terminal by trace direction:
    - Downstream traces (e.g. Balanced Distribution Transformer Load and Count,
      Downstream Service Point) start on the DOWNSTREAM terminal — the secondary /
      low side / line side, where ``isUpstreamTerminal`` is ``False`` and
      ``recommendedFor`` is ``'downstream'``.
    - Upstream / isolation traces (e.g. Distribution Isolation) start on the
      UPSTREAM terminal — the primary / high side / source side, where
      ``isUpstreamTerminal`` is ``True`` and ``recommendedFor`` is ``'upstream'``.
    - If more than one terminal matches the needed direction, or the direction is
      unclear, DO NOT guess: present the terminal list to the user and let them
      choose (in the client, this can be a selection on the map).

    How it works:
    1. Loads the utility network data model (domain networks, sources, asset
       groups/types, and terminal configurations).
    2. Locates the feature by GlobalID across the network's source layers to read
       its asset group and asset type.
    3. Maps that asset type to its terminal configuration and returns the
       terminals it defines, plus the source's role (``usageType``/``isDevice``).

    Returns a dict with keys:
    - ``globalId``                    — the GlobalID that was resolved.
    - ``domainNetworkName``           — the domain network the feature belongs to.
    - ``sourceType``                  — ``'junction'`` or ``'edge'``.
    - ``layerId``                     — the feature service layer ID of the feature.
    - ``usageType``                   — the source's utility network feature-class usage
      type (e.g. ``'esriUNFCUTDevice'`` for devices).
    - ``isDevice``                    — ``True`` when ``usageType == 'esriUNFCUTDevice'``.
      Distribution and isolation trace start points must be devices.
    - ``assetGroupCode`` / ``assetGroupName`` — the feature's asset group.
    - ``assetTypeCode`` / ``assetTypeName``   — the feature's asset type.
    - ``terminalConfigurationId`` / ``terminalConfigurationName`` — the terminal
      configuration the asset type uses.
    - ``terminals``                   — list of ``{terminalId, terminalName,
      isUpstreamTerminal, recommendedFor}``.  Single-terminal features return one
      entry; edge or simple-junction features may return an empty list.
    - ``terminalCount``               — number of terminals.
    - ``subnetworkName`` / ``subnetworkNames`` — the feature's raw subnetwork field
      value and the split list of subnetwork names it participates in. This is the
      link between the feature and its tier.
    - ``tiers``                       — the domain's tier catalog: a list of
      ``{tierId, name, rank, tierGroupName}``. ``rank`` separates higher tiers (e.g.
      transmission) from lower ones (e.g. distribution).
    - ``featureTierNames`` / ``featureTierRanks`` — the tier(s) the feature actually
      belongs to, resolved by joining its subnetwork membership through the domain's
      subnetwork line layer. Empty when membership can't be resolved; in that case
      use ``subnetworkNames`` + ``tiers`` to reason about the tier.

    Determining the tier: match ``featureTierNames`` when present. If it is empty,
    the feature's ``subnetworkNames`` combined with the ``tiers`` catalog tells you
    which tier(s) apply.

    Args:
        global_id: GlobalID (GUID) of the network feature, e.g.
            ``'{12345678-ABCD-...}'``.
        network_service_url: FeatureServer URL of the utility network.  Falls back
            to the ``UTILITY_NETWORK_URL`` environment variable when omitted.
        token: Optional ArcGIS token.  Falls back to the configured/default token.
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    gis = _connect_gis(token)
    return await asyncio.to_thread(get_device_terminals, gis, service_url, global_id)
