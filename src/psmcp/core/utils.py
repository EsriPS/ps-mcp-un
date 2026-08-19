"""Project-wide logging configuration.

Call :func:`setup_logging` once at process startup (e.g., in
``src/psmcp/__main__.py``). All other modules should only do::

    import logging
    logger = logging.getLogger(__name__)

This avoids duplicated handlers and keeps formatting/levels in a single place.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any


def setup_logging(*, level: str | int | None = None) -> None:
    """Configure Python logging for the whole process.

    Safe to call multiple times — extra calls only adjust the level.

    Args:
        level: Optional explicit log level (``"DEBUG"``, ``logging.INFO``, ...).
            Falls back to the ``LOG_LEVEL`` environment variable, then ``INFO``.
    """
    chosen_level: Any = level or os.getenv("LOG_LEVEL", "INFO")
    root = logging.getLogger()

    # If logging is already configured, just adjust the level instead of
    # adding another handler (which would cause duplicate log lines).
    if root.handlers:
        root.setLevel(chosen_level)
        return

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    root.addHandler(handler)
    root.setLevel(chosen_level)

    # Reduce noise from chatty libraries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
