"""ArcGIS Utility Network 811 dig-ticket domain router plugin for PS-MCP.

Single service file exposing the ``domain811_router`` FastMCP instance and its
tools. All utility network operations go through
``arcgis.features._utility.UtilityNetworkManager`` and
``arcgis.features.FeatureLayerCollection`` on an ``arcgis.gis.GIS`` connection,
resolving auth via ``psmcp.core.auth.resolve_token`` and the service URL from the
``UTILITY_NETWORK_URL`` environment variable or a ``network_service_url`` argument.

The ``domain811_analyze_ticket`` tool analyzes an 811 (call-before-you-dig) dig
ticket against the live utility network: it validates the untrusted ticket
payload, finds features intersecting the georeferenced dig area, runs a
trace-backed impact analysis from those features, and returns the list of
impacted assets with an assigned risk level. Tool-level failures return an
``{"error": ...}`` shape (mirroring the other UN routers); a rejected ticket
retains no partial analysis results.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from arcgis.features import FeatureLayerCollection
from arcgis.features._utility import UtilityNetworkManager
from arcgis.gis import GIS
from dotenv import load_dotenv
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

load_dotenv()

logger = logging.getLogger(__name__)

domain811_router = FastMCP(name="Domain 811")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() != "false"
UTILITY_NETWORK_URL = os.getenv("UTILITY_NETWORK_URL")

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Esri geometry types that describe a georeferenced dig area (a polygon extent
# or a bounding envelope). Points/polylines are not valid dig areas.
_POLYGON_KEYS = ("rings",)
_ENVELOPE_KEYS = ("xmin", "ymin", "xmax", "ymax")

# Risk thresholds keyed on the number of trace-backed impacted assets.
_RISK_MEDIUM_THRESHOLD = 1
_RISK_HIGH_THRESHOLD = 10


def _read_skill(filename: str) -> str:
    """Read a skill file from the skills directory."""
    skill_path = _SKILLS_DIR / filename
    if not skill_path.exists():
        logger.error("Skill file not found: %s", skill_path)
        raise FileNotFoundError(f"Skill file not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Core helpers (GIS connection, URL building, manager access)
# ---------------------------------------------------------------------------


def _resolve_service_url(network_service_url: str | None) -> str:
    """Return the FeatureServer URL from the argument or the environment."""
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    return service_url.rstrip("/")


def _connect_gis(token: str | None = None) -> GIS:
    """Establish a GIS connection, resolving the token at runtime."""
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


def _utility_network_url(network_service_url: str) -> str:
    """FeatureServer URL -> UtilityNetworkServer URL (manager REST endpoint)."""
    base = network_service_url.rstrip("/")
    if base.lower().endswith("/utilitynetworkserver"):
        return base
    if base.lower().endswith("/featureserver"):
        parent, _ = base.rsplit("/", 1)
        return f"{parent}/UtilityNetworkServer"
    return f"{base}/UtilityNetworkServer"


def _get_feature_layer_collection(gis: GIS, service_url: str) -> FeatureLayerCollection:
    """Return the FeatureLayerCollection for the service."""
    return FeatureLayerCollection(service_url.rstrip("/"), gis=gis)


def _get_manager(gis: GIS, service_url: str) -> UtilityNetworkManager:
    """Return the UtilityNetworkManager bound to the UtilityNetworkServer endpoint."""
    return UtilityNetworkManager(url=_utility_network_url(service_url), gis=gis)


# ---------------------------------------------------------------------------
# Untrusted-ticket validation
# ---------------------------------------------------------------------------


class _TicketError(ValueError):
    """Raised when an untrusted 811 ticket payload is invalid."""


def _extract_dig_area(ticket: Any) -> dict[str, Any]:
    """Validate an untrusted 811 ticket and return its georeferenced dig area.

    The ticket must be a JSON object carrying a georeferenced dig area under one
    of ``dig_area``, ``digArea``, or ``geometry``. The dig area must be an Esri
    polygon (``rings``) or a bounding envelope (``xmin/ymin/xmax/ymax``); any
    other shape is treated as an unparseable geometry.

    Raises:
        _TicketError: If the ticket is missing a dig area or the geometry is
            unparseable, so the caller can reject the ticket without producing
            any partial analysis.
    """
    if not isinstance(ticket, dict):
        raise _TicketError("ticket must be a JSON object")

    dig_area = None
    for key in ("dig_area", "digArea", "geometry"):
        candidate = ticket.get(key)
        if candidate is not None:
            dig_area = candidate
            break
    if dig_area is None:
        raise _TicketError(
            "ticket is missing a georeferenced dig area (expected 'dig_area', "
            "'digArea', or 'geometry')"
        )
    if not isinstance(dig_area, dict):
        raise _TicketError("dig area geometry must be a JSON object")

    if any(key in dig_area for key in _POLYGON_KEYS):
        rings = dig_area.get("rings")
        if not isinstance(rings, list) or not rings:
            raise _TicketError("dig area polygon has an unparseable 'rings' geometry")
        return dig_area
    if all(key in dig_area for key in _ENVELOPE_KEYS):
        try:
            _ = [float(dig_area[key]) for key in _ENVELOPE_KEYS]
        except (TypeError, ValueError) as exc:
            raise _TicketError(f"dig area envelope has unparseable bounds: {exc}") from exc
        return dig_area

    raise _TicketError(
        "dig area geometry is unparseable; expected a polygon ('rings') or an "
        "envelope ('xmin', 'ymin', 'xmax', 'ymax')"
    )


def _dig_area_query_geometry(dig_area: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return ``(geometry, geometry_type)`` for a spatial query from a dig area."""
    if any(key in dig_area for key in _POLYGON_KEYS):
        return dig_area, "esriGeometryPolygon"
    return dig_area, "esriGeometryEnvelope"


# ---------------------------------------------------------------------------
# Impact analysis (synchronous worker, run off the event loop)
# ---------------------------------------------------------------------------


def _asset_from_feature(layer_name: str, layer_id: Any, feature: Any) -> dict[str, Any]:
    """Normalize a queried feature into an impacted-asset record."""
    attrs = {}
    raw_attrs = getattr(feature, "attributes", None)
    if isinstance(raw_attrs, dict):
        attrs = {str(k).lower(): v for k, v in raw_attrs.items()}
    return {
        "layer_id": layer_id,
        "layer_name": layer_name,
        "global_id": attrs.get("globalid") or attrs.get("global_id"),
        "object_id": attrs.get("objectid") or attrs.get("object_id"),
        "asset_group": attrs.get("assetgroup"),
        "asset_type": attrs.get("assettype"),
    }


def _elements_to_assets(elements: Any) -> list[dict[str, Any]]:
    """Normalize trace ``traceResults.elements`` into impacted-asset records."""
    assets: list[dict[str, Any]] = []
    if not isinstance(elements, list):
        return assets
    for element in elements:
        if not isinstance(element, dict):
            continue
        assets.append(
            {
                "network_source_id": element.get("networkSourceId"),
                "global_id": element.get("globalId"),
                "object_id": element.get("objectId"),
                "asset_group": element.get("assetGroupCode"),
                "asset_type": element.get("assetTypeCode"),
                "terminal_id": element.get("terminalId"),
            }
        )
    return assets


def _dedupe_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate assets keyed by (global_id, object_id, network_source_id)."""
    seen: set[tuple[Any, Any, Any]] = set()
    unique: list[dict[str, Any]] = []
    for asset in assets:
        key = (
            asset.get("global_id"),
            asset.get("object_id"),
            asset.get("network_source_id") or asset.get("layer_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(asset)
    return unique


def _assess_risk(impacted_count: int) -> str:
    """Assign a risk level from the set {low, medium, high} by impacted count."""
    if impacted_count >= _RISK_HIGH_THRESHOLD:
        return "high"
    if impacted_count >= _RISK_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _query_features_in_dig_area(
    flc: FeatureLayerCollection, geometry: dict[str, Any], geometry_type: str
) -> list[dict[str, Any]]:
    """Query every UN layer for features intersecting the dig area geometry."""
    impacted: list[dict[str, Any]] = []
    for layer in getattr(flc, "layers", []) or []:
        props = getattr(layer, "properties", {}) or {}
        layer_id = props.get("id") if isinstance(props, dict) else getattr(props, "id", None)
        layer_name = (
            props.get("name") if isinstance(props, dict) else getattr(props, "name", None)
        ) or str(layer_id)
        try:
            result = layer.query(
                geometry_filter={"geometry": geometry, "geometryType": geometry_type},
                spatial_relationship="esriSpatialRelIntersects",
                out_fields="*",
                return_geometry=False,
            )
        except Exception:  # pragma: no cover - a non-spatial layer/table is skipped
            logger.debug("domain811: layer %s skipped during dig-area query", layer_id)
            continue
        for feature in getattr(result, "features", []) or []:
            impacted.append(_asset_from_feature(layer_name, layer_id, feature))
    return impacted


def _trace_from_assets(
    manager: UtilityNetworkManager, assets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Run a connected trace from features in the dig area to find impacts."""
    locations = [
        {"traceLocationType": "startingPoint", "globalId": asset["global_id"]}
        for asset in assets
        if asset.get("global_id")
    ]
    if not locations:
        return []
    result = manager.trace(
        locations=locations,
        trace_type="connected",
        result_types=[{"type": "elements", "includeGeometry": False}],
    )
    if isinstance(result, dict):
        if result.get("error"):
            raise RuntimeError(str(result.get("error")))
        trace_results = result.get("traceResults") or {}
        return _elements_to_assets(trace_results.get("elements"))
    return []


def _analyze_ticket_sync(
    service_url: str, dig_area: dict[str, Any], token: str | None
) -> dict[str, Any]:
    """Find impacted assets in the dig area and assess dig risk (trace-backed)."""
    geometry, geometry_type = _dig_area_query_geometry(dig_area)
    gis = _connect_gis(token)
    flc = _get_feature_layer_collection(gis, service_url)

    in_area = _query_features_in_dig_area(flc, geometry, geometry_type)

    traced: list[dict[str, Any]] = []
    try:
        manager = _get_manager(gis, service_url)
        traced = _trace_from_assets(manager, in_area)
    except Exception as exc:  # a trace failure degrades to the intersecting set
        logger.warning("domain811: trace-backed impact analysis failed: %s", exc)

    impacted_assets = _dedupe_assets(in_area + traced)
    return {
        "impacted_assets": impacted_assets,
        "risk": _assess_risk(len(impacted_assets)),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@domain811_router.tool(name="domain811_analyze_ticket")
async def domain811_analyze_ticket(
    ticket: dict,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Analyze an 811 dig ticket against the utility network (trace-backed).

    Validates the untrusted ``ticket`` payload and extracts its georeferenced dig
    area (an Esri polygon or envelope), queries the utility network for features
    intersecting the dig area, runs a connected trace from those features to
    surface trace-backed impacts, and assigns a risk level from the set
    ``{low, medium, high}`` based on the number of impacted assets.

    A ticket that is missing a georeferenced dig area or contains an unparseable
    geometry is rejected with an ``{"error": ...}`` shape and no partial analysis.

    Returns ``{impacted_assets: [...], risk}`` on success.
    """
    try:
        service_url = _resolve_service_url(network_service_url)
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        dig_area = _extract_dig_area(ticket)
    except _TicketError as exc:
        logger.warning("domain811_analyze_ticket rejected ticket: %s", exc)
        return {"error": f"Invalid 811 ticket: {exc}"}

    try:
        return await asyncio.to_thread(_analyze_ticket_sync, service_url, dig_area, token)
    except ValueError as exc:
        logger.warning("domain811_analyze_ticket: %s", exc)
        return {"error": str(exc)}
    except Exception as exc:  # surface a stable error shape to the agent
        logger.exception("domain811_analyze_ticket failed")
        return {"error": f"811 ticket analysis failed: {exc}"}


@domain811_router.prompt(name="domain811_ticket_analysis")
def domain811_ticket_analysis() -> str:
    """Guide the AI through analyzing an 811 dig ticket against the network."""
    return _read_skill("domain811_workflow.md")
