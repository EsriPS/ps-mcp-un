"""ArcGIS Utility Network router plugin for PS-MCP.

Single service file containing all tools, resources, prompts, and internal helpers
for the utility network router. Consolidates functionality previously split across
metadata.py, associations.py, domain_resolver.py, formatting.py, traces.py,
prompts.py, and resources.py.
"""

import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from arcgis.features import FeatureLayer, FeatureLayerCollection
from arcgis.features._utility import UtilityNetworkManager
from arcgis.gis import GIS
from dotenv import load_dotenv
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

load_dotenv()

logger = logging.getLogger(__name__)

utilitynetwork_router = FastMCP(name="Utility Network Service")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() != "false"

_PII_FIELDS = {"full_name", "phone_number", "billing_address"}

# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------

# Data element cache (from metadata.py)
_cached_data_element: dict[str, Any] | None = None
_cached_service_url: str | None = None

# Layer metadata cache (from domain_resolver.py)
_cached_layer_metadata: dict[str, dict[str, Any]] = {}

# Mapping from user-facing association type names to the integer codes used by the
# ArcGIS associations/query REST endpoint.
_ASSOCIATION_TYPE_CODES: dict[str, int] = {
    "connectivity": 1,
    "containment": 2,
    "structural attachment": 3,
    "structuralattachment": 3,
    "structural_attachment": 3,
}

# Reverse mapping: integer code -> human-readable name.
_ASSOCIATION_TYPE_NAMES: dict[int, str] = {
    1: "connectivity",
    2: "containment",
    3: "structuralAttachment",
}

# Accepted trace types for the generic trace tool
_ACCEPTED_TRACE_TYPES = frozenset(
    {"isolation", "connected", "subnetwork", "subnetworkController", "loops", "shortestPath"}
)

# Fallback phase labels — the common Esri convention. Used ONLY when the caller
# does not provide a phase_domain resolved from the data element.
_DEFAULT_PHASE_LABELS: dict[int, str] = {
    7: "ABC",
    6: "AB",
    5: "AC",
    4: "A",
    3: "BC",
    2: "B",
    1: "C",
    0: "None",
}

# Maps a trace's persisted ``traceType`` to the terminal direction a device should
# start from.
_TRACE_TYPE_TERMINAL_DIRECTION = {
    "downstream": "downstream",
    "upstream": "upstream",
    "isolation": "upstream",
}

# Status markers
NEEDS_TERMINAL_SELECTION = "needs_terminal_selection"
INVALID_START_POINT = "invalid_start_point"

_NO_STARTING_POINTS = -2147208614  # extendedCode for "No starting points found."

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Core helpers (GIS connection, URL building, starting points)
# ---------------------------------------------------------------------------


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
            print(
                f"  Matched source: '{src['name']}'  "
                f"(sourceId={src['sourceId']}, type={src['sourceType']})"
            )
            return src["name"]
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
    gis = GIS(url=ARCGIS_PORTAL_URL, **kwargs) if ARCGIS_PORTAL_URL else GIS(**kwargs)
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
    """Build a traceLocations starting-point entry."""
    loc: dict[str, Any] = {
        "traceLocationType": "startingPoint",
        "globalId": global_id,
    }
    if terminal_id is not None:
        loc["terminalId"] = terminal_id
    if percent_along is not None:
        loc["percentAlong"] = percent_along
    return [loc]


def _quote(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _find_layer(gis: GIS, service_url: str, name: str) -> FeatureLayer:
    flc = FeatureLayerCollection(service_url.rstrip("/"), gis=gis)
    target = name.lower()
    for group in (flc.layers, flc.tables):
        for layer in group:
            if layer.properties.name.lower() == target:
                return layer
    raise ValueError(f"Layer or table '{name}' not found.")


# ---------------------------------------------------------------------------
# Data element helpers (from metadata.py)
# ---------------------------------------------------------------------------


def _get_data_element(service_url: str, token: str | None = None) -> dict[str, Any]:
    """Return the utility network data element, caching it across calls."""
    global _cached_data_element, _cached_service_url
    if _cached_data_element is not None and _cached_service_url == service_url:
        logger.debug("_get_data_element: cache hit for %s", service_url)
        return _cached_data_element
    logger.info("_get_data_element: fetching data element for %s", service_url)
    gis = _connect_gis(token)
    flc = FeatureLayerCollection(service_url.rstrip("/"), gis=gis)
    _cached_data_element = _un_data_element(flc)
    _cached_service_url = service_url
    return _cached_data_element


def _invalidate_data_element_cache() -> None:
    """Reset the module-level data element cache."""
    global _cached_data_element, _cached_service_url
    logger.info("_invalidate_data_element_cache: clearing cached data element")
    _cached_data_element = None
    _cached_service_url = None


def _un_data_element(flc: FeatureLayerCollection) -> dict[str, Any]:
    """Return the utility network data element (schema) from a FeatureServer."""
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
        un_layer_id,
        time.perf_counter() - started,
    )
    elements = result.get("layerDataElements") if isinstance(result, dict) else None
    if not elements:
        raise ValueError("queryDataElements returned no utility network data element.")
    data_element = elements[0].get("dataElement", {})
    if not data_element:
        raise ValueError("Utility network data element is empty.")
    return data_element


# ---------------------------------------------------------------------------
# Association helpers (from associations.py)
# ---------------------------------------------------------------------------


def _build_source_lookup(data_element: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Build a lookup from networkSourceId to source metadata."""
    lookup: dict[int, dict[str, Any]] = {}

    for dn in data_element.get("domainNetworks", []):
        all_sources = [
            *[(s, "junction") for s in dn.get("junctionSources", [])],
            *[(s, "edge") for s in dn.get("edgeSources", [])],
        ]
        for source, source_type in all_sources:
            source_id = source.get("sourceId")
            if source_id is None:
                continue
            asset_groups: dict[int, dict[str, Any]] = {}
            for grp in source.get("assetGroups", []):
                grp_code = grp.get("assetGroupCode")
                if grp_code is None:
                    continue
                asset_types: dict[int, str] = {}
                for at in grp.get("assetTypes", []):
                    at_code = at.get("assetTypeCode")
                    if at_code is not None:
                        asset_types[at_code] = at.get("assetTypeName", "")
                asset_groups[grp_code] = {
                    "assetGroupName": grp.get("assetGroupName", ""),
                    "assetTypes": asset_types,
                }
            lookup[source_id] = {
                "sourceName": source.get("name", ""),
                "sourceType": source_type,
                "domainNetworkName": dn.get("domainNetworkName", ""),
                "assetGroups": asset_groups,
            }

    return lookup


def _build_terminal_lookup(data_element: dict[str, Any]) -> dict[int, str]:
    """Build a flat terminalId -> terminalName lookup across all configurations."""
    flat: dict[int, str] = {}
    for cfg in data_element.get("terminalConfigurations", []):
        for term in cfg.get("terminals", []):
            tid = term.get("terminalId")
            if tid is not None:
                flat[tid] = term.get("terminalName", f"Terminal {tid}")
    return flat


def _resolve_feature_identity(
    record: dict[str, Any],
    prefix: str,
    source_lookup: dict[int, dict[str, Any]],
    terminal_lookup: dict[int, str],
) -> dict[str, Any]:
    """Resolve numeric codes in an association record to names."""
    source_id = record.get(f"{prefix}NetworkSourceId")
    asset_group_code = record.get(f"{prefix}AssetGroupCode")
    asset_type_code = record.get(f"{prefix}AssetTypeCode")
    terminal_id = record.get(f"{prefix}TerminalId")
    global_id = record.get(f"{prefix}GlobalId")

    source_info = source_lookup.get(source_id, {})
    source_name = source_info.get("sourceName", "")

    asset_group_name = ""
    asset_type_name = ""
    asset_groups = source_info.get("assetGroups", {})
    if asset_group_code is not None:
        grp_info = asset_groups.get(asset_group_code, {})
        asset_group_name = grp_info.get("assetGroupName", "")
        if asset_type_code is not None:
            asset_type_name = grp_info.get("assetTypes", {}).get(asset_type_code, "")

    terminal_name = ""
    if terminal_id is not None:
        terminal_name = terminal_lookup.get(terminal_id, f"Terminal {terminal_id}")

    identity: dict[str, Any] = {
        "globalId": global_id,
        "networkSourceId": source_id,
        "sourceName": source_name,
        "assetGroupCode": asset_group_code,
        "assetGroupName": asset_group_name,
        "assetTypeCode": asset_type_code,
        "assetTypeName": asset_type_name,
    }

    if terminal_id is not None:
        identity["terminalId"] = terminal_id
        identity["terminalName"] = terminal_name

    return identity


# ---------------------------------------------------------------------------
# Trace enrichment helper (from traces.py)
# ---------------------------------------------------------------------------


def _enrich_trace_elements(
    raw: dict[str, Any], service_url: str, token: str | None
) -> dict[str, Any]:
    """Resolve numeric codes in trace elements to human-readable names.

    Mutates and returns the raw trace results dict, adding ``sourceName``,
    ``assetGroupName``, and ``assetTypeName`` fields to each element.
    """
    trace_results = raw.get("traceResults", raw)
    elements = trace_results.get("elements")
    if not elements:
        return raw

    data_element = _get_data_element(service_url, token)
    source_lookup = _build_source_lookup(data_element)

    for elem in elements:
        source_id = elem.get("networkSourceId")
        source_info = source_lookup.get(source_id, {})

        elem["sourceName"] = source_info.get("sourceName", "")

        asset_group_code = elem.get("assetGroupCode")
        asset_groups = source_info.get("assetGroups", {})
        group_info = asset_groups.get(asset_group_code, {})

        elem["assetGroupName"] = group_info.get("assetGroupName", "")

        asset_type_code = elem.get("assetTypeCode")
        asset_types_map = group_info.get("assetTypes", {})
        elem["assetTypeName"] = asset_types_map.get(asset_type_code, "")

    return raw


# ---------------------------------------------------------------------------
# Domain resolver helpers (from domain_resolver.py)
# ---------------------------------------------------------------------------


def _invalidate_layer_metadata_cache(layer_url: str | None = None) -> None:
    """Clear cached layer metadata. If layer_url given, clear only that entry."""
    global _cached_layer_metadata
    if layer_url:
        _cached_layer_metadata.pop(layer_url, None)
    else:
        _cached_layer_metadata.clear()


async def _get_layer_metadata(layer_url: str, token: str | None = None) -> dict[str, Any]:
    """Fetch and cache layer metadata (fields, subtypes, domains)."""
    url = layer_url.rstrip("/")
    if url in _cached_layer_metadata:
        logger.debug("_get_layer_metadata: cache hit for %s", url)
        return _cached_layer_metadata[url]

    logger.info("_get_layer_metadata: fetching metadata for %s", url)
    resolved_token = resolve_token(token)
    params: dict[str, str] = {"f": "json"}
    if resolved_token:
        params["token"] = resolved_token

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=VERIFY_SSL) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            _cached_layer_metadata[url] = data
            return data
    except Exception as exc:
        logger.warning("_get_layer_metadata: failed to fetch %s: %s", url, exc)
        return {}


def _build_subtype_domain_lookup(
    layer_metadata: dict[str, Any],
) -> tuple[str | None, dict[int, dict[str, dict[int, str]]]]:
    """Build a lookup structure from layer metadata for domain resolution."""
    subtype_field = layer_metadata.get("subtypeField") or layer_metadata.get("typeIdField")
    types = layer_metadata.get("types", [])

    subtype_domains: dict[int, dict[str, dict[int, str]]] = {}

    for subtype in types:
        subtype_id = subtype.get("id")
        if subtype_id is None:
            continue
        domains = subtype.get("domains", {})
        field_domains: dict[str, dict[int, str]] = {}
        for field_name, domain_def in domains.items():
            if not isinstance(domain_def, dict):
                continue
            if domain_def.get("type") != "codedValue":
                continue
            coded_values = domain_def.get("codedValues", [])
            code_map: dict[int, str] = {}
            for cv in coded_values:
                code = cv.get("code")
                name = cv.get("name", "")
                if code is not None:
                    code_map[code] = name
            if code_map:
                field_domains[field_name] = code_map
        subtype_domains[subtype_id] = field_domains

    return subtype_field, subtype_domains


def _build_default_domain_lookup(
    layer_metadata: dict[str, Any],
) -> dict[str, dict[int, str]]:
    """Build a default (non-subtype-specific) domain lookup from field definitions."""
    fields = layer_metadata.get("fields", [])
    default_domains: dict[str, dict[int, str]] = {}

    for field in fields:
        domain = field.get("domain")
        if not domain or not isinstance(domain, dict):
            continue
        if domain.get("type") != "codedValue":
            continue
        field_name = field.get("name", "")
        coded_values = domain.get("codedValues", [])
        code_map: dict[int, str] = {}
        for cv in coded_values:
            code = cv.get("code")
            name = cv.get("name", "")
            if code is not None:
                code_map[code] = name
        if code_map and field_name:
            default_domains[field_name] = code_map

    return default_domains


def resolve_subtype_domains(
    features: list[dict[str, Any]],
    layer_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve coded values to labels using subtype-specific domains."""
    if not features or not layer_metadata:
        return features

    subtype_field, subtype_domains = _build_subtype_domain_lookup(layer_metadata)
    default_domains = _build_default_domain_lookup(layer_metadata)

    resolved_features: list[dict[str, Any]] = []

    for feature in features:
        resolved = dict(feature)  # shallow copy

        if subtype_field:
            subtype_value = feature.get(subtype_field)
            if subtype_value is None:
                for k, v in feature.items():
                    if k.lower() == subtype_field.lower():
                        subtype_value = v
                        break
            if subtype_value is not None:
                field_domains = subtype_domains.get(int(subtype_value))
                if field_domains is None:
                    logger.debug(
                        "resolve_subtype_domains: unknown subtype code %s, "
                        "falling back to default domains",
                        subtype_value,
                    )
                    field_domains = default_domains
            else:
                field_domains = default_domains
        else:
            field_domains = default_domains

        # Resolve coded values
        for field_name, code_map in field_domains.items():
            actual_key = None
            for k in feature:
                if k.lower() == field_name.lower():
                    actual_key = k
                    break
            if actual_key is None:
                continue

            raw_value = feature.get(actual_key)
            if raw_value is None:
                continue

            try:
                int_value = int(raw_value)
            except (ValueError, TypeError):
                continue

            label = code_map.get(int_value)
            if label is not None:
                resolved[actual_key] = {"code": int_value, "label": label}

        # Also apply default domains for fields not covered by subtype domains
        if subtype_field and default_domains:
            for field_name, code_map in default_domains.items():
                if field_name.lower() in {k.lower() for k in field_domains}:
                    continue
                actual_key = None
                for k in feature:
                    if k.lower() == field_name.lower():
                        actual_key = k
                        break
                if actual_key is None:
                    continue
                raw_value = feature.get(actual_key)
                if raw_value is None:
                    continue
                try:
                    int_value = int(raw_value)
                except (ValueError, TypeError):
                    continue
                label = code_map.get(int_value)
                if label is not None:
                    resolved[actual_key] = {"code": int_value, "label": label}

        resolved_features.append(resolved)

    return resolved_features


# ---------------------------------------------------------------------------
# Formatting helpers (from formatting.py)
# ---------------------------------------------------------------------------


def resolve_phase_domain(data_element: dict[str, Any]) -> dict[int, str] | None:
    """Extract the phase coded value domain from the utility network data element."""
    for attr in data_element.get("networkAttributes", []):
        domain = attr.get("domain")
        if domain is None:
            continue
        attr_name = (attr.get("name") or "").lower()
        if "phase" not in attr_name:
            continue
        coded_values = domain.get("codedValues")
        if not coded_values:
            continue
        phase_map: dict[int, str] = {}
        for cv in coded_values:
            code = cv.get("code")
            name = cv.get("name", "")
            if code is not None:
                phase_map[int(code)] = name
        if phase_map:
            return phase_map
    return None


def truncate_results(
    items: list[Any],
    limit: int = 100,
    label: str = "elements",
) -> dict[str, Any]:
    """Return first N items with a count note if truncated."""
    total = len(items)
    if total <= limit:
        return {
            "items": items,
            "total": total,
            "truncated": False,
        }
    return {
        "items": items[:limit],
        "total": total,
        "truncated": True,
        "note": f"showing {limit} of {total} {label}",
    }


def summarize_trace_results(
    raw_results: dict[str, Any],
    source_mapping: dict[str, str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Group trace elements by source/asset group, count, and highlight controllers."""
    trace_results = raw_results.get("traceResults", raw_results)
    elements = trace_results.get("elements", [])

    group_counts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for elem in elements:
        source_name = elem.get("sourceName", "")
        if not source_name and source_mapping:
            source_id = str(elem.get("networkSourceId", ""))
            source_name = source_mapping.get(source_id, "")
        if not source_name:
            code = elem.get("networkSourceId", "?")
            source_name = f"Unknown (code={code})"

        asset_group_name = elem.get("assetGroupName", "")
        if not asset_group_name:
            code = elem.get("assetGroupCode", "?")
            asset_group_name = f"Unknown (code={code})"

        group_counts[(source_name, asset_group_name)].append(elem)

    groups: list[dict[str, Any]] = []
    for (source_name, asset_group_name), group_elements in group_counts.items():
        type_counts: dict[str, int] = defaultdict(int)
        for elem in group_elements:
            asset_type_name = elem.get("assetTypeName", "")
            if not asset_type_name:
                code = elem.get("assetTypeCode", "?")
                asset_type_name = f"Unknown (code={code})"
            type_counts[asset_type_name] += 1

        asset_types = [
            {"name": name, "count": count}
            for name, count in sorted(type_counts.items(), key=lambda x: -x[1])
        ]

        groups.append(
            {
                "sourceName": source_name,
                "assetGroupName": asset_group_name,
                "count": len(group_elements),
                "assetTypes": asset_types,
            }
        )

    groups.sort(key=lambda g: -g["count"])

    controllers = [
        elem
        for elem in elements
        if "controller" in (elem.get("assetGroupName", "") or "").lower()
        or "controller" in (elem.get("assetTypeName", "") or "").lower()
    ]

    truncated_result = truncate_results(elements, limit=limit, label="elements")

    return {
        "totalElements": len(elements),
        "groups": groups,
        "controllers": controllers,
        "elements": truncated_result["items"],
        "truncated": truncated_result["truncated"],
        **({"note": truncated_result["note"]} if truncated_result["truncated"] else {}),
    }


def format_customer_impact(
    customers: list[dict[str, Any]],
    phases: dict[str, Any] | None = None,
    phase_domain: dict[int, str] | None = None,
    load_field: str | None = None,
    phase_field: str = "phase",
) -> dict[str, Any]:
    """Format customer impact data into a concise summary."""
    customer_count = len(customers)

    total_load = 0.0
    if load_field:
        for customer in customers:
            val = customer.get(load_field)
            if val is not None:
                total_load += float(val)

    if phases is not None:
        phase_breakdown = phases
    else:
        if phase_domain is not None:
            labels = phase_domain
        else:
            logger.warning(
                "format_customer_impact: no phase_domain provided; using default "
                "phase labels. Resolve from data element for accuracy."
            )
            labels = _DEFAULT_PHASE_LABELS

        phase_breakdown: dict[str, int] = defaultdict(int)
        for customer in customers:
            phase_val = customer.get(phase_field)
            if phase_val is not None:
                label = labels.get(int(phase_val), f"Unknown ({phase_val})")
                phase_breakdown[label] += 1
        phase_breakdown = dict(phase_breakdown)

    return {
        "customerCount": customer_count,
        "totalLoad": total_load,
        "phaseBreakdown": phase_breakdown,
        "customers": customers,
    }


# ---------------------------------------------------------------------------
# Metadata section parsers (from metadata.py)
# ---------------------------------------------------------------------------


def _parse_domain_networks(data_element: dict[str, Any], **_filters: Any) -> dict[str, Any]:
    """Parse domain networks with tiers, topology type, and tier groups."""
    raw_networks = data_element.get("domainNetworks", [])
    domain_networks: list[dict[str, Any]] = []

    for dn in raw_networks:
        tier_groups: list[dict[str, Any]] = []
        for tg in dn.get("tierGroups", []):
            tier_names = [t.get("name", "") for t in tg.get("tiers", [])]
            tier_groups.append({"name": tg.get("name", ""), "tierNames": tier_names})

        tiers: list[dict[str, Any]] = []
        for tier in dn.get("tiers", []):
            tiers.append(
                {
                    "tierId": tier.get("tierId"),
                    "name": tier.get("name", ""),
                    "rank": tier.get("rank"),
                    "tierGroupName": tier.get("tierGroupName", ""),
                    "topologyType": tier.get("topologyType", ""),
                    "subnetworkFieldName": tier.get("subnetworkFieldName", ""),
                }
            )

        domain_networks.append(
            {
                "domainNetworkName": dn.get("domainNetworkName", ""),
                "domainNetworkId": dn.get("domainNetworkId"),
                "tierDefinition": dn.get("tierDefinition", ""),
                "subnetworkTableName": dn.get("subnetworkTableName", ""),
                "tierGroups": tier_groups,
                "tiers": tiers,
            }
        )

    return {"domainNetworks": domain_networks, "count": len(domain_networks)}


def _parse_asset_types(data_element: dict[str, Any], **filters: Any) -> dict[str, Any]:
    """Parse asset groups/types with codes, categories, and terminal config IDs."""
    domain_network = filters.get("domain_network")
    source_name = filters.get("source_name")

    terminal_configs: dict[int, str] = {}
    for cfg in data_element.get("terminalConfigurations", []):
        cfg_id = cfg.get("terminalConfigurationId")
        cfg_name = cfg.get("terminalConfigurationName", "")
        if cfg_id is not None:
            terminal_configs[cfg_id] = cfg_name

    sources: list[dict[str, Any]] = []
    total_asset_groups = 0

    for dn in data_element.get("domainNetworks", []):
        dn_name = dn.get("domainNetworkName", "")
        if domain_network and dn_name.lower() != domain_network.lower():
            continue

        all_sources = [
            *[(s, "junction") for s in dn.get("junctionSources", [])],
            *[(s, "edge") for s in dn.get("edgeSources", [])],
        ]

        for source, source_type in all_sources:
            src_name = source.get("name", "")
            # Filter by source_name if provided
            if source_name:
                # First try exact match on source name
                if src_name and src_name.lower() == source_name.lower():
                    pass  # matches, keep it
                elif not src_name:
                    # Source has no name — check if any asset group name contains the filter term
                    has_matching_group = any(
                        source_name.lower() in (grp.get("assetGroupName") or "").lower()
                        for grp in source.get("assetGroups", [])
                    )
                    if not has_matching_group:
                        continue
                else:
                    continue

            asset_groups: list[dict[str, Any]] = []
            for grp in source.get("assetGroups", []):
                asset_types_list: list[dict[str, Any]] = []
                for at in grp.get("assetTypes", []):
                    tc_id = at.get("terminalConfigurationId")
                    asset_type_entry: dict[str, Any] = {
                        "assetTypeCode": at.get("assetTypeCode"),
                        "assetTypeName": at.get("assetTypeName", ""),
                        "categories": at.get("categories", []),
                    }
                    if tc_id is not None:
                        asset_type_entry["terminalConfigurationId"] = tc_id
                        asset_type_entry["terminalConfigurationName"] = terminal_configs.get(
                            tc_id, ""
                        )
                    asset_types_list.append(asset_type_entry)

                asset_groups.append(
                    {
                        "assetGroupCode": grp.get("assetGroupCode"),
                        "assetGroupName": grp.get("assetGroupName", ""),
                        "assetTypes": asset_types_list,
                    }
                )

            total_asset_groups += len(asset_groups)
            sources.append(
                {
                    "domainNetworkName": dn_name,
                    "sourceName": src_name,
                    "sourceType": source_type,
                    "assetGroups": asset_groups,
                }
            )

    return {"sources": sources, "totalAssetGroups": total_asset_groups}


def _parse_network_attributes(data_element: dict[str, Any], **_filters: Any) -> dict[str, Any]:
    """Parse network attributes with data type, domain, and usage type."""
    raw_attrs = data_element.get("networkAttributes", [])
    attributes: list[dict[str, Any]] = []

    for attr in raw_attrs:
        domain = attr.get("domain")
        domain_name: str | None = None
        if domain is not None:
            domain_name = domain.get("domainName", None)

        attributes.append(
            {
                "networkAttributeId": attr.get("networkAttributeId"),
                "name": attr.get("name", ""),
                "dataType": attr.get("dataType", ""),
                "domainName": domain_name,
                "usageType": attr.get("usageType", ""),
                "isApportionable": attr.get("isApportionable", False),
            }
        )

    return {"networkAttributes": attributes, "count": len(attributes)}


def _parse_terminal_configurations(data_element: dict[str, Any], **_filters: Any) -> dict[str, Any]:
    """Parse terminal configurations with names, paths, and direction."""
    raw_configs = data_element.get("terminalConfigurations", [])
    configs: list[dict[str, Any]] = []

    for cfg in raw_configs:
        terminals: list[dict[str, Any]] = []
        for term in cfg.get("terminals", []):
            terminals.append(
                {
                    "terminalId": term.get("terminalId"),
                    "terminalName": term.get("terminalName", ""),
                    "isUpstreamTerminal": term.get("isUpstreamTerminal", False),
                }
            )

        config_entry: dict[str, Any] = {
            "terminalConfigurationId": cfg.get("terminalConfigurationId"),
            "terminalConfigurationName": cfg.get("terminalConfigurationName", ""),
            "terminals": terminals,
            "traversabilityModel": cfg.get("traversabilityModel", ""),
        }

        raw_paths = cfg.get("terminalPaths")
        if raw_paths is not None:
            terminal_paths: list[dict[str, Any]] = []
            for path in raw_paths:
                terminal_paths.append(
                    {
                        "id": path.get("id"),
                        "name": path.get("name", ""),
                        "fromTerminalId": path.get("fromTerminalId"),
                        "toTerminalId": path.get("toTerminalId"),
                        "isDefaultPath": path.get("isDefaultPath", False),
                    }
                )
            config_entry["terminalPaths"] = terminal_paths

        configs.append(config_entry)

    return {"terminalConfigurations": configs, "count": len(configs)}


def _parse_categories(data_element: dict[str, Any], **_filters: Any) -> dict[str, Any]:
    """Parse categories with their member asset types."""
    category_members: dict[str, list[dict[str, Any]]] = {}

    for cat in data_element.get("categories", []):
        cat_name = cat.get("name", "")
        if cat_name:
            category_members[cat_name] = []

    for dn in data_element.get("domainNetworks", []):
        dn_name = dn.get("domainNetworkName", "")
        all_sources = [
            *dn.get("junctionSources", []),
            *dn.get("edgeSources", []),
        ]
        for source in all_sources:
            src_name = source.get("name", "")
            for grp in source.get("assetGroups", []):
                grp_name = grp.get("assetGroupName", "")
                for at in grp.get("assetTypes", []):
                    at_categories = at.get("categories", [])
                    for cat_name in at_categories:
                        if cat_name not in category_members:
                            category_members[cat_name] = []
                        category_members[cat_name].append(
                            {
                                "domainNetworkName": dn_name,
                                "sourceName": src_name,
                                "assetGroupName": grp_name,
                                "assetTypeName": at.get("assetTypeName", ""),
                                "assetTypeCode": at.get("assetTypeCode"),
                            }
                        )

    categories: list[dict[str, Any]] = []
    for cat_name, members in category_members.items():
        categories.append({"name": cat_name, "memberAssetTypes": members})

    return {"categories": categories, "count": len(categories)}


def _parse_topology_rules(data_element: dict[str, Any], **_filters: Any) -> dict[str, Any]:
    """Parse connectivity and association rules from the data element."""
    rules: list[dict[str, Any]] = []
    for dn in data_element.get("domainNetworks", []):
        dn_name = dn.get("domainNetworkName", "")
        all_sources = [
            *dn.get("junctionSources", []),
            *dn.get("edgeSources", []),
        ]
        for source in all_sources:
            src_name = source.get("name", "")
            for rule in source.get("connectivityRules", []):
                rules.append(
                    {
                        "domainNetworkName": dn_name,
                        "sourceName": src_name,
                        "ruleType": rule.get("type", ""),
                        "fromAssetGroupCode": rule.get("fromAssetGroupCode"),
                        "fromAssetTypeCode": rule.get("fromAssetTypeCode"),
                        "fromTerminalId": rule.get("fromTerminalId"),
                        "toAssetGroupCode": rule.get("toAssetGroupCode"),
                        "toAssetTypeCode": rule.get("toAssetTypeCode"),
                        "toTerminalId": rule.get("toTerminalId"),
                        "viaNetworkSourceId": rule.get("viaNetworkSourceId"),
                        "viaAssetGroupCode": rule.get("viaAssetGroupCode"),
                        "viaAssetTypeCode": rule.get("viaAssetTypeCode"),
                    }
                )
    return {"topologyRules": rules, "count": len(rules)}


def _parse_propagators(data_element: dict[str, Any], **_filters: Any) -> dict[str, Any]:
    """Parse network attribute propagators from the data element."""
    propagators: list[dict[str, Any]] = []
    for dn in data_element.get("domainNetworks", []):
        dn_name = dn.get("domainNetworkName", "")
        for tier in dn.get("tiers", []):
            tier_name = tier.get("name", "")
            for prop in tier.get("propagators", []):
                propagators.append(
                    {
                        "domainNetworkName": dn_name,
                        "tierName": tier_name,
                        "networkAttributeName": prop.get("networkAttributeName", ""),
                        "propagatorFunctionType": prop.get("propagatorFunctionType", ""),
                        "operator": prop.get("operator", ""),
                        "value": prop.get("value"),
                        "substitutionAttributeName": prop.get("substitutionAttributeName", ""),
                    }
                )
    return {"propagators": propagators, "count": len(propagators)}


_SECTION_PARSERS: dict[str, Callable[..., dict[str, Any]]] = {
    "domain_networks": _parse_domain_networks,
    "asset_types": _parse_asset_types,
    "network_attributes": _parse_network_attributes,
    "terminal_configurations": _parse_terminal_configurations,
    "categories": _parse_categories,
    "topology_rules": _parse_topology_rules,
    "propagators": _parse_propagators,
}


# ---------------------------------------------------------------------------
# Prompt/skill helpers (from prompts.py)
# ---------------------------------------------------------------------------


def _read_skill(filename: str) -> str:
    """Read a skill file from the skills directory."""
    skill_path = _SKILLS_DIR / filename
    if not skill_path.exists():
        logger.error("Skill file not found: %s", skill_path)
        raise FileNotFoundError(f"Skill file not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Named trace helpers
# ---------------------------------------------------------------------------


def _strip_trace_suffix(name: str) -> str:
    """Normalize a named-trace name for forgiving comparison."""
    normalized = " ".join(name.strip().lower().split())
    if normalized.endswith(" trace"):
        normalized = normalized[: -len(" trace")]
    elif normalized == "trace":
        normalized = ""
    return normalized


def _named_trace_config(un_manager: UtilityNetworkManager, named_trace_name: str) -> dict[str, Any]:
    """Look up a named trace configuration by name and return its full record."""
    result = un_manager.trace_configurations().query()
    configs = result.get("traceConfigurations", []) or []
    target = named_trace_name.strip().lower()

    named = [(str(cfg.get("title") or cfg.get("name") or ""), cfg) for cfg in configs]
    named = [(name, cfg) for name, cfg in named if name]

    for name, cfg in named:
        if name.strip().lower() == target:
            return cfg

    fuzzy = [
        (name, cfg)
        for name, cfg in named
        if _strip_trace_suffix(name) == _strip_trace_suffix(named_trace_name)
    ]

    if not fuzzy:
        fuzzy = [
            (name, cfg)
            for name, cfg in named
            if _strip_trace_suffix(named_trace_name)
            and _strip_trace_suffix(named_trace_name) in _strip_trace_suffix(name)
        ]

    unique = {id(cfg): (name, cfg) for name, cfg in fuzzy}
    if len(unique) == 1:
        return next(iter(unique.values()))[1]

    available = sorted(name for name, _ in named)
    raise ValueError(
        f"Named trace configuration '{named_trace_name}' not found. "
        f"Available named traces ({len(available)}): "
        f"{', '.join(available) or '(none)'}"
    )


def _named_trace_global_id(un_manager: UtilityNetworkManager, named_trace_name: str) -> str:
    """Look up the global ID for a named trace configuration by name."""
    config = _named_trace_config(un_manager, named_trace_name)
    global_id = config.get("globalId")
    if not global_id:
        raise ValueError(f"Named trace '{named_trace_name}' has no globalId.")
    return str(global_id)


# ---------------------------------------------------------------------------
# Terminal and tier helpers
# ---------------------------------------------------------------------------


def _terminal_recommended_for(is_upstream_terminal: bool | None) -> str | None:
    """Map a terminal's isUpstreamTerminal flag to the trace direction it suits."""
    if is_upstream_terminal is True:
        return "upstream"
    if is_upstream_terminal is False:
        return "downstream"
    return None


def _recommended_terminal_direction(trace_type: str | None) -> str | None:
    """Return the terminal direction a trace prefers."""
    return _TRACE_TYPE_TERMINAL_DIRECTION.get((trace_type or "").strip().lower())


def _split_subnetwork_names(raw: Any) -> list[str]:
    """Split a SUBNETWORKNAME field value into individual subnetwork names."""
    if not raw:
        return []
    parts = re.split(r"[,\n]", str(raw))
    return [p.strip() for p in parts if p.strip() and p.strip().lower() != "unknown"]


def _feature_tier_info(
    flc: FeatureLayerCollection,
    domain: dict[str, Any],
    attrs: dict[str, Any],
) -> dict[str, Any]:
    """Return everything needed to decide which tier a feature belongs to."""
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
    subnetwork_names = _split_subnetwork_names(attrs.get("subnetworkname"))

    info: dict[str, Any] = {
        "subnetworkName": attrs.get("subnetworkname"),
        "subnetworkNames": subnetwork_names,
        "tiers": tier_catalog,
        "featureTierNames": [],
        "featureTierRanks": [],
    }

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
    except Exception as exc:
        logger.warning("Tier resolution for subnetworks %s failed: %s", subnetwork_names, exc)
    return info


# ---------------------------------------------------------------------------
# Core trace and named trace execution
# ---------------------------------------------------------------------------


def _validate_topology(
    un_manager: UtilityNetworkManager, feature_service_url: str, gis: GIS
) -> None:
    """Attempt a topology validation over the service extent."""
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
    """Execute a direct upstream or downstream trace on the utility network."""
    un_manager = UtilityNetworkManager(_utility_network_url(network_service_url), gis=gis)

    if terminal_id is not None or percent_along is not None:
        locations = _starting_point(global_id, terminal_id=terminal_id, percent_along=percent_along)
    elif feature_service_url:
        locations = _starting_point(global_id)
    else:
        locations = _starting_point(global_id)

    configuration: dict[str, Any] = {}
    if domain_network_name:
        configuration["domainNetworkName"] = domain_network_name
    if tier_name:
        configuration["tierName"] = tier_name

    logger.info("Running %s trace from %s", trace_type, global_id)

    def _do_trace() -> dict[str, Any]:
        return un_manager.trace(
            locations=locations,
            trace_type=trace_type,
            configuration=configuration if configuration else None,
            result_types=[{"type": "elements"}],
        )

    raw = _do_trace()

    if raw.get("error", {}).get("extendedCode") == _NO_STARTING_POINTS and feature_service_url:
        logger.warning(
            "Trace returned 'No starting points found'; attempting topology "
            "validation and retrying."
        )
        _validate_topology(un_manager, feature_service_url, gis)
        raw = _do_trace()

    return raw


def run_named_trace(
    gis: GIS,
    network_service_url: str,
    named_trace_name: str,
    global_id: str,
    trace_type: str | None = None,
    terminal_id: int | None = None,
) -> dict[str, Any]:
    """Run a named trace from a starting feature global ID."""
    un_manager = UtilityNetworkManager(_utility_network_url(network_service_url), gis=gis)
    lookup_started = time.perf_counter()
    config = _named_trace_config(un_manager, named_trace_name)
    logger.info(
        "run_named_trace: resolved named trace config '%s' in %.2f seconds.",
        named_trace_name,
        time.perf_counter() - lookup_started,
    )
    trace_config_id = config.get("globalId")
    if not trace_config_id:
        raise ValueError(f"Named trace '{named_trace_name}' has no globalId.")
    resolved_trace_type = trace_type or config.get("traceType") or "connected"

    logger.info(
        "Running named trace '%s' (type=%s) from %s (terminalId=%s)",
        named_trace_name,
        resolved_trace_type,
        global_id,
        terminal_id,
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
        named_trace_name,
        time.perf_counter() - trace_started,
    )
    return result


def _run_trace_with_subnetwork(
    gis: Any,
    network_service_url: str,
    trace_type: str,
    global_id: str,
    domain_network_name: str | None,
    tier_name: str | None,
    terminal_id: int | None,
    percent_along: float | None,
    subnetwork_name: str,
) -> dict[str, Any]:
    """Run a trace with subnetworkName in the configuration."""
    un_manager = UtilityNetworkManager(_utility_network_url(network_service_url), gis=gis)

    locations = _starting_point(global_id, terminal_id=terminal_id, percent_along=percent_along)

    configuration: dict[str, Any] = {"subnetworkName": subnetwork_name}
    if domain_network_name:
        configuration["domainNetworkName"] = domain_network_name
    if tier_name:
        configuration["tierName"] = tier_name

    logger.info(
        "Running %s trace from %s (subnetwork=%s)",
        trace_type,
        global_id,
        subnetwork_name,
    )

    return un_manager.trace(
        locations=locations,
        trace_type=trace_type,
        configuration=configuration,
        result_types=[{"type": "elements"}],
    )


# ---------------------------------------------------------------------------
# Customer data, device terminals, and validation helpers
# ---------------------------------------------------------------------------


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
        return {
            "meterIds": [],
            "globalIdMeterMap": global_map,
            "customers": [],
            "customerCount": 0,
        }

    cust_layer = _find_layer(gis, service_url, "CIS_CUST_VIEW")
    out_fields = (
        ",".join(
            f["name"] for f in cust_layer.properties.fields if f["name"].lower() not in _PII_FIELDS
        )
        or "*"
    )
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


def get_device_terminals(
    gis: GIS,
    feature_service_url: str,
    global_id: str,
) -> dict[str, Any]:
    """Resolve the terminal(s) of a network feature identified by its GlobalID."""
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
        len(layers_by_id),
        time.perf_counter() - flc_started,
    )

    gid = global_id.strip()
    where = f"globalid = {_quote([gid])}"

    scan_started = time.perf_counter()
    queries = 0
    for domain in data_element.get("domainNetworks", []) or []:
        junction_sources = domain.get("junctionSources", []) or []
        edge_sources = domain.get("edgeSources", []) or []
        for source_type, source in [("junction", s) for s in junction_sources] + [
            ("edge", s) for s in edge_sources
        ]:
            layer = layers_by_id.get(source.get("layerId"))
            if layer is None:
                continue
            queries += 1
            features = layer.query(where=where, out_fields="*", return_geometry=False).features
            if not features:
                continue
            logger.info(
                "get_device_terminals: found feature after %d source-layer queries "
                "in %.2f seconds.",
                queries,
                time.perf_counter() - scan_started,
            )

            attrs = {k.lower(): v for k, v in features[0].attributes.items()}
            assetgroup_code = attrs.get("assetgroup")
            assettype_code = attrs.get("assettype")

            grp = next(
                (
                    g
                    for g in source.get("assetGroups", []) or []
                    if g.get("assetGroupCode") == assetgroup_code
                ),
                None,
            )
            asset_type = next(
                (
                    a
                    for a in (grp or {}).get("assetTypes", []) or []
                    if a.get("assetTypeCode") == assettype_code
                ),
                None,
            )
            cfg = terminal_configs.get(
                asset_type.get("terminalConfigurationId") if asset_type else None,
                {},
            )
            terminals = [
                {
                    "terminalId": t.get("terminalId"),
                    "terminalName": t.get("terminalName"),
                    "isUpstreamTerminal": t.get("isUpstreamTerminal"),
                    "recommendedFor": _terminal_recommended_for(t.get("isUpstreamTerminal")),
                }
                for t in cfg.get("terminals", []) or []
            ]
            usage_type = source.get("utilityNetworkFeatureClassUsageType")
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
                "assetTypeName": (asset_type.get("assetTypeName") if asset_type else None),
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


def _terminal_selection_prompt(
    gis: GIS,
    feature_service_url: str,
    global_id: str,
    named_trace_name: str,
    trace_type: str | None,
) -> dict[str, Any] | None:
    """Return a structured 'choose a terminal' response for multi-terminal devices."""
    try:
        info = get_device_terminals(gis, feature_service_url, global_id)
    except Exception as exc:
        logger.warning(
            "Terminal precheck for %s failed (%s); proceeding without a terminal.",
            global_id,
            exc,
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


def _locate_feature_attrs(
    flc: FeatureLayerCollection,
    data_element: dict[str, Any],
    global_id: str,
    domain_network_name: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find a network feature by GlobalID by scanning the domain's sources by role."""
    layers_by_id = {int(lyr.properties.id): lyr for lyr in flc.layers}
    where = f"globalid = {_quote([global_id.strip()])}"
    for domain in data_element.get("domainNetworks", []) or []:
        if (
            domain_network_name
            and str(domain.get("domainNetworkName", "")).strip().lower()
            != str(domain_network_name).strip().lower()
        ):
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
    """Verify the start feature belongs to the tier the named trace targets."""
    trace_cfg = config.get("traceConfiguration") or {}
    domain_name = trace_cfg.get("domainNetworkName")
    tier_name = trace_cfg.get("sourceTierName") or trace_cfg.get("tierName")
    if not tier_name:
        return None

    try:
        flc = FeatureLayerCollection(feature_service_url.rstrip("/"), gis=gis)
        data_element = _un_data_element(flc)

        target_domain = next(
            (
                d
                for d in data_element.get("domainNetworks", []) or []
                if not domain_name
                or str(d.get("domainNetworkName", "")).strip().lower()
                == str(domain_name).strip().lower()
            ),
            None,
        )
        if target_domain is None:
            return None
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
            return None

        _, attrs = _locate_feature_attrs(
            flc, data_element, global_id, target_domain.get("domainNetworkName")
        )
        if not attrs:
            return None
        subnetwork_names = _split_subnetwork_names(attrs.get("subnetworkname"))
        if not subnetwork_names:
            return None

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
            r.attributes.get("TIERNAME") for r in rows if r.attributes.get("TIERNAME") is not None
        }
        if not feature_ranks:
            return None
        if target_rank in feature_ranks:
            return None

        feature_tier_names = sorted(name_by_rank.get(r, f"rank {r}") for r in feature_ranks)
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
                f"Start feature {asset_id} is in subnetwork(s) "
                f"{subnetwork_names}, which belong to tier "
                f"{feature_tier_names}, but the named trace "
                f"'{config.get('title') or config.get('name')}' runs on the "
                f"'{tier_name}' tier. Pick a start feature that participates "
                f"in the '{tier_name}' tier (for a distribution trace, a "
                f"medium-voltage distribution device such as an MV "
                f"transformer — not a high-voltage station transformer)."
            ),
        }
    except Exception as exc:
        logger.warning(
            "Tier precheck for %s failed (%s); proceeding without validation.",
            global_id,
            exc,
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


def _query_associations_sync(
    service_url: str,
    global_id: str,
    association_types: list[str] | None,
    token: str | None,
) -> dict[str, Any]:
    """Synchronous implementation of the associations query."""
    gis = _connect_gis(token)
    un_url = _utility_network_url(service_url)
    associations_url = f"{un_url}/associations/query"

    params: dict[str, Any] = {
        "f": "json",
        "globalIds": f'["{global_id}"]',
    }

    if association_types:
        type_codes: list[int] = []
        for at in association_types:
            code = _ASSOCIATION_TYPE_CODES.get(at.lower().strip().replace(" ", ""))
            if code is None:
                code = _ASSOCIATION_TYPE_CODES.get(at.lower().strip())
            if code is not None:
                type_codes.append(code)
            else:
                logger.warning(
                    "Unknown association type '%s'; accepted values: %s",
                    at,
                    list(_ASSOCIATION_TYPE_CODES.keys()),
                )
        if type_codes:
            params["types"] = str(type_codes)

    logger.info(
        "Querying associations for %s at %s (types=%s)",
        global_id,
        associations_url,
        association_types,
    )

    response = gis._con.post(associations_url, params)

    if isinstance(response, dict) and "error" in response:
        error = response["error"]
        return {
            "error": (
                f"Associations query failed: "
                f"{error.get('message', str(error))} "
                f"(code {error.get('code', 'unknown')})"
            ),
            "endpoint": associations_url,
            "globalId": global_id,
        }

    raw_associations = []
    if isinstance(response, dict):
        raw_associations = response.get("associations", [])
    elif isinstance(response, list):
        raw_associations = response

    data_element = _get_data_element(service_url, token)
    source_lookup = _build_source_lookup(data_element)
    terminal_lookup = _build_terminal_lookup(data_element)

    associations_list: list[dict[str, Any]] = []
    for record in raw_associations:
        assoc_type_code = record.get("associationType")
        assoc_type_name = _ASSOCIATION_TYPE_NAMES.get(
            assoc_type_code, f"unknown ({assoc_type_code})"
        )

        from_identity = _resolve_feature_identity(record, "from", source_lookup, terminal_lookup)
        to_identity = _resolve_feature_identity(record, "to", source_lookup, terminal_lookup)

        association: dict[str, Any] = {
            "associationType": assoc_type_name,
            "associationTypeCode": assoc_type_code,
            "fromFeature": from_identity,
            "toFeature": to_identity,
        }

        if assoc_type_code == 2:
            is_content_visible = record.get("isContentVisible")
            if is_content_visible is not None:
                association["isContentVisible"] = is_content_visible

        percent_along_from = record.get("fromPercentAlong")
        percent_along_to = record.get("toPercentAlong")
        if percent_along_from is not None:
            association["fromPercentAlong"] = percent_along_from
        if percent_along_to is not None:
            association["toPercentAlong"] = percent_along_to

        associations_list.append(association)

    logger.info(
        "network_query_associations: returning %d associations for %s",
        len(associations_list),
        global_id,
    )

    return {
        "globalId": global_id,
        "associations": associations_list,
        "associationCount": len(associations_list),
        "serviceUrl": service_url,
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@utilitynetwork_router.tool(name="network_initialize_session")
async def network_initialize_session() -> dict[str, Any]:
    """REQUIRED: Call this before using any other utility network tool.

    Returns the utility network data model guidance that must inform all
    subsequent tool calls. Call once per session. No parameters needed.
    """
    md_path = Path(__file__).resolve().parent / "utility-network-data-model.md"
    content = md_path.read_text(encoding="utf-8")
    return {"guidance": content, "initialized": True}


@utilitynetwork_router.tool(name="network_get_metadata")
async def network_get_metadata(
    section: str,
    domain_network: str | None = None,
    source_name: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Query the utility network data element for a specific section.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Returns focused, LLM-friendly subsets of the network schema. Use this to
    discover the network's structure, asset types, attributes, and rules.

    section values:
    - domain_networks: domain networks with tiers, topology type, tier groups
    - asset_types: asset groups/types with codes, categories (filterable by domain_network, source_name)
    - network_attributes: network attributes with data type, domain, usage
    - terminal_configurations: terminal configs with names, paths, direction
    - categories: categories with member asset types
    - topology_rules: connectivity rules, edge-junction rules
    - propagators: network attribute propagators (bitwise, max, min)
    """
    if section not in _SECTION_PARSERS:
        return {
            "error": (
                f"Invalid section '{section}'. "
                f"Valid sections: {', '.join(sorted(_SECTION_PARSERS))}."
            ),
        }

    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")

    data_element = await asyncio.to_thread(_get_data_element, service_url, token)

    parser = _SECTION_PARSERS[section]
    return parser(data_element, domain_network=domain_network, source_name=source_name)


@utilitynetwork_router.tool(name="network_refresh_metadata")
async def network_refresh_metadata(
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Invalidate the cached utility network data element and re-fetch it.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Call this if the network schema has changed (e.g., new asset types added,
    terminal configurations updated). After this call, subsequent metadata tool
    calls will use fresh data from the service.
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")

    _invalidate_data_element_cache()
    logger.info("network_refresh_metadata: cache invalidated, re-fetching")
    await asyncio.to_thread(_get_data_element, service_url, token)

    return {
        "message": "Metadata cache invalidated and refreshed successfully.",
        "serviceUrl": service_url,
    }


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

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Calls the UN trace REST endpoint directly with traceType="downstream".
    No named/persisted trace configuration is used.

    - For junction features, supply terminal_id to identify the correct terminal.
    - For edge features, supply percent_along (0.0-1.0) to locate the starting
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
        service_url,
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

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Calls the UN trace REST endpoint directly with traceType="upstream".
    No named/persisted trace configuration is used.

    - For junction features, supply terminal_id to identify the correct terminal.
    - For edge features, supply percent_along (0.0-1.0) to locate the starting
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
        service_url,
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

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    A named trace is a pre-configured trace saved on the server that encapsulates
    a specific trace algorithm along with its barriers, conditions, output filters,
    and result types. This tool executes that saved configuration from a starting
    feature and returns the raw trace results.

    Args:
        named_trace_name: Exact name of the persisted trace configuration to run.
        starting_global_id: GlobalID (GUID) of the network feature to start from.
        trace_type: Optional trace algorithm override.
        terminal_id: Integer terminal ID of the starting feature's terminal.
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

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Returns each configuration's name, globalId, description, trace type, and creator.
    Use this tool to discover which named traces exist before running one with
    ``network_named_trace``.
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


@utilitynetwork_router.tool(name="network_device_terminals")
async def network_device_terminals(
    global_id: str,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Get the terminal ID(s) and their names for a network feature by GlobalID.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Utility network junction features (e.g. transformers, switches, fuses) can
    have multiple terminals. This tool resolves the valid terminals for a given
    feature so you can pick the correct ``terminal_id`` before calling
    ``network_named_trace`` (or another trace tool).
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    gis = _connect_gis(token)
    return await asyncio.to_thread(get_device_terminals, gis, service_url, global_id)


@utilitynetwork_router.tool(name="query_customer_data")
async def query_customer_data(
    global_ids: list[str],
    meter_ids: list[str] | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Query CIS_CUST_VIEW by meter_ids, or resolve meter_ids from ElectricDevice global_ids.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    gis = _connect_gis(token)
    return await asyncio.to_thread(get_customer_data, gis, service_url, global_ids, meter_ids)


@utilitynetwork_router.tool(name="network_trace")
async def network_trace(
    starting_global_id: str,
    trace_type: str,
    network_service_url: str | None = None,
    domain_network_name: str | None = None,
    tier_name: str | None = None,
    terminal_id: int | None = None,
    percent_along: float | None = None,
    subnetwork_name: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Execute any type of utility network trace.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Use this tool for trace types not covered by the dedicated downstream/upstream
    tools: isolation, connected, subnetwork, subnetworkController, loops, shortestPath.

    Each element in the trace results is enriched with resolved names:
    sourceName, assetGroupName, assetTypeName (from the cached data element).
    """
    if trace_type not in _ACCEPTED_TRACE_TYPES:
        return {
            "error": (
                f"Invalid trace_type '{trace_type}'. "
                f"Accepted values: {', '.join(sorted(_ACCEPTED_TRACE_TYPES))}."
            ),
        }

    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")

    gis = _connect_gis(token)

    if trace_type == "subnetwork" and subnetwork_name:
        raw = await asyncio.to_thread(
            _run_trace_with_subnetwork,
            gis,
            service_url,
            trace_type,
            starting_global_id,
            domain_network_name,
            tier_name,
            terminal_id,
            percent_along,
            subnetwork_name,
        )
    else:
        raw = await asyncio.to_thread(
            run_trace,
            gis,
            service_url,
            trace_type,
            starting_global_id,
            domain_network_name,
            tier_name,
            terminal_id,
            percent_along,
            service_url,
        )

    raw = _enrich_trace_elements(raw, service_url, token)

    return _trace_response(trace_type, service_url, starting_global_id, raw)


@utilitynetwork_router.tool(name="network_query_associations")
async def network_query_associations(
    global_id: str,
    association_types: list[str] | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Query utility network associations for a feature by GlobalID.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Returns connectivity, containment, and/or structural attachment associations.
    Use association_types to filter (e.g., ["connectivity", "containment"]).

    Each association includes:
    - associationType: human-readable name (connectivity, containment, structuralAttachment)
    - fromFeature / toFeature: identity with globalId, sourceName, assetGroupName,
      assetTypeName, and terminalName (all resolved from numeric codes)
    """
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")

    return await asyncio.to_thread(
        _query_associations_sync, service_url, global_id, association_types, token
    )


@utilitynetwork_router.tool(name="network_resolve_coded_values")
async def network_resolve_coded_values(
    features: list[dict[str, Any]],
    layer_url: str,
    token: str | None = None,
) -> dict[str, Any]:
    """Resolve coded attribute values to human-readable labels using layer subtype domains.

    Prerequisite: call ``network_initialize_session`` first if not already done this session.

    Use this when you have features from query_feature_layer on a UN layer and
    need to decode their coded values.

    For each feature, determines its subtype from the layer's subtypeField, then
    resolves each field that has a coded value domain for that subtype. The output
    preserves both the raw code and the label: {"code": N, "label": "Human Name"}.
    """
    layer_metadata = await _get_layer_metadata(layer_url, token)

    if not layer_metadata:
        logger.warning(
            "network_resolve_coded_values: could not fetch layer metadata for %s; "
            "returning features unchanged.",
            layer_url,
        )
        return {
            "features": features,
            "featureCount": len(features),
            "layerUrl": layer_url,
            "resolvedFields": [],
            "warning": ("Could not fetch layer metadata; features returned with raw codes."),
        }

    resolved = resolve_subtype_domains(features, layer_metadata)

    resolved_fields: set[str] = set()
    for orig, res in zip(features, resolved, strict=True):
        for key, val in res.items():
            if (
                isinstance(val, dict)
                and "code" in val
                and "label" in val
                and not isinstance(orig.get(key), dict)
            ):
                resolved_fields.add(key)

    return {
        "features": resolved,
        "featureCount": len(resolved),
        "layerUrl": layer_url,
        "resolvedFields": sorted(resolved_fields),
    }


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@utilitynetwork_router.resource(uri="resource://utility-network/workflow-guidance")
def workflow_guidance_resource() -> str:
    """Provide utility network workflow guidance to LLM clients."""
    md_path = os.path.join(_CURRENT_DIR, "utility-network-workflows.md")
    try:
        with open(md_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Workflow guidance file not found: %s", md_path)
        return (
            "Utility network workflow guidance is unavailable. "
            "The utility-network-workflows.md file was not found in the "
            "package directory."
        )


@utilitynetwork_router.resource(uri="resource://utility-network/data-model-guidance")
def data_model_guidance_resource() -> str:
    """Provide utility network data model disambiguation guidance to LLM clients."""
    md_path = os.path.join(_CURRENT_DIR, "utility-network-data-model.md")
    try:
        with open(md_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Data model guidance file not found: %s", md_path)
        return (
            "Utility network data model guidance is unavailable. "
            "The utility-network-data-model.md file was not found in the "
            "package directory."
        )


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@utilitynetwork_router.prompt(name="utility_network_metadata_discovery")
def utility_network_metadata_discovery() -> str:
    """Guide the AI through discovering utility network structure and metadata."""
    return _read_skill("metadata_discovery.md")


@utilitynetwork_router.prompt(name="utility_network_downstream_customer_impact")
def utility_network_downstream_customer_impact() -> str:
    """Guide the AI through finding customers affected by a downstream outage."""
    return _read_skill("downstream_customer_impact.md")


@utilitynetwork_router.prompt(name="utility_network_isolation_analysis")
def utility_network_isolation_analysis() -> str:
    """Guide the AI through identifying isolation devices for a network element."""
    return _read_skill("isolation_analysis.md")


@utilitynetwork_router.prompt(name="utility_network_spatial_impact")
def utility_network_spatial_impact() -> str:
    """Guide the AI through assessing customer impact within a geographic area."""
    return _read_skill("spatial_impact_assessment.md")


@utilitynetwork_router.prompt(name="utility_network_named_trace_execution")
def utility_network_named_trace_execution() -> str:
    """Guide the AI through discovering and executing named trace configurations."""
    return _read_skill("named_trace_execution.md")


@utilitynetwork_router.prompt(name="utility_network_customer_data_discovery")
def utility_network_customer_data_discovery() -> str:
    """Guide the AI through discovering customer data sources on the network."""
    return _read_skill("customer_data_discovery.md")


@utilitynetwork_router.prompt(name="utility_network_address_resolution")
def utility_network_address_resolution() -> str:
    """Guide the AI through resolving an address to a network element GlobalID."""
    return _read_skill("address_to_network_element.md")


@utilitynetwork_router.prompt(name="utility_network_trace_interpretation")
def utility_network_trace_interpretation() -> str:
    """Guide the AI through interpreting utility network trace results.

    Use this prompt after running a trace to understand how to read elements,
    sourceMapping, function results, phase encoding, and identify issues.
    """
    return _read_skill("trace_interpretation.md")
