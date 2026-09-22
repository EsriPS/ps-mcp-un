"""ArcGIS Utility Network version & editing router plugin for PS-MCP.

Single service file exposing the ``version_editing_router`` FastMCP instance and
its tools. All utility network operations go through
``arcgis.features._utility.UtilityNetworkManager`` and
``arcgis.features.FeatureLayerCollection`` on an ``arcgis.gis.GIS`` connection,
with branch-version management via ``arcgis.features._version.VersionManager``.
Auth is resolved through ``psmcp.core.auth.resolve_token`` and the service URL is
taken from the ``UTILITY_NETWORK_URL`` environment variable or a
``network_service_url`` argument.

Tool-level failures return an ``{"error": ...}`` shape (mirroring the
``psmcp-router-utilitynetwork`` router); missing service configuration raises
``ValueError`` so the caller learns to provide the URL.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from arcgis.features import FeatureLayer, FeatureLayerCollection
from arcgis.features._utility import UtilityNetworkManager
from arcgis.features._version import VersionManager
from arcgis.gis import GIS
from dotenv import load_dotenv
from fastmcp import FastMCP

from psmcp.core.auth import resolve_token

load_dotenv()

logger = logging.getLogger(__name__)

version_editing_router = FastMCP(name="UN Version & Editing")

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL")
VERIFY_SSL = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() != "false"
UTILITY_NETWORK_URL = os.getenv("UTILITY_NETWORK_URL")

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Access values accepted by the version management server (branch versioning).
_ACCESS_TO_PERMISSION = {
    "private": "private",
    "protected": "protected",
    "public": "public",
}


def _read_skill(filename: str) -> str:
    """Read a skill file from the skills directory."""
    skill_path = _SKILLS_DIR / filename
    if not skill_path.exists():
        logger.error("Skill file not found: %s", skill_path)
        raise FileNotFoundError(f"Skill file not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Core helpers (GIS connection, URL building, version + UN managers)
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


def _version_management_url(network_service_url: str) -> str:
    """FeatureServer URL -> VersionManagementServer URL."""
    base = network_service_url.rstrip("/")
    if base.lower().endswith("/versionmanagementserver"):
        return base
    if base.lower().endswith("/featureserver"):
        parent, _ = base.rsplit("/", 1)
        return f"{parent}/VersionManagementServer"
    return f"{base}/VersionManagementServer"


def _get_feature_layer_collection(gis: GIS, service_url: str) -> FeatureLayerCollection:
    """Return the FeatureLayerCollection for the service."""
    return FeatureLayerCollection(service_url.rstrip("/"), gis=gis)


def _get_version_manager(gis: GIS, service_url: str) -> VersionManager:
    """Return the VersionManager for the service's version management server."""
    return VersionManager(_version_management_url(service_url), gis=gis)


def _get_un_manager(
    gis: GIS, service_url: str, version_name: str | None = None
) -> UtilityNetworkManager:
    """Return the UtilityNetworkManager for the service, optionally version-scoped.

    The arcgis ``UtilityNetworkManager(url, version=...)`` constructor requires
    ``version`` to be a *Version object* (it reads ``version.properties.versionName``
    and ``version._guid``), NOT a version-name string. Passing a bare name raises
    ``'str' object has no attribute 'properties'``. So when a named version is
    requested we resolve it to its Version object first via the VersionManager.
    ``None`` or the default version means unversioned (``version=None``).
    """
    version_obj = None
    if version_name and str(version_name).lower() not in ("default", "sde.default", "dbo.default"):
        vm = _get_version_manager(gis, service_url)
        version_obj = _find_version(vm, version_name)
        if version_obj is None:
            raise ValueError(f"Branch version '{version_name}' was not found.")
    return UtilityNetworkManager(_utility_network_url(service_url), version=version_obj, gis=gis)


def _find_version(version_manager: VersionManager, version_name: str) -> Any:
    """Locate a branch version by name, returning None when not found."""
    getter = getattr(version_manager, "get_by_name", None)
    if callable(getter):
        try:
            found = getter(version_name)
            if found:
                return found
        except Exception:  # pragma: no cover - fall through to search
            pass
    target = version_name.lower()
    try:
        for version in version_manager.all:
            props = getattr(version, "properties", {}) or {}
            name = _read_value(props, "versionName") or _read_value(props, "name") or ""
            if str(name).lower() == target or str(name).lower().endswith(f".{target}"):
                return version
    except Exception:  # pragma: no cover - defensive
        return None
    return None


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


def _find_layer(flc: FeatureLayerCollection, layer_id: Any) -> FeatureLayer | None:
    """Find a layer or table on the FeatureLayerCollection by id or name."""
    for group in (getattr(flc, "layers", []) or [], getattr(flc, "tables", []) or []):
        for layer in group:
            props = getattr(layer, "properties", {}) or {}
            lid = _read_value(props, "id")
            lname = _read_value(props, "name")
            if lid is not None and str(lid) == str(layer_id):
                return layer
            if lname is not None and str(lname).lower() == str(layer_id).lower():
                return layer
    return None


# ---------------------------------------------------------------------------
# Prompt / skill exposure
# ---------------------------------------------------------------------------


@version_editing_router.prompt(name="version_editing_governance_loop")
def version_editing_governance_loop() -> str:
    """Guide the AI through the branch-version edit, validate, and promote loop."""
    return _read_skill("version_editing_workflow.md")


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@version_editing_router.tool(name="version_create_branch")
async def version_create_branch(
    version_name: str,
    access: str = "private",
    description: str = "",
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Create a branch version for editing.

    ``access`` is one of ``private``, ``protected``, or ``public``.
    Returns ``{version_name, version_guid, access}``. On failure returns an
    ``{"error": ...}`` shape and creates no partial version.
    """
    service_url = _resolve_service_url(network_service_url)
    permission = _ACCESS_TO_PERMISSION.get(access.lower())
    if permission is None:
        return {
            "error": (
                f"Invalid access '{access}'. "
                f"Valid values: {', '.join(sorted(_ACCESS_TO_PERMISSION))}."
            )
        }

    def _create() -> dict[str, Any]:
        gis = _connect_gis()
        vm = _get_version_manager(gis, service_url)
        result = vm.create(version_name, permission=permission, description=description)
        return result if isinstance(result, dict) else {"success": bool(result)}

    try:
        result = await asyncio.to_thread(_create)
    except Exception as exc:  # pragma: no cover - network/runtime failure
        logger.exception("version_create_branch failed for %s", version_name)
        return {"error": f"Branch version creation failed: {exc}"}

    if not result.get("success", True):
        return {"error": f"Branch version creation failed: {result.get('error', result)}"}

    version_info = result.get("versionInfo") or {}
    created_name = version_info.get("versionName") or result.get("versionName") or version_name
    version_guid = version_info.get("versionGuid") or result.get("versionGuid")
    return {
        "version_name": created_name,
        "version_guid": version_guid,
        "access": access.lower(),
    }


@version_editing_router.tool(name="version_take_control")
async def version_take_control(
    version_name: str,
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Take ownership/control of a branch version for editing.

    Starts an edit session (acquiring the version lock). Returns
    ``{version_name, controlled: bool}``; on conflict or failure returns an
    ``{"error": ...}`` shape with ``controlled`` set to ``False``.
    """
    service_url = _resolve_service_url(network_service_url)

    def _take_control() -> dict[str, Any]:
        gis = _connect_gis()
        vm = _get_version_manager(gis, service_url)
        version = _find_version(vm, version_name)
        if version is None:
            return {"__not_found__": True}
        version.start_reading()
        version.start_editing()
        return {"__controlled__": True}

    try:
        result = await asyncio.to_thread(_take_control)
    except Exception as exc:
        logger.exception("version_take_control failed for %s", version_name)
        return {
            "error": f"Could not take control of version '{version_name}': {exc}",
            "version_name": version_name,
            "controlled": False,
        }

    if result.get("__not_found__"):
        return {
            "error": f"Branch version '{version_name}' was not found.",
            "version_name": version_name,
            "controlled": False,
        }

    return {"version_name": version_name, "controlled": True}


@version_editing_router.tool(name="version_apply_edits")
async def version_apply_edits(
    version_name: str,
    edits: list[dict],
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Apply attribute/geometry edits to a branch version.

    ``edits`` is a list of ``{layer_id, adds?, updates?, deletes?}`` entries.
    Returns ``{applied: int, dirty_areas_created: bool}``. On failure the branch
    version state is preserved and an ``{"error": ...}`` shape identifies the
    failing edits.
    """
    service_url = _resolve_service_url(network_service_url)
    if not edits:
        return {"applied": 0, "dirty_areas_created": False}

    def _apply() -> dict[str, Any]:
        gis = _connect_gis()
        vm = _get_version_manager(gis, service_url)
        version = _find_version(vm, version_name)
        if version is None:
            return {"__not_found__": True}
        flc = _get_feature_layer_collection(gis, service_url)
        version.start_reading()
        version.start_editing()
        applied = 0
        failures: list[dict[str, Any]] = []
        try:
            for edit in edits:
                layer_id = edit.get("layer_id")
                layer = _find_layer(flc, layer_id)
                if layer is None:
                    failures.append({"layer_id": layer_id, "error": "layer not found"})
                    continue
                result = version.edit(
                    layer,
                    adds=edit.get("adds"),
                    updates=edit.get("updates"),
                    deletes=edit.get("deletes"),
                    use_global_ids=edit.get("use_global_ids", False),
                    rollback_on_failure=True,
                )
                applied += _count_applied(result)
                edit_failures = _edit_failures(result, layer_id)
                if edit_failures:
                    failures.extend(edit_failures)
        finally:
            try:
                version.stop_editing(save=not failures)
            except Exception:  # pragma: no cover - best-effort session close
                logger.warning("version_apply_edits: stop_editing failed", exc_info=True)
        return {"applied": applied, "failures": failures}

    try:
        result = await asyncio.to_thread(_apply)
    except Exception as exc:
        logger.exception("version_apply_edits failed for %s", version_name)
        return {"error": f"Applying edits failed: {exc}"}

    if result.get("__not_found__"):
        return {"error": f"Branch version '{version_name}' was not found."}

    failures = result.get("failures") or []
    if failures:
        return {
            "error": "One or more edits failed to apply; branch version preserved.",
            "failed_edits": failures,
            "applied": 0,
        }

    applied = result.get("applied", 0)
    return {"applied": applied, "dirty_areas_created": applied > 0}


def _count_applied(edit_result: Any) -> int:
    """Count successful add/update/delete results from an edit() response."""
    if not isinstance(edit_result, dict):
        return 0
    total = 0
    for key in ("addResults", "updateResults", "deleteResults"):
        for entry in edit_result.get(key, []) or []:
            if isinstance(entry, dict) and entry.get("success", False):
                total += 1
    return total


def _edit_failures(edit_result: Any, layer_id: Any) -> list[dict[str, Any]]:
    """Extract per-feature failures from an edit() response."""
    failures: list[dict[str, Any]] = []
    if not isinstance(edit_result, dict):
        return failures
    for key in ("addResults", "updateResults", "deleteResults"):
        for entry in edit_result.get(key, []) or []:
            if isinstance(entry, dict) and not entry.get("success", True):
                failures.append(
                    {
                        "layer_id": layer_id,
                        "object_id": entry.get("objectId"),
                        "operation": key,
                        "error": _read_value(entry.get("error", {}), "description")
                        or entry.get("error", "edit failed"),
                    }
                )
    return failures


def _validate_topology_versioned(
    gis: GIS,
    service_url: str,
    version_name: str,
    envelope: dict | None = None,
) -> dict[str, Any]:
    """Validate topology for a branch version inside a managed read session.

    ``UtilityNetworkManager.validate_topology`` on a versioned network needs the
    version's server-side read session to be active, otherwise the server returns
    "Unable to resume a server side session". For a named (non-default) version we
    resolve the Version object, ``start_reading`` on it, validate, then always
    ``stop_reading``. The default/unversioned case validates directly.
    """
    is_named = bool(version_name) and str(version_name).lower() not in (
        "default",
        "sde.default",
        "dbo.default",
    )

    def _extent(un_mgr: UtilityNetworkManager) -> dict[str, Any]:
        # Prefer the caller's envelope, then the feature service's real extent,
        # then the UN manager's extent, then a world fallback.
        return (
            envelope
            or _service_full_extent(gis, service_url)
            or _full_extent(un_mgr)
        )

    if not is_named:
        # Default/unversioned: no read session required.
        un = UtilityNetworkManager(_utility_network_url(service_url), version=None, gis=gis)
        return un.validate_topology(envelope=_extent(un)) or {}

    # Named version: build ONE Version object and use it for BOTH the read
    # session and the UtilityNetworkManager, so they share the same session id
    # (``version._guid``). Building the UN manager from a *different* Version
    # object (e.g. a second VersionManager lookup) yields a mismatched session id
    # and the server rejects validate with "Unable to resume a server side
    # session".
    vm = _get_version_manager(gis, service_url)
    version = _find_version(vm, version_name)
    if version is None:
        return {"error": f"Branch version '{version_name}' was not found."}

    un = UtilityNetworkManager(
        _utility_network_url(service_url), version=version, gis=gis
    )
    extent = _extent(un)

    started = False
    try:
        try:
            version.start_reading()
            started = True
        except Exception:  # pragma: no cover - some services auto-manage reading
            started = False
        return un.validate_topology(envelope=extent) or {}
    finally:
        if started:
            try:
                version.stop_reading()
            except Exception:  # pragma: no cover - best-effort session close
                logger.warning("validate: stop_reading failed", exc_info=True)


@version_editing_router.tool(name="network_validate_topology")
async def network_validate_topology(
    version_name: str,
    envelope: dict | None = None,
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Validate network topology over the dirty areas of a branch version.

    When ``envelope`` is omitted the full spatial extent is validated. Returns
    ``{validated, has_errors, error_count, errors: [{rule, feature_id, geometry,
    description}]}``.
    """
    service_url = _resolve_service_url(network_service_url)

    def _validate() -> dict[str, Any]:
        gis = _connect_gis()
        return _validate_topology_versioned(gis, service_url, version_name, envelope)

    try:
        raw = await asyncio.to_thread(_validate)
    except Exception as exc:
        logger.exception("network_validate_topology failed for %s", version_name)
        return {"error": f"Topology validation failed: {exc}"}

    if isinstance(raw, dict) and "error" in raw:
        return {"error": f"Topology validation failed: {raw.get('error')}"}

    errors = _parse_topology_errors(raw)
    return {
        "validated": True,
        "has_errors": len(errors) > 0,
        "error_count": len(errors),
        "errors": errors,
    }


def _service_full_extent(gis: GIS, service_url: str) -> dict[str, Any] | None:
    """Return the FeatureLayerCollection's full extent (in its own SR).

    The UtilityNetworkServer's ``properties.fullExtent`` is often absent, which
    is why validate must use the feature service's real extent — a world
    envelope in the wrong spatial reference does not overlap the dirty areas and
    the server reports "a dirty area is not present within the ... input extent."
    """
    try:
        flc = _get_feature_layer_collection(gis, service_url)
        props = getattr(flc, "properties", {}) or {}
        extent = _read_value(props, "fullExtent") or _read_value(props, "initialExtent")
        if isinstance(extent, dict) and "xmin" in extent:
            return extent
        # PropertyMap objects: coerce to a plain dict when possible.
        if extent is not None and hasattr(extent, "xmin"):
            return {
                "xmin": extent.xmin,
                "ymin": extent.ymin,
                "xmax": extent.xmax,
                "ymax": extent.ymax,
                "spatialReference": _read_value(extent, "spatialReference"),
            }
    except Exception:  # pragma: no cover - defensive
        logger.warning("could not read service full extent", exc_info=True)
    return None


def _full_extent(un_manager: UtilityNetworkManager) -> dict[str, Any]:
    """Return the full-extent envelope for the utility network service."""
    props = getattr(un_manager, "properties", {}) or {}
    extent = _read_value(props, "fullExtent") or _read_value(props, "extent")
    if isinstance(extent, dict):
        return extent
    # Fall back to a world envelope; the server clips to actual dirty areas.
    return {
        "xmin": -20037508.34,
        "ymin": -20037508.34,
        "xmax": 20037508.34,
        "ymax": 20037508.34,
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
    }


def _parse_topology_errors(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize validate_topology output into the documented error shape."""
    if not isinstance(raw, dict):
        return []
    candidates = (
        raw.get("errors") or raw.get("validationErrors") or raw.get("dirtyAreaErrors") or []
    )
    # Some responses nest errors under moment/edits payloads.
    if not candidates and isinstance(raw.get("edits"), list):
        for edit in raw["edits"]:
            if isinstance(edit, dict) and edit.get("errors"):
                candidates = edit["errors"]
                break

    normalized: list[dict[str, Any]] = []
    for err in candidates or []:
        if not isinstance(err, dict):
            continue
        normalized.append(
            {
                "rule": err.get("rule")
                or err.get("ruleType")
                or err.get("errorType")
                or err.get("code"),
                "feature_id": err.get("feature_id")
                or err.get("featureId")
                or err.get("globalId")
                or err.get("objectId"),
                "geometry": err.get("geometry"),
                "description": err.get("description")
                or err.get("message")
                or err.get("errorMessage"),
            }
        )
    return normalized


@version_editing_router.tool(name="version_reconcile_post")
async def version_reconcile_post(
    version_name: str,
    target: str = "default",
    abort_if_conflicts: bool = True,
    with_post: bool = True,
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Reconcile a branch version, and optionally post (promote) it to target.

    When ``abort_if_conflicts`` is true and reconcile reports conflicts, the post
    is aborted and the version remains a branch. When ``with_post`` is false the
    version is reconciled only (brought up to date with ``default``) and is NOT
    promoted — useful for the Version Management Agent's reconcile-only mode.
    Returns ``{reconciled, posted, conflicts}``.
    """
    service_url = _resolve_service_url(network_service_url)
    if target.lower() != "default":
        return {"error": f"Unsupported reconcile target '{target}'. Only 'default' is supported."}

    def _reconcile_post() -> dict[str, Any]:
        gis = _connect_gis()
        vm = _get_version_manager(gis, service_url)
        version = _find_version(vm, version_name)
        if version is None:
            return {"__not_found__": True}
        version.start_reading()
        version.start_editing()
        reconcile_result = version.reconcile(
            end_with_conflict=not abort_if_conflicts,
            with_post=False,
            conflict_detection="byObject",
        )
        conflicts = _conflict_count(reconcile_result, version)
        if conflicts > 0 and abort_if_conflicts:
            try:
                version.stop_editing(save=False)
            except Exception:  # pragma: no cover
                logger.warning("reconcile abort: stop_editing failed", exc_info=True)
            return {"reconciled": True, "posted": False, "conflicts": conflicts}
        if not with_post:
            # Reconcile-only: bring the branch up to date without promoting it.
            try:
                version.stop_editing(save=True)
            except Exception:  # pragma: no cover
                logger.warning("reconcile-only: stop_editing failed", exc_info=True)
            return {"reconciled": True, "posted": False, "conflicts": conflicts}
        post_result = version.post()
        posted = _is_success(post_result)
        try:
            version.stop_editing(save=True)
        except Exception:  # pragma: no cover
            logger.warning("post: stop_editing failed", exc_info=True)
        return {"reconciled": True, "posted": posted, "conflicts": conflicts}

    try:
        result = await asyncio.to_thread(_reconcile_post)
    except Exception as exc:
        logger.exception("version_reconcile_post failed for %s", version_name)
        return {"error": f"Reconcile/post failed: {exc}"}

    if result.get("__not_found__"):
        return {"error": f"Branch version '{version_name}' was not found."}
    return result


def _conflict_count(reconcile_result: Any, version: Any) -> int:
    """Determine the conflict count from a reconcile response or the version."""
    if isinstance(reconcile_result, dict):
        if "conflicts" in reconcile_result:
            value = reconcile_result["conflicts"]
            if isinstance(value, bool):
                return 1 if value else 0
            if isinstance(value, int):
                return value
            if isinstance(value, list):
                return len(value)
        if reconcile_result.get("hasConflicts"):
            try:
                conflicts = version.conflicts()
                if isinstance(conflicts, list):
                    return len(conflicts)
            except Exception:  # pragma: no cover
                return 1
            return 1
    return 0


def _is_success(result: Any) -> bool:
    """Interpret an ArcGIS operation result as a boolean success."""
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        if "success" in result:
            return bool(result["success"])
        if "moment" in result or "postResults" in result:
            return True
        return "error" not in result
    return bool(result)


@version_editing_router.tool(name="version_list_branches")
async def version_list_branches(
    include_default: bool = False,
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """List branch versions and their states.

    When ``include_default`` is false the ``sde.DEFAULT`` version is omitted.
    Returns ``{versions: [{name, owner, access, has_dirty_areas}]}``.
    """
    service_url = _resolve_service_url(network_service_url)

    def _list() -> list[dict[str, Any]]:
        gis = _connect_gis()
        vm = _get_version_manager(gis, service_url)
        versions: list[dict[str, Any]] = []
        for version in vm.all:
            props = getattr(version, "properties", {}) or {}
            name = _read_value(props, "versionName") or _read_value(props, "name") or ""
            if not include_default and str(name).lower().endswith(".default"):
                continue
            versions.append(
                {
                    "name": name,
                    "owner": _read_value(props, "versionOwner") or _read_value(props, "owner"),
                    "access": _read_value(props, "access")
                    or _read_value(props, "accessPermission"),
                    "has_dirty_areas": _has_dirty_areas(version, props),
                }
            )
        return versions

    try:
        versions = await asyncio.to_thread(_list)
    except Exception as exc:
        logger.exception("version_list_branches failed")
        return {"error": f"Listing branch versions failed: {exc}"}

    return {"versions": versions}


def _has_dirty_areas(version: Any, props: dict[str, Any]) -> bool:
    """Best-effort determination of whether a version has dirty areas."""
    for key in ("hasDirtyAreas", "isDirty", "dirty"):
        value = _read_value(props, key)
        if isinstance(value, bool):
            return value
    modified = _read_value(props, "modifiedDate") or _read_value(props, "commonAncestorDate")
    created = _read_value(props, "creationDate") or _read_value(props, "createdDate")
    if isinstance(modified, (int, float)) and isinstance(created, (int, float)):
        return modified > created
    return False


@version_editing_router.tool(name="version_edit_summary")
async def version_edit_summary(
    version_name: str,
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Summarize the edits pending in a branch version.

    Reports how much has changed in ``version_name`` relative to the default
    version, plus the number of dirty areas awaiting validation:

    * ``features_edited`` — count of features that differ from ``default``
      (inserts + updates + deletes) across all layers/tables, computed via the
      version's ``differences`` operation (the ArcGIS version read-session is
      managed for you).
    * ``dirty_areas`` — count of features in the Utility Network *Dirty Areas*
      layer for this version (areas edited since the last validate).
    * ``has_dirty_areas`` — convenience boolean (``dirty_areas > 0``).
    * ``error_count`` — number of network topology errors in the version
      (validated read-only over the full extent). ``0`` means clean.
    * ``has_errors`` — convenience boolean (``error_count > 0``).

    Read-only: it opens a read session, reads differences, validates topology,
    and closes without editing. Returns ``{version_name, features_edited,
    dirty_areas, has_dirty_areas, error_count, has_errors}`` or an
    ``{"error": ...}`` shape on failure. A count may be ``null`` if the server
    does not support that query on this service.
    """
    service_url = _resolve_service_url(network_service_url)

    def _summarize() -> dict[str, Any]:
        gis = _connect_gis()
        vm = _get_version_manager(gis, service_url)
        version = _find_version(vm, version_name)
        if version is None:
            return {"__not_found__": True}

        features_edited = _count_version_differences(version)
        dirty_areas = _count_dirty_areas(gis, service_url, version_name)
        error_count = _count_topology_errors(gis, service_url, version_name)
        return {
            "features_edited": features_edited,
            "dirty_areas": dirty_areas,
            "error_count": error_count,
        }

    try:
        result = await asyncio.to_thread(_summarize)
    except Exception as exc:
        logger.exception("version_edit_summary failed for %s", version_name)
        return {"error": f"Version edit summary failed: {exc}"}

    if result.get("__not_found__"):
        return {"error": f"Branch version '{version_name}' was not found."}

    dirty_areas = result.get("dirty_areas")
    error_count = result.get("error_count")
    return {
        "version_name": version_name,
        "features_edited": result.get("features_edited"),
        "dirty_areas": dirty_areas,
        "has_dirty_areas": bool(dirty_areas) if dirty_areas is not None else None,
        "error_count": error_count,
        "has_errors": bool(error_count) if error_count is not None else None,
    }


def _count_topology_errors(gis: GIS, service_url: str, version_name: str) -> int | None:
    """Count network topology errors in a version (read-only validate).

    Runs ``validate_topology`` (inside the version's read session, via
    :func:`_validate_topology_versioned`) over the full extent and counts the
    normalized errors. Returns ``None`` when validation is unavailable on this
    service so callers can distinguish "unknown" from "clean" (``0``).
    """
    try:
        raw = _validate_topology_versioned(gis, service_url, version_name)
        if isinstance(raw, dict) and "error" in raw:
            return None
        return len(_parse_topology_errors(raw))
    except Exception:  # pragma: no cover - validate unsupported/failed
        logger.warning("topology validate unavailable for %s", version_name, exc_info=True)
        return None


def _count_version_differences(version: Any) -> int | None:
    """Count features that differ from default (inserts + updates + deletes).

    Uses the version's ``differences`` (objectIds) operation inside a managed
    read session. Returns ``None`` if differences are unavailable on this
    service. The read session is always closed.
    """
    started = False
    try:
        try:
            version.start_reading()
            started = True
        except Exception:  # pragma: no cover - some services auto-manage reading
            started = False
        diffs = version.differences(result_type="objectIds")
        return _sum_difference_object_ids(diffs)
    except Exception:  # pragma: no cover - differences unsupported/failed
        logger.warning("version differences unavailable", exc_info=True)
        return None
    finally:
        if started:
            try:
                version.stop_reading()
            except Exception:  # pragma: no cover - best-effort session close
                logger.warning("version_edit_summary: stop_reading failed", exc_info=True)


def _sum_difference_object_ids(diffs: Any) -> int:
    """Sum inserted/updated/deleted object ids across all layers in a diff result.

    Tolerant of the shape variants ArcGIS returns: a top-level list of per-layer
    dicts, or a dict wrapping such a list under ``differences``/``layers``. Each
    per-layer entry carries object-id lists under ``inserts``/``updates``/
    ``deletes`` (or the ``*ObjectIds`` variants).
    """
    layers: Any
    if isinstance(diffs, dict):
        layers = diffs.get("differences") or diffs.get("layers") or diffs.get("features") or []
    elif isinstance(diffs, list):
        layers = diffs
    else:
        layers = []

    total = 0
    for layer in layers or []:
        if not isinstance(layer, dict):
            continue
        for key in (
            "inserts",
            "updates",
            "deletes",
            "insertObjectIds",
            "updateObjectIds",
            "deleteObjectIds",
        ):
            ids = layer.get(key)
            if isinstance(ids, list):
                total += len(ids)
            elif isinstance(ids, int):
                total += ids
    return total


def _count_dirty_areas(gis: GIS, service_url: str, version_name: str) -> int | None:
    """Count features in the UN Dirty Areas layer scoped to ``version_name``.

    Locates the layer named 'Dirty Areas' on the FeatureLayerCollection and runs
    a count-only query with the ``gdbVersion`` set to the branch version. Returns
    ``None`` when the layer cannot be found or the count query fails.
    """
    try:
        flc = _get_feature_layer_collection(gis, service_url)
        dirty_layer = _find_layer(flc, "Dirty Areas")
        if dirty_layer is None:
            return None
        result = dirty_layer.query(
            where="1=1",
            return_count_only=True,
            gdb_version=version_name,
        )
        if isinstance(result, int):
            return result
        if isinstance(result, dict):
            count = result.get("count")
            return int(count) if isinstance(count, (int, float)) else None
        # arcgis may return a FeatureSet-like object exposing .count
        count_attr = getattr(result, "count", None)
        return int(count_attr) if isinstance(count_attr, (int, float)) else None
    except Exception:  # pragma: no cover - service without dirty-areas layer
        logger.warning("dirty-area count unavailable for %s", version_name, exc_info=True)
        return None


@version_editing_router.tool(name="quality_fix_errors")
async def quality_fix_errors(
    version_name: str,
    error_ids: list[str] | None = None,
    strategy: str = "auto",
    network_service_url: str | None = None,
) -> dict[str, Any]:
    """Apply PSMCP-supported fixes for validation/topology errors.

    ``strategy`` is ``auto`` (apply supported fixes then re-validate) or
    ``suggest-only`` (report actions without applying). Returns
    ``{fixed: int, remaining: int, actions: [...]}``.
    """
    service_url = _resolve_service_url(network_service_url)
    if strategy not in ("auto", "suggest-only"):
        return {"error": (f"Invalid strategy '{strategy}'. Valid values: 'auto', 'suggest-only'.")}

    def _fix() -> dict[str, Any]:
        gis = _connect_gis()
        un = _get_un_manager(gis, service_url, version_name)
        extent = _full_extent(un)

        # Assess current errors first.
        before = _parse_topology_errors(un.validate_topology(envelope=extent) or {})
        targeted = _select_target_errors(before, error_ids)

        actions: list[dict[str, Any]] = []
        for err in targeted:
            actions.append(
                {
                    "feature_id": err.get("feature_id"),
                    "rule": err.get("rule"),
                    "action": "revalidate-dirty-area",
                    "applied": strategy == "auto",
                }
            )

        if strategy == "suggest-only":
            return {"fixed": 0, "remaining": len(before), "actions": actions}

        # 'auto': the only PSMCP-supported fix primitive is re-running validation
        # over the dirty areas so the server can clear transient/derivable errors.
        after = _parse_topology_errors(un.validate_topology(envelope=extent) or {})
        fixed = max(0, len(before) - len(after))
        return {"fixed": fixed, "remaining": len(after), "actions": actions}

    try:
        result = await asyncio.to_thread(_fix)
    except Exception as exc:
        logger.exception("quality_fix_errors failed for %s", version_name)
        return {"error": f"Error-fix pass failed: {exc}"}

    return result


def _select_target_errors(
    errors: list[dict[str, Any]], error_ids: list[str] | None
) -> list[dict[str, Any]]:
    """Filter the error list to the requested ids, or all when none given."""
    if not error_ids:
        return errors
    wanted = {str(eid) for eid in error_ids}
    return [e for e in errors if str(e.get("feature_id")) in wanted]
