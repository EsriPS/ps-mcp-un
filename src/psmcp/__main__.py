"""
PS-MCP Server

A Model Context Protocol (MCP) server built with FastMCP.
Routers are discovered via Python entry points (group: psmcp.routers).

This module is the entry point for ``python -m psmcp``.
Server logic lives in ``server.py``; CLI logic lives in ``cli.py``.

Logging is configured inside ``cli.main()`` *after* ``--env-file`` has been
processed, so ``LOG_LEVEL`` from a ``.env`` file is honored on the first call.
"""

from .cli import main

if __name__ == "__main__":
    main()
