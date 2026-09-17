"""ArcGIS Utility Network data model & service admin router plugin for PS-MCP.

Single service file exposing the ``datamodel_router`` FastMCP instance and its
tools. Data model analysis/apply operations run against the utility network
service (``UtilityNetworkManager`` on a ``FeatureLayerCollection``); service
stop/start operations run against ArcGIS Server admin resolved from the portal.

Tools
-----
- ``datamodel_analyze_change``  -> ``{valid, requires_republish, impacted_services, notes}``
- ``serviceadmin_stop_services`` -> ``{stopped, failed}``
- ``datamodel_apply_change``     -> ``{applied, details}``
- ``serviceadmin_start_services`` -> ``{started, failed}``

If ``datamodel_analyze_change`` returns ``requires_republish=True`` the Data
Model Agent must NOT auto-apply; it guides the user to republish manually.
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

datamodel_router = FastMCP(name="UN Data Model & Service Admin")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() != "false"
UTILITY_NETWORK_URL = os.getenv("UTILITY_NETWORK_URL")

# Data model change operations that force a service republish before they can be
# consumed by clients (schema-altering changes cannot be applied hot).
_REPUBLISH_OPERATIONS = frozenset(
    {
        "add_field",
        "delete_field",
        "add_asset_type",
        "delete_asset_type",
        "add_domain_network",
        "delete_domain_network",
        "modify_schema",
        "add_terminal_configuration",
    }
)

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


# ---------------------------------------------------------------------------
# Skills / prompts
# ---------------------------------------------------------------------------


def _read_skill(filename: str) -> str:
    """Read a skill file from the skills directory."""
    skill_path = _SKILLS_DIR / filename
    if not skill_path.exists():
        logger.error("Skill file not found: %s", skill_path)
        raise FileNotFoundError(f"Skill file not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


@datamodel_router.prompt(name="datamodel_apply_workflow")
def datamodel_apply_workflow() -> str:
    """Guide the AI through analyzing and applying a data model change."""
    return _read_skill("datamodel_workflow.md")


# ---------------------------------------------------------------------------
# Core helpers (GIS connection, service resolution)
# ---------------------------------------------------------------------------


def _connect_gis(token: str | None = None, portal_url: str | None = None) -> GIS:
    """Establish an authenticated GIS connection.

    Auth resolves through :func:`psmcp.core.auth.resolve_token`; the portal URL
    resolves from the ``portal_url`` argument or the ``ARCGIS_PORTAL_URL`` env
    var. Honors the ``ARCGIS_VERIFY_SSL`` flag on connect.
    """
    token = resolve_token(token)
    url = portal_url or ARCGIS_PORTAL_URL
    if not token and not url:
        raise ValueError("Set ARCGIS_TOKEN or ARCGIS_PORTAL_URL.")
    kwargs: dict[str, Any] = {"verify_cert": VERIFY_SSL}
    if token:
        kwargs["token"] = token
    started = time.perf_counter()
    gis = GIS(url=url, **kwargs) if url else GIS(**kwargs)
    logger.info(
        "_connect_gis: GIS connection established in %.2f seconds.",
        time.perf_counter() - started,
    )
    return gis


def _service_name_matches(service: Any, wanted: str) -> bool:
    """Return True when an ArcGIS Server ``Service`` matches a requested name.

    Matching is case-insensitive and tolerant of the ``<name>.<type>`` form
    (e.g. ``ElectricNetwork.MapServer``) as well as a bare service name.
    """
    props = getattr(service, "properties", None)
    svc_name = None
    svc_type = None
    if props is not None:
        svc_name = getattr(props, "serviceName", None) or (
            props.get("serviceName") if isinstance(props, dict) else None
        )
        svc_type = getattr(props, "type", None) or (
            props.get("type") if isinstance(props, dict) else None
        )
    if not svc_name:
        return False
    wanted_l = wanted.strip().lower()
    candidates = {svc_name.lower()}
    if svc_type:
        candidates.add(f"{svc_name}.{svc_type}".lower())
    return wanted_l in candidates


def _iter_admin_services(gis: GIS) -> list[Any]:
    """Return the list of ArcGIS Server ``Service`` objects for the portal.

    Resolves every federated ArcGIS Server via ``gis.admin.servers`` and
    aggregates the services across all folders.
    """
    services: list[Any] = []
    servers = gis.admin.servers.list()
    for server in servers:
        manager = server.services
        # Root folder plus every named folder.
        folders = ["/"]
        try:
            folders.extend(f for f in manager.folders if f not in ("/", ""))
        except Exception as exc:  # pragma: no cover - folder listing best-effort
            logger.debug("Could not enumerate service folders: %s", exc)
        seen: set[int] = set()
        for folder in folders:
            for svc in manager.list(folder=folder):
                if id(svc) not in seen:
                    seen.add(id(svc))
                    services.append(svc)
    return services


def _resolve_services(gis: GIS, service_names: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Map requested service names to ``Service`` objects.

    Returns a tuple ``(resolved, missing)`` where ``resolved`` maps the
    requested name to its ``Service`` object and ``missing`` lists names that
    could not be found on any federated server.
    """
    all_services = _iter_admin_services(gis)
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for name in service_names:
        match = next((s for s in all_services if _service_name_matches(s, name)), None)
        if match is None:
            missing.append(name)
        else:
            resolved[name] = match
    return resolved, missing


def _un_manager(service_url: str, token: str | None) -> UtilityNetworkManager:
    """Build a ``UtilityNetworkManager`` for the given feature service URL.

    Resolves the ``UtilityNetworkServer`` admin endpoint from a FeatureServer
    URL and connects it to an authenticated GIS. The ``FeatureLayerCollection``
    confirms the target service is reachable before manager operations run.
    """
    gis = _connect_gis(token)
    # Touch the FLC so an unreachable/invalid service fails fast with a clear error.
    FeatureLayerCollection(service_url, gis)
    un_url = _utility_network_url(service_url)
    return UtilityNetworkManager(url=un_url, gis=gis)


def _utility_network_url(network_service_url: str) -> str:
    """FeatureServer URL -> UtilityNetworkServer URL (manager REST endpoint)."""
    base = network_service_url.rstrip("/")
    lower = base.lower()
    if lower.endswith("/utilitynetworkserver"):
        return base
    if lower.endswith("/featureserver"):
        parent, _ = base.rsplit("/", 1)
        return f"{parent}/UtilityNetworkServer"
    return f"{base}/UtilityNetworkServer"


def _change_operation(change_spec: dict) -> str:
    """Extract the change operation identifier from a change spec."""
    op = change_spec.get("operation") or change_spec.get("op") or change_spec.get("type")
    return str(op).strip().lower() if op else ""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@datamodel_router.tool(name="datamodel_analyze_change")
async def datamodel_analyze_change(
    change_spec: dict,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Analyze a proposed data model change before it is applied.

    Determines whether the change spec is well-formed, whether applying it
    requires republishing the impacted services, and which services are
    impacted.

    Returns ``{valid, requires_republish, impacted_services, notes}``.
    """
    notes: list[str] = []

    if not isinstance(change_spec, dict) or not change_spec:
        return {
            "valid": False,
            "requires_republish": False,
            "impacted_services": [],
            "notes": ["change_spec must be a non-empty object."],
        }

    operation = _change_operation(change_spec)
    if not operation:
        return {
            "valid": False,
            "requires_republish": False,
            "impacted_services": [],
            "notes": ["change_spec is missing an 'operation' identifier."],
        }

    service_url = network_service_url or UTILITY_NETWORK_URL
    if not service_url:
        return {
            "valid": False,
            "requires_republish": False,
            "impacted_services": [],
            "notes": ["Provide network_service_url or set UTILITY_NETWORK_URL."],
        }

    impacted_services: list[str] = []
    explicit = change_spec.get("impacted_services")
    if isinstance(explicit, list):
        impacted_services = [str(s) for s in explicit if s]

    try:
        manager = await asyncio.to_thread(_un_manager, service_url, token)
        # Touch the manager properties to confirm the target UN is reachable and
        # to let the caller relate the change to a live service.
        props = await asyncio.to_thread(lambda: manager.properties)
        if not impacted_services:
            svc_name = None
            if props is not None:
                svc_name = getattr(props, "name", None) or (
                    props.get("name") if isinstance(props, dict) else None
                )
            if svc_name:
                impacted_services = [str(svc_name)]
        notes.append(f"Analyzed change operation '{operation}' against {service_url}.")
    except Exception as exc:
        logger.exception("datamodel_analyze_change failed")
        return {
            "valid": False,
            "requires_republish": False,
            "impacted_services": impacted_services,
            "notes": [f"Could not analyze change against the utility network: {exc}"],
        }

    requires_republish = operation in _REPUBLISH_OPERATIONS
    if requires_republish:
        notes.append(
            "This change alters the published schema and requires republishing "
            "the impacted services; it must not be auto-applied."
        )
    else:
        notes.append(
            "This change can be applied with a stop/change/start service cycle."
        )

    return {
        "valid": True,
        "requires_republish": requires_republish,
        "impacted_services": impacted_services,
        "notes": notes,
    }


@datamodel_router.tool(name="serviceadmin_stop_services")
async def serviceadmin_stop_services(
    service_names: list[str],
    portal_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Stop the given ArcGIS Server services.

    Resolves services from the portal's federated ArcGIS Server(s). Requested
    names may be bare (``ElectricNetwork``) or qualified (``ElectricNetwork.MapServer``).

    Returns ``{stopped: [str], failed: [str]}``.
    """
    if not isinstance(service_names, list) or not service_names:
        return {"stopped": [], "failed": [], "error": "service_names must be a non-empty list."}

    try:
        gis = await asyncio.to_thread(_connect_gis, token, portal_url)
        resolved, missing = await asyncio.to_thread(_resolve_services, gis, service_names)
    except Exception as exc:
        logger.exception("serviceadmin_stop_services connection failed")
        return {"stopped": [], "failed": list(service_names), "error": str(exc)}

    stopped: list[str] = []
    failed: list[str] = list(missing)
    for name, svc in resolved.items():
        try:
            ok = await asyncio.to_thread(svc.stop)
            (stopped if ok else failed).append(name)
        except Exception:
            logger.exception("Failed to stop service %s", name)
            failed.append(name)

    return {"stopped": stopped, "failed": failed}


@datamodel_router.tool(name="datamodel_apply_change")
async def datamodel_apply_change(
    change_spec: dict,
    network_service_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Apply a data model change to the utility network.

    Assumes impacted services have already been stopped by the caller. If the
    change requires republishing (per ``datamodel_analyze_change``), the change
    is NOT applied and an error indication is returned so the caller can guide a
    manual republish.

    Returns ``{applied: bool, details: dict}``.
    """
    if not isinstance(change_spec, dict) or not change_spec:
        return {
            "applied": False,
            "details": {"error": "change_spec must be a non-empty object."},
        }

    operation = _change_operation(change_spec)
    if not operation:
        return {
            "applied": False,
            "details": {"error": "change_spec is missing an 'operation' identifier."},
        }

    if operation in _REPUBLISH_OPERATIONS:
        return {
            "applied": False,
            "details": {
                "error": "This change requires republishing and must not be auto-applied.",
                "requires_republish": True,
                "operation": operation,
            },
        }

    service_url = network_service_url or UTILITY_NETWORK_URL
    if not service_url:
        return {
            "applied": False,
            "details": {"error": "Provide network_service_url or set UTILITY_NETWORK_URL."},
        }

    try:
        manager = await asyncio.to_thread(_un_manager, service_url, token)
        result = await asyncio.to_thread(_apply_change_operation, manager, change_spec)
    except Exception as exc:
        logger.exception("datamodel_apply_change failed")
        return {
            "applied": False,
            "details": {"error": str(exc), "operation": operation},
        }

    return {"applied": True, "details": {"operation": operation, "result": result}}


def _apply_change_operation(manager: UtilityNetworkManager, change_spec: dict) -> Any:
    """Apply a non-republish data model change via the UtilityNetworkManager.

    Delegates to the appropriate ``UtilityNetworkManager`` operation based on the
    change spec's operation identifier. Only hot (non-schema) operations that do
    not require republishing are supported here; schema-altering operations are
    gated out earlier via ``_REPUBLISH_OPERATIONS``. Raises on failure so the
    caller can surface an error indication.
    """
    operation = _change_operation(change_spec)
    payload = change_spec.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    if operation == "enable_topology":
        return manager.enable_topology(**payload)
    if operation == "disable_topology":
        return manager.disable_topology(**payload)
    if operation in ("update_is_connected", "update_connectivity"):
        return manager.update_is_connected()

    raise ValueError(f"Unsupported data model change operation: '{operation}'.")


@datamodel_router.tool(name="serviceadmin_start_services")
async def serviceadmin_start_services(
    service_names: list[str],
    portal_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Start the given ArcGIS Server services.

    Resolves services from the portal's federated ArcGIS Server(s). Requested
    names may be bare (``ElectricNetwork``) or qualified (``ElectricNetwork.MapServer``).

    Returns ``{started: [str], failed: [str]}``.
    """
    if not isinstance(service_names, list) or not service_names:
        return {"started": [], "failed": [], "error": "service_names must be a non-empty list."}

    try:
        gis = await asyncio.to_thread(_connect_gis, token, portal_url)
        resolved, missing = await asyncio.to_thread(_resolve_services, gis, service_names)
    except Exception as exc:
        logger.exception("serviceadmin_start_services connection failed")
        return {"started": [], "failed": list(service_names), "error": str(exc)}

    started: list[str] = []
    failed: list[str] = list(missing)
    for name, svc in resolved.items():
        try:
            ok = await asyncio.to_thread(svc.start)
            (started if ok else failed).append(name)
        except Exception:
            logger.exception("Failed to start service %s", name)
            failed.append(name)

    return {"started": started, "failed": failed}
