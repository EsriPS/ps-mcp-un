"""feature_service router plugin for PS-MCP."""

from .feature_service import feature_service_router

try:
    from ._version import __version__  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "feature_service_router"]
