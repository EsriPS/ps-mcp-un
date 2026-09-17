"""Data model & service admin router plugin for PS-MCP."""

from .datamodel_service import datamodel_router

try:
    from ._version import __version__  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "datamodel_router"]
