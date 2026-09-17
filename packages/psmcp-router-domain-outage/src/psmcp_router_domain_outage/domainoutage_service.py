"""ArcGIS Utility Network outage-event domain router plugin for PS-MCP.

Single service file exposing the ``domainoutage_router`` FastMCP instance and its
tools. All utility network operations go through
``arcgis.features._utility.UtilityNetworkManager`` on an ``arcgis.gis.GIS``
connection, resolving auth via ``psmcp.core.auth.resolve_token`` and the service
URL from the ``UTILITY_NETWORK_URL`` environment variable or a
``network_service_url`` argument.

The ``domainoutage_analyze_event`` tool analyzes an outage event: it validates
the untrusted outage payload, runs a downstream trace from the referenced network
location, counts affected customers, and returns the affected assets. Tool-level
failures return an ``{"error": ...}`` shape (mirroring the other UN routers); an
outage event that references a nonexistent or untraceable location returns an
error with no partial trace results.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from arcgis.features._utility import UtilityNetworkManager
from arcgis.gis import GIS
from dotenv import load_dotenv
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

load_dotenv()

logger = logging.getLogger(__name__)

domainoutage_router = FastMCP(name="Domain Outage")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() != "false"
UTILITY_NETWORK_URL = os.getenv("UTILITY_NETWORK_URL")

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Asset-group / asset-type substrings that identify a customer service point.
# Downstream elements whose category or asset group looks like a service/meter
# point are counted as affected customers.
_CUSTOMER_HINTS = ("service", "meter", "customer", "consumer")


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


def _get_manager(gis: GIS, service_url: str) -> UtilityNetworkManager:
    """Return the UtilityNetworkManager bound to the UtilityNetworkServer endpoint."""
    return UtilityNetworkManager(url=_utility_network_url(service_url), gis=gis)


# ---------------------------------------------------------------------------
# Untrusted-payload validation
# ---------------------------------------------------------------------------


class _OutageError(ValueError):
    """Raised when an untrusted outage-event payload is invalid."""


def _extract_location(outage_event: Any) -> dict[str, Any]:
    """Validate an untrusted outage event and return its trace starting point.

    The event must be a JSON object referencing a network location. A location is
    accepted when it supplies a feature ``globalId`` (optionally with a
    ``terminalId`` or ``percentAlong``) under one of ``location``, ``start`` or
    the event's own ``global_id``/``globalId`` fields.

    Raises:
        _OutageError: If the event is not an object or does not reference a
            network location, so the caller can reject it without producing any
            partial trace results.
    """
    if not isinstance(outage_event, dict):
        raise _OutageError("outage_event must be a JSON object")

    location = None
    for key in ("location", "start", "starting_point", "startingPoint"):
        candidate = outage_event.get(key)
        if isinstance(candidate, dict):
            location = candidate
            break
    if location is None:
        # Allow a flat event carrying the identifiers directly.
        if outage_event.get("global_id") or outage_event.get("globalId"):
            location = outage_event
        else:
            raise _OutageError(
                "outage_event does not reference a network location (expected a "
                "'location' object or a 'global_id')"
            )

    global_id = location.get("global_id") or location.get("globalId")
    if not isinstance(global_id, str) or not global_id.strip():
        raise _OutageError("outage location must include a non-empty feature 'global_id'")

    trace_location: dict[str, Any] = {
        "traceLocationType": "startingPoint",
        "globalId": global_id,
    }
    terminal_id = location.get("terminal_id", location.get("terminalId"))
    if terminal_id is not None:
        trace_location["terminalId"] = terminal_id
    percent_along = location.get("percent_along", location.get("percentAlong"))
    if percent_along is not None:
        trace_location["percentAlong"] = percent_along
    return trace_location


# ---------------------------------------------------------------------------
# Impact analysis (synchronous worker, run off the event loop)
# ---------------------------------------------------------------------------


def _elements_to_assets(elements: Any) -> list[dict[str, Any]]:
    """Normalize trace ``traceResults.elements`` into affected-asset records."""
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


def _looks_like_customer(asset: dict[str, Any]) -> bool:
    """Return True when an affected asset represents a customer service point."""
    haystack = " ".join(
        str(asset.get(key, "")).lower()
        for key in ("asset_group", "asset_type", "category", "layer_name")
    )
    return any(hint in haystack for hint in _CUSTOMER_HINTS)


def _count_affected_customers(assets: list[dict[str, Any]]) -> int:
    """Count the affected assets that represent customer service points."""
    return sum(1 for asset in assets if _looks_like_customer(asset))


def _analyze_event_sync(
    service_url: str, trace_location: dict[str, Any], token: str | None
) -> dict[str, Any]:
    """Run a downstream trace from the outage location and summarize impact.

    A location that does not exist in the utility network or a trace that fails
    surfaces as a ``ValueError`` so the tool rejects the event without returning
    any partial trace results.
    """
    gis = _connect_gis(token)
    manager = _get_manager(gis, service_url)

    try:
        result = manager.trace(
            locations=[trace_location],
            trace_type="downstream",
            result_types=[{"type": "elements", "includeGeometry": False}],
        )
    except Exception as exc:
        raise ValueError(
            f"Outage location could not be traced (location may not exist in the "
            f"utility network): {exc}"
        ) from exc

    if isinstance(result, dict) and result.get("error"):
        raise ValueError(f"Outage downstream trace failed: {result.get('error')}")

    trace_results = result.get("traceResults") if isinstance(result, dict) else None
    if not isinstance(trace_results, dict):
        raise ValueError(
            "Outage downstream trace returned no results; the referenced location "
            "may not exist in the utility network."
        )

    affected_assets = _elements_to_assets(trace_results.get("elements"))
    return {
        "affected_customers": _count_affected_customers(affected_assets),
        "affected_assets": affected_assets,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@domainoutage_router.tool(name="domainoutage_analyze_event")
async def domainoutage_analyze_event(
    outage_event: dict,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Analyze an outage event via a downstream trace over the utility network.

    Validates the untrusted ``outage_event`` payload and extracts the referenced
    network location (a feature ``global_id`` starting point), runs a downstream
    trace from that location, counts affected customers among the downstream
    assets, and returns the affected assets.

    An outage event that references a network location that does not exist or
    cannot be traced returns an ``{"error": ...}`` shape with no partial results.

    Returns ``{affected_customers: int, affected_assets: [...]}`` on success.
    """
    try:
        service_url = _resolve_service_url(network_service_url)
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        trace_location = _extract_location(outage_event)
    except _OutageError as exc:
        logger.warning("domainoutage_analyze_event rejected event: %s", exc)
        return {"error": f"Invalid outage event: {exc}"}

    try:
        return await asyncio.to_thread(_analyze_event_sync, service_url, trace_location, token)
    except ValueError as exc:
        logger.warning("domainoutage_analyze_event: %s", exc)
        return {"error": str(exc)}
    except Exception as exc:  # surface a stable error shape to the agent
        logger.exception("domainoutage_analyze_event failed")
        return {"error": f"Outage event analysis failed: {exc}"}


@domainoutage_router.prompt(name="domainoutage_event_analysis")
def domainoutage_event_analysis() -> str:
    """Guide the AI through analyzing an outage event against the network."""
    return _read_skill("domainoutage_workflow.md")
