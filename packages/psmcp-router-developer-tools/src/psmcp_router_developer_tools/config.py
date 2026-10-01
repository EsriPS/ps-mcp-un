"""Environment-based configuration for the developer-tools router."""

import json
import logging
import os

logger = logging.getLogger(__name__)

GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")

_DEFAULT_CACHE_TTL = 60
try:
    CACHE_TTL_MINUTES: int = int(os.getenv("DEVTOOLS_CACHE_TTL_MINUTES", str(_DEFAULT_CACHE_TTL)))
except ValueError:
    logger.warning(
        "DEVTOOLS_CACHE_TTL_MINUTES is not a valid integer, falling back to %d",
        _DEFAULT_CACHE_TTL,
    )
    CACHE_TTL_MINUTES = _DEFAULT_CACHE_TTL


def load_skill_sources() -> list[dict]:
    """Parse DEVTOOLS_SKILL_SOURCES JSON env var.

    Returns:
        List of source config dicts. Unconfigured means intentionally empty.

    Raises:
        ValueError: Configured JSON is invalid or contains invalid sources.
    """
    raw = os.getenv("DEVTOOLS_SKILL_SOURCES", "")
    if not raw:
        return []
    try:
        sources = json.loads(raw)
        if not isinstance(sources, list):
            raise ValueError("DEVTOOLS_SKILL_SOURCES must be a JSON array")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("Each DEVTOOLS_SKILL_SOURCES entry must be an object")
            source_type = source.get("type")
            required = {"local": ("path",), "github": ("url",), "package": ("package", "path")}
            if source_type not in required:
                raise ValueError(f"Unknown skill source type: {source_type!r}")
            for key in required[source_type]:
                if not isinstance(source.get(key), str) or not source[key].strip():
                    raise ValueError(f"Skill source {source_type!r} requires a nonempty {key!r}")
        return sources
    except json.JSONDecodeError as e:
        raise ValueError("Invalid JSON in DEVTOOLS_SKILL_SOURCES") from e


def load_sample_sources() -> list[dict]:
    """Parse DEVTOOLS_SAMPLE_SOURCES JSON env var.

    Returns:
        List of source config dicts. Empty list on parse failure.
    """
    raw = os.getenv("DEVTOOLS_SAMPLE_SOURCES", "")
    if not raw:
        return []
    try:
        sources = json.loads(raw)
        if not isinstance(sources, list):
            logger.error("DEVTOOLS_SAMPLE_SOURCES must be a JSON array")
            return []
        return sources
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in DEVTOOLS_SAMPLE_SOURCES: %s", e)
        return []
