"""ArcGIS Utility Network subnetwork router plugin for PS-MCP.

Single service file exposing the ``subnetwork_router`` FastMCP instance and its
tools. All UN operations go through ``arcgis.features._utility.UtilityNetworkManager``
and ``FeatureLayerCollection`` on ``arcgis.gis.GIS``, resolving auth via
``psmcp.core.auth.resolve_token`` and the service URL from the ``UTILITY_NETWORK_URL``
environment variable or a ``network_service_url`` argument.
"""

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arcgis.features import FeatureLayerCollection
from arcgis.features._utility import UtilityNetworkManager
from arcgis.features._version import VersionManager
from arcgis.gis import GIS
from dotenv import load_dotenv
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

load_dotenv()

logger = logging.getLogger(__name__)

subnetwork_router = FastMCP(name="UN Subnetwork")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() != "false"
UTILITY_NETWORK_URL = os.getenv("UTILITY_NETWORK_URL")

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


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
    """Resolve the FeatureServer service URL from an arg or the environment."""
    service_url = network_service_url or os.getenv("UTILITY_NETWORK_URL")
    if not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    return service_url


def _connect_gis(token: str | None = None) -> GIS:
    """Establish an authenticated GIS connection using the resolved token."""
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
    """Build a UtilityNetworkManager bound to the UtilityNetworkServer endpoint."""
    return UtilityNetworkManager(url=_utility_network_url(service_url), gis=gis)


def _version_guid(gis: GIS, service_url: str, version_ref: str) -> str | None:
    """Resolve a branch version reference to its version GUID.

    ``version_ref`` of ``"default"`` (case-insensitive) resolves to ``None`` so the
    operation targets the default version. Any other value is matched against the
    available branch versions by name; a missing version raises ``ValueError`` so the
    caller can surface a "branch not found" error without mutating any state.
    """
    if not version_ref or version_ref.lower() == "default":
        return None

    vms_url = _utility_network_url(service_url).rsplit("/", 1)[0] + "/VersionManagementServer"
    version_manager = VersionManager(url=vms_url, gis=gis)
    target = version_ref.lower()
    for version in version_manager.all:
        props = getattr(version, "properties", {}) or {}
        name = str(props.get("versionName", "")).lower()
        if name == target or name.endswith("." + target):
            guid = props.get("versionGuid") or props.get("versionIdentifier")
            if guid:
                return str(guid)
    raise ValueError(f"Branch version '{version_ref}' was not found.")


def _controller_count(result: dict[str, Any]) -> int:
    """Best-effort extraction of the subnetwork controller count from a result."""
    if not isinstance(result, dict):
        return 0
    for key in ("controllers", "subnetworkControllers"):
        value = result.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int):
            return value
    moments = result.get("moments") or result.get("results")
    if isinstance(moments, list):
        return len(moments)
    return 0


# ---------------------------------------------------------------------------
# Synchronous worker implementations (run off the event loop)
# ---------------------------------------------------------------------------


def _update_subnetwork_sync(
    service_url: str,
    domain_network: str,
    tier: str,
    subnetwork_name: str,
    version_ref: str,
    token: str | None,
) -> dict[str, Any]:
    gis = _connect_gis(token)
    version_guid = _version_guid(gis, service_url, version_ref)
    manager = _get_manager(gis, service_url)

    kwargs: dict[str, Any] = {
        "domain_name": domain_network,
        "tier_name": tier,
        "subnetwork_name": subnetwork_name,
    }
    if version_guid is not None:
        kwargs["gdb_version"] = version_ref
        kwargs["session_id"] = version_guid

    result = manager.update_subnetwork(**kwargs)

    success = bool(result.get("success", True)) if isinstance(result, dict) else True
    if isinstance(result, dict) and result.get("error"):
        return {"error": str(result.get("error"))}

    is_dirty = False
    if isinstance(result, dict):
        is_dirty = bool(result.get("isDirty", result.get("is_dirty", False)))

    return {
        "subnetwork_name": subnetwork_name,
        "updated": success,
        "is_dirty": is_dirty,
        "controller_count": _controller_count(result if isinstance(result, dict) else {}),
    }


def _export_subnetwork_sync(
    service_url: str,
    domain_network: str,
    tier: str,
    subnetwork_name: str,
    version_ref: str,
    export_path: str | None,
    token: str | None,
) -> dict[str, Any]:
    resolved_path = export_path or os.getenv("SUBNETWORK_EXPORT_PATH")
    if not resolved_path:
        return {"error": "Provide export_path or set SUBNETWORK_EXPORT_PATH."}

    # Validate the destination is writable BEFORE performing the export so a failure
    # never leaves a partial JSON file behind.
    out_path = Path(resolved_path)
    parent = out_path.parent if out_path.suffix else out_path
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / f".psmcp_write_probe_{os.getpid()}"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return {"error": f"Export path is not writable: {resolved_path} ({exc})."}

    gis = _connect_gis(token)
    version_guid = _version_guid(gis, service_url, version_ref)
    manager = _get_manager(gis, service_url)

    kwargs: dict[str, Any] = {
        "domain_name": domain_network,
        "tier_name": tier,
        "subnetwork_name": subnetwork_name,
        "result_types": [
            {"type": "features", "includeGeometry": False},
            {"type": "controllers", "includeGeometry": False},
        ],
    }
    if version_guid is not None:
        kwargs["gdb_version"] = version_ref
        kwargs["session_id"] = version_guid

    result = manager.export_subnetwork(**kwargs)

    if isinstance(result, dict) and result.get("error"):
        return {"error": str(result.get("error"))}

    features = []
    if isinstance(result, dict):
        features = result.get("features") or result.get("elements") or []
    feature_count = len(features) if isinstance(features, list) else 0

    # Determine the final file path. If a directory was supplied, name the file after
    # the subnetwork.
    if out_path.suffix.lower() != ".json":
        final_path = out_path / f"{subnetwork_name}.json"
    else:
        final_path = out_path

    try:
        final_path.write_text(
            json.dumps(result if isinstance(result, dict) else {}, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        return {"error": f"Failed to write export file: {final_path} ({exc})."}

    return {
        "path": str(final_path.resolve()),
        "feature_count": feature_count,
        "exported_at": datetime.now(UTC).isoformat(),
    }


def _list_subnetworks_sync(
    service_url: str,
    domain_network: str | None,
    tier: str | None,
    token: str | None,
) -> dict[str, Any]:
    gis = _connect_gis(token)
    flc = FeatureLayerCollection(service_url.rstrip("/"), gis=gis)

    controller = dict(flc.properties.get("controllerDatasetLayers", {}) or {})
    subnet_table_id = controller.get("subnetworksTableId")
    if subnet_table_id is None:
        return {"error": "Service does not expose a Subnetworks table."}

    subnet_table = None
    for table in flc.tables:
        if getattr(table.properties, "id", None) == subnet_table_id:
            subnet_table = table
            break
    if subnet_table is None:
        return {"error": "Subnetworks table not found on the service."}

    where_clauses: list[str] = []
    if domain_network:
        where_clauses.append(f"domainnetworkname = '{domain_network.replace(chr(39), chr(39) * 2)}'")
    if tier:
        where_clauses.append(f"tiername = '{tier.replace(chr(39), chr(39) * 2)}'")
    where = " AND ".join(where_clauses) if where_clauses else "1=1"

    features = subnet_table.query(where=where, out_fields="*", return_geometry=False).features

    subnetworks: list[dict[str, Any]] = []
    for feat in features:
        attrs = {k.lower(): v for k, v in (feat.attributes or {}).items()}
        subnetworks.append(
            {
                "name": attrs.get("subnetworkname") or attrs.get("subnetwork_name"),
                "domain_network": attrs.get("domainnetworkname"),
                "tier": attrs.get("tiername"),
                "is_dirty": bool(attrs.get("isdirty", False)),
            }
        )

    return {"subnetworks": subnetworks}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@subnetwork_router.tool(name="subnetwork_update")
async def subnetwork_update(
    domain_network: str,
    tier: str,
    subnetwork_name: str,
    version_ref: str = "default",
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Update (recompute) a subnetwork on a branch or the default version.

    Traces from all subnetwork controllers, refreshes the SubnetLine record, updates
    the Subnetworks table, and regenerates diagrams for the named subnetwork. When
    ``version_ref`` is ``"default"`` the update targets the default version; otherwise
    it targets the named branch version. A branch that does not exist is rejected with
    an error and no state is changed.

    Returns ``{subnetwork_name, updated, is_dirty, controller_count}``.
    """
    service_url = _resolve_service_url(network_service_url)
    try:
        return await asyncio.to_thread(
            _update_subnetwork_sync,
            service_url,
            domain_network,
            tier,
            subnetwork_name,
            version_ref,
            token,
        )
    except ValueError as exc:
        logger.warning("subnetwork_update: %s", exc)
        return {"error": str(exc)}
    except Exception as exc:  # surface a stable error shape to the agent
        logger.exception("subnetwork_update failed")
        return {"error": f"Subnetwork update failed: {exc}"}


@subnetwork_router.tool(name="subnetwork_export_json")
async def subnetwork_export_json(
    domain_network: str,
    tier: str,
    subnetwork_name: str,
    version_ref: str = "default",
    export_path: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Export a subnetwork as a JSON file to the configured export path.

    Validates that the destination is writable before exporting so an unwritable path
    aborts without producing a partial file and returns an error indication. On success
    reports the absolute output path and a non-negative exported feature count.

    Returns ``{path, feature_count, exported_at}``.
    """
    service_url = _resolve_service_url(network_service_url)
    try:
        return await asyncio.to_thread(
            _export_subnetwork_sync,
            service_url,
            domain_network,
            tier,
            subnetwork_name,
            version_ref,
            export_path,
            token,
        )
    except ValueError as exc:
        logger.warning("subnetwork_export_json: %s", exc)
        return {"error": str(exc)}
    except Exception as exc:  # surface a stable error shape to the agent
        logger.exception("subnetwork_export_json failed")
        return {"error": f"Subnetwork export failed: {exc}"}


@subnetwork_router.tool(name="subnetwork_list")
async def subnetwork_list(
    domain_network: str | None = None,
    tier: str | None = None,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """List subnetworks, optionally filtered by domain network and/or tier.

    Reads the Subnetworks table from the utility network FeatureServer. Returns an
    empty list when no subnetworks match the filters.

    Returns ``{subnetworks: [{name, domain_network, tier, is_dirty}]}``.
    """
    service_url = _resolve_service_url(network_service_url)
    try:
        return await asyncio.to_thread(
            _list_subnetworks_sync,
            service_url,
            domain_network,
            tier,
            token,
        )
    except ValueError as exc:
        logger.warning("subnetwork_list: %s", exc)
        return {"error": str(exc)}
    except Exception as exc:  # surface a stable error shape to the agent
        logger.exception("subnetwork_list failed")
        return {"error": f"Subnetwork list failed: {exc}"}


@subnetwork_router.prompt(name="subnetwork_update_export")
def subnetwork_update_export() -> str:
    """Guide the AI through updating and exporting a subnetwork."""
    return _read_skill("subnetwork_workflow.md")
