"""Version and editing router plugin for PS-MCP."""

from .version_editing_service import version_editing_router

try:
    from ._version import __version__  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "version_editing_router"]
