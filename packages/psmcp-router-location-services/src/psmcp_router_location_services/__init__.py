"""location_services router plugin for PS-MCP."""

from .location_services import location_services_router

try:
    from ._version import __version__  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "location_services_router"]
