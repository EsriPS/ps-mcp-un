"""Subnetwork router plugin for PS-MCP."""

from .subnetwork_service import subnetwork_router

try:
    from ._version import __version__  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "subnetwork_router"]
