"""Configuration directory and ``routers.json`` management.

Resolution order for the config directory:

    1. ``PSMCP_CONFIG_DIR`` environment variable
    2. ``.psmcp/`` relative to the current working directory
    3. ``~/.psmcp/`` (user home)
"""

from __future__ import annotations

import json
import logging
import os
import pathlib

logger = logging.getLogger(__name__)

_ROUTERS_FILE = "routers.json"


def get_config_dir() -> pathlib.Path:
    """Return the resolved config directory, creating it if needed."""
    env = os.getenv("PSMCP_CONFIG_DIR")
    if env:
        path = pathlib.Path(env)
    else:
        local = pathlib.Path.cwd() / ".psmcp"
        path = local if local.is_dir() else pathlib.Path.home() / ".psmcp"

    path.mkdir(parents=True, exist_ok=True)
    return path


def _routers_path() -> pathlib.Path:
    return get_config_dir() / _ROUTERS_FILE


def load_enabled_routers() -> list[str] | None:
    """Load enabled router names from ``routers.json``.

    Returns ``None`` if the file does not exist (meaning "enable all
    discovered routers"). Returns a list of router entry-point names if the
    file exists and is valid; returns ``None`` again on parse errors after
    logging a warning.
    """
    path = _routers_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("enabled")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return None


def save_enabled_routers(names: list[str]) -> None:
    """Persist the enabled router list to ``routers.json``."""
    path = _routers_path()
    payload = {"enabled": sorted(set(names))}
    path.write_text(json.dumps(payload, indent=2) + "\n")
    logger.info("Saved enabled routers to %s", path)


def add_router(name: str) -> list[str]:
    """Enable a router by name and return the updated list."""
    current = load_enabled_routers() or []
    if name not in current:
        current.append(name)
    save_enabled_routers(current)
    return current


def remove_router(name: str, all_discovered: list[str] | None = None) -> list[str]:
    """Disable a router by name and return the updated list.

    If no ``routers.json`` exists yet (the "enable all" default state),
    ``all_discovered`` is used as the starting set so disabling one router
    doesn't accidentally disable everything else.
    """
    current = load_enabled_routers()
    if current is None:
        current = list(all_discovered) if all_discovered else []
    current = [r for r in current if r != name]
    save_enabled_routers(current)
    return current
