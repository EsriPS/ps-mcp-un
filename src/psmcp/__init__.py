"""PS-MCP — pluggable FastMCP server for ArcGIS-first workflows.

The package version is derived from git tags via ``hatch-vcs`` and written to
``psmcp._version`` at build/install time. We fall back to
``importlib.metadata`` so editable installs that haven't run the build hook
yet still expose a sensible value.
"""

from __future__ import annotations

try:
    from psmcp._version import __version__, __version_tuple__  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - only hit before the build hook ran
    try:
        from importlib.metadata import PackageNotFoundError, version

        __version__ = version("ps-mcp")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"
    __version_tuple__ = tuple(  # type: ignore[assignment]
        int(p) if p.isdigit() else p for p in __version__.split(".")
    )

__all__ = ["__version__", "__version_tuple__"]
