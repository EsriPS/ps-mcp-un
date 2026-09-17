"""ArcGIS Utility Network integrations router plugin for PS-MCP.

Single service file exposing the ``integration_router`` FastMCP instance. It
provides file/transform tools that turn an exported subnetwork JSON into an
external application schema/format using a caller-supplied field map, plus a
tool that validates such a field map against a sample export.

Both tools operate purely on local files (read an exported subnetwork JSON,
apply ``source_path -> target_path`` transforms, write the output) and never
touch the live UN service, so no ArcGIS auth is required.
"""

import csv
import json
import logging
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

logger = logging.getLogger(__name__)

integration_router = FastMCP(name="UN Integrations")

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Supported output formats for a transform.
_SUPPORTED_TARGET_FORMATS = frozenset({"json", "geojson", "csv"})

# File extension per target format.
_TARGET_FORMAT_EXTENSION = {
    "json": ".json",
    "geojson": ".geojson",
    "csv": ".csv",
}


def _read_skill(filename: str) -> str:
    """Read a skill file from the skills directory."""
    skill_path = _SKILLS_DIR / filename
    if not skill_path.exists():
        logger.error("Skill file not found: %s", skill_path)
        raise FileNotFoundError(f"Skill file not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# region INTERNAL HELPERS
# ---------------------------------------------------------------------------


class _MappingError(ValueError):
    """Raised when an untrusted field map is structurally invalid."""


def _normalize_field_map(field_map: Any) -> dict[str, str]:
    """Validate and normalize an untrusted ``field_map``.

    A field map maps a source dotted-path (in the input record) to a target
    dotted-path (in the output record). Both keys and values must be non-empty
    strings. Returns the validated mapping or raises ``_MappingError`` with a
    human-readable cause. The map is treated as untrusted input.

    Args:
        field_map: The caller-supplied mapping object.

    Returns:
        A shallow copy of the validated mapping.

    Raises:
        _MappingError: If the mapping is not a dict of non-empty str->str pairs.
    """
    if not isinstance(field_map, dict):
        raise _MappingError("field_map must be an object mapping source paths to target paths")
    if not field_map:
        raise _MappingError("field_map must contain at least one source-to-target mapping")

    normalized: dict[str, str] = {}
    for source, target in field_map.items():
        if not isinstance(source, str) or not source.strip():
            raise _MappingError("every field_map source path must be a non-empty string")
        if not isinstance(target, str) or not target.strip():
            raise _MappingError(
                f"field_map target for source '{source}' must be a non-empty string"
            )
        # Reject path segments that are empty (e.g. "a..b" or leading/trailing dots)
        # so a malformed mapping fails fast rather than producing surprising output.
        if any(not seg for seg in source.split(".")):
            raise _MappingError(f"field_map source path '{source}' has an empty path segment")
        if any(not seg for seg in target.split(".")):
            raise _MappingError(f"field_map target path '{target}' has an empty path segment")
        normalized[source] = target
    return normalized


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    """Extract the list of records from a parsed subnetwork export payload.

    Accepts the common export shapes:
      - a bare list of record objects,
      - ``{"records": [...]}``,
      - ``{"features": [...]}`` (Esri feature JSON), or
      - ``{"type": "FeatureCollection", "features": [...]}`` (GeoJSON).

    An empty/zero-record payload yields an empty list (not an error).

    Raises:
        _MappingError: If the payload cannot be interpreted as a record set.
    """
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("records"), list):
            records = payload["records"]
        elif isinstance(payload.get("features"), list):
            records = payload["features"]
        else:
            raise _MappingError(
                "subnetwork JSON must be a list of records or contain a 'records'/'features' list"
            )
    else:
        raise _MappingError("subnetwork JSON must be a JSON object or array")

    result: list[dict[str, Any]] = []
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise _MappingError(f"record at index {idx} is not a JSON object")
        result.append(rec)
    return result


def _get_by_path(record: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve a dotted ``path`` against a record.

    Returns ``(found, value)`` where ``found`` is ``False`` when any segment is
    missing, so callers can distinguish an absent field from a stored ``None``.
    """
    current: Any = record
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return False, None
    return True, current


def _set_by_path(target: dict[str, Any], path: str, value: Any) -> None:
    """Set ``value`` at a dotted ``path`` in ``target``, creating dicts as needed."""
    segments = path.split(".")
    current = target
    for segment in segments[:-1]:
        existing = current.get(segment)
        if not isinstance(existing, dict):
            existing = {}
            current[segment] = existing
        current = existing
    current[segments[-1]] = value


def _transform_record(record: dict[str, Any], field_map: dict[str, str]) -> dict[str, Any]:
    """Apply ``field_map`` to a single record, producing a new output record.

    Source paths absent from the record are skipped (a partially-populated
    source is not an error at the record level).
    """
    out: dict[str, Any] = {}
    for source, target in field_map.items():
        found, value = _get_by_path(record, source)
        if found:
            _set_by_path(out, target, value)
    return out


def _flatten(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict into dotted keys for CSV output."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, dotted))
        else:
            flat[dotted] = value
    return flat


def _resolve_output_path(source_json_path: str, target_format: str) -> Path:
    """Derive the output path for a transform based on the source and format."""
    source = Path(source_json_path)
    extension = _TARGET_FORMAT_EXTENSION[target_format]
    return source.with_name(f"{source.stem}.transformed{extension}")


def _write_json(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"records": records}, indent=2), encoding="utf-8")


def _write_geojson(path: Path, records: list[dict[str, Any]]) -> None:
    features = [
        {
            "type": "Feature",
            "geometry": rec.get("geometry"),
            "properties": {k: v for k, v in rec.items() if k != "geometry"},
        }
        for rec in records
    ]
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    flattened = [_flatten(rec) for rec in records]
    fieldnames: list[str] = []
    for rec in flattened:
        for key in rec:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rec in flattened:
            writer.writerow(rec)


def _write_output(path: Path, records: list[dict[str, Any]], target_format: str) -> None:
    """Write records to ``path`` in the requested format."""
    if target_format == "json":
        _write_json(path, records)
    elif target_format == "geojson":
        _write_geojson(path, records)
    else:  # csv
        _write_csv(path, records)


def _load_subnetwork_json(source_json_path: str) -> list[dict[str, Any]]:
    """Read and parse an exported subnetwork JSON into a list of records.

    Raises:
        _MappingError: If the file is missing, unreadable, or malformed JSON.
    """
    path = Path(source_json_path)
    if not path.is_file():
        raise _MappingError(f"subnetwork JSON not found at path: {source_json_path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _MappingError(f"could not read subnetwork JSON: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _MappingError(f"malformed subnetwork JSON: {exc}") from exc
    return _extract_records(payload)


def _collect_source_paths(records: Iterable[dict[str, Any]]) -> set[str]:
    """Collect every dotted source path present across the sample records."""
    paths: set[str] = set()

    def _walk(obj: Any, prefix: str) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                dotted = f"{prefix}.{key}" if prefix else key
                paths.add(dotted)
                _walk(value, dotted)

    for record in records:
        _walk(record, "")
    return paths


# endregion INTERNAL HELPERS


# ---------------------------------------------------------------------------
# region TOOLS
# ---------------------------------------------------------------------------


@integration_router.tool
async def integration_transform_subnetwork(
    source_json_path: str,
    field_map: dict[str, str],
    target_format: str = "json",
) -> dict[str, Any]:
    """Transform an exported subnetwork JSON into an external schema/format.

    Reads the exported subnetwork JSON at ``source_json_path``, applies the
    ``field_map`` (each entry maps a dotted source path in an input record to a
    dotted target path in the output record), and writes the result next to the
    source file in the requested ``target_format``.

    Behavior:
      - An empty/zero-record input produces a zero-record output (not an error).
      - Malformed JSON, an unreadable/missing source file, an invalid field map,
        or an unsupported target format aborts the transform and produces no
        partial output.

    Args:
        source_json_path: Path to the exported subnetwork JSON file.
        field_map: Untrusted mapping of source dotted-path -> target dotted-path.
        target_format: Output format, one of "json", "geojson", or "csv".

    Returns:
        On success: ``{"output_path", "record_count", "target_format"}``.
        On failure: ``{"error": <cause>}`` with no output written.
    """
    start_time = time.time()
    try:
        fmt = (target_format or "json").lower()
        if fmt not in _SUPPORTED_TARGET_FORMATS:
            return {
                "error": (
                    f"unsupported target_format '{target_format}'; "
                    f"expected one of {sorted(_SUPPORTED_TARGET_FORMATS)}"
                )
            }

        try:
            normalized_map = _normalize_field_map(field_map)
            records = _load_subnetwork_json(source_json_path)
        except _MappingError as exc:
            return {"error": str(exc)}

        transformed = [_transform_record(rec, normalized_map) for rec in records]

        output_path = _resolve_output_path(source_json_path, fmt)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _write_output(output_path, transformed, fmt)
        except OSError as exc:
            # Do not leave a partial file behind on a write failure.
            try:
                if output_path.exists():
                    output_path.unlink()
            except OSError:
                logger.warning("Could not remove partial output file: %s", output_path)
            return {"error": f"could not write transformed output: {exc}"}

        return {
            "output_path": str(output_path.resolve()),
            "record_count": len(transformed),
            "target_format": fmt,
        }
    except Exception as exc:
        # Surface an error shape rather than crashing the tool.
        logger.exception("integration_transform_subnetwork failed")
        return {"error": f"transform failed: {exc}"}
    finally:
        logger.info(
            "integration_transform_subnetwork completed in %.2f seconds",
            time.time() - start_time,
        )


@integration_router.tool
async def integration_validate_mapping(
    field_map: dict[str, str],
    sample_json_path: str,
) -> dict[str, Any]:
    """Validate a field map against a sample exported subnetwork JSON.

    Checks that the untrusted ``field_map`` is structurally sound and that every
    declared source path is present in at least one record of the sample export.

    Args:
        field_map: Untrusted mapping of source dotted-path -> target dotted-path.
        sample_json_path: Path to a sample exported subnetwork JSON file.

    Returns:
        ``{"valid": bool, "unmapped": [str], "errors": [str]}`` where:
          - ``unmapped`` lists field-map source paths not found in the sample, and
          - ``errors`` lists structural problems (bad map, missing/malformed sample).
        ``valid`` is ``True`` only when there are no errors and no unmapped fields.
    """
    start_time = time.time()
    errors: list[str] = []
    unmapped: list[str] = []
    try:
        normalized_map: dict[str, str] | None = None
        try:
            normalized_map = _normalize_field_map(field_map)
        except _MappingError as exc:
            errors.append(str(exc))

        records: list[dict[str, Any]] = []
        try:
            records = _load_subnetwork_json(sample_json_path)
        except _MappingError as exc:
            errors.append(str(exc))

        if normalized_map is not None and not errors:
            present_paths = _collect_source_paths(records)
            unmapped = [source for source in normalized_map if source not in present_paths]

        valid = not errors and not unmapped
        return {"valid": valid, "unmapped": unmapped, "errors": errors}
    except Exception as exc:
        # Surface an error shape rather than crashing the tool.
        logger.exception("integration_validate_mapping failed")
        return {"valid": False, "unmapped": unmapped, "errors": [f"validation failed: {exc}"]}
    finally:
        logger.info(
            "integration_validate_mapping completed in %.2f seconds",
            time.time() - start_time,
        )


# endregion TOOLS


@integration_router.prompt(name="integration_transform_workflow")
def integration_transform_workflow() -> str:
    """Guide the AI through validating a mapping and transforming a subnetwork export."""
    return _read_skill("integration_workflow.md")
