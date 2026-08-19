"""Shared core utilities for the PS-MCP server and router plugins.

Public re-exports so router authors can write either::

    from psmcp.core import resolve_token, setup_logging
    # or, for the auth-related symbols specifically:
    from psmcp.core.auth import resolve_token, ArcGISAuthProvider

The submodule paths (``psmcp.core.auth``, ``psmcp.core.config``,
``psmcp.core.utils``) are stable; treat anything imported from inside those
modules as the public API.
"""

from psmcp.core.auth import (
    ArcGISAuthProvider,
    ArcGISTokenVerifier,
    AuthenticationError,
    resolve_token,
)
from psmcp.core.config import (
    add_router,
    get_config_dir,
    load_enabled_routers,
    remove_router,
    save_enabled_routers,
)
from psmcp.core.utils import setup_logging

__all__ = [
    "ArcGISAuthProvider",
    "ArcGISTokenVerifier",
    "AuthenticationError",
    "add_router",
    "get_config_dir",
    "load_enabled_routers",
    "remove_router",
    "resolve_token",
    "save_enabled_routers",
    "setup_logging",
]
