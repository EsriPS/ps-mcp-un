"""PS-MCP Server — FastMCP instance creation and router discovery."""

import importlib.metadata
import logging
import os

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from psmcp.core.config import load_enabled_routers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pretty startup banner
# ---------------------------------------------------------------------------


def _center(text: str, width: int) -> str:
    if width <= 0:
        return text
    return text.center(width)


def _frame_lines(
    *,
    title: str,
    lines: list[str],
    width: int = 66,
    border: tuple[str, str, str] = ("═", "║", "╔╗╚╝"),
) -> list[str]:
    """Build a unicode box around lines."""
    h, v, corners = border
    tl, tr, bl, br = corners[0], corners[1], corners[2], corners[3]

    safe_width = max(10, width)

    top = f"{tl}{h * (safe_width + 2)}{tr}"
    bottom = f"{bl}{h * (safe_width + 2)}{br}"

    title_line = f"{v} {_center(title, safe_width)} {v}"

    framed: list[str] = [top, title_line]
    framed.append(f"{v} {h * safe_width} {v}")

    for line in lines:
        clipped = line[:safe_width]
        framed.append(f"{v} {clipped.ljust(safe_width)} {v}")

    return [*framed, bottom]


def _ps_mcp_logo() -> list[str]:
    return [
        "██████╗ ███████╗      ███╗   ███╗ ██████╗ ██████╗",
        "██╔══██╗██╔════╝      ████╗ ████║██╔════╝██╔══██╗",
        "██████╔╝███████╗█████╗██╔████╔██║██║     ██████╔╝",
        "██╔═══╝ ╚════██║╚════╝██║╚██╔╝██║██║     ██╔═══╝ ",
        "██║     ███████║      ██║ ╚═╝ ██║╚██████╗██║     ",
        "╚═╝     ╚══════╝      ╚═╝     ╚═╝ ╚═════╝╚═╝     ",
        "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░",
    ]


def _build_startup_banner(
    *, transport: str, host: str, port: int, routers: list[str] | None = None
) -> list[str]:
    inner_width = 72

    logo = _ps_mcp_logo()
    logo_centered = [_center(line, inner_width) for line in logo]

    info_lines = [
        "",
        "Name      : ps-mcp",
        f"Transport : {transport}",
        f"Host      : {host}",
        f"Port      : {port}",
    ]

    if routers:
        prefix = "Routers   : "
        continuation = " " * len(prefix)
        # Wrap router names so each rendered line fits within `inner_width`.
        current_line = prefix
        for i, name in enumerate(routers):
            addition = name if i == 0 else f", {name}"
            if len(current_line) + len(addition) > inner_width:
                info_lines.append(current_line)
                current_line = continuation + name
            else:
                current_line += addition
        info_lines.append(current_line)

    content = ["Starting server…", "", *logo_centered, *info_lines]
    return _frame_lines(title="", lines=content, width=inner_width, border=("═", "║", "╔╗╚╝"))


# ---------------------------------------------------------------------------
# Entry-point based router discovery
# ---------------------------------------------------------------------------


def _discover_routers() -> dict[str, importlib.metadata.EntryPoint]:
    """Discover all installed router plugins via entry points."""
    eps = importlib.metadata.entry_points(group="psmcp.routers")
    return {ep.name: ep for ep in eps}


def _get_enabled_router_names(discovered: dict[str, object]) -> list[str]:
    """Determine which routers to enable.

    Priority:
        1. ENABLED_ROUTERS env var (comma-separated, overrides everything)
        2. routers.json config file
        3. All discovered routers (default)
    """
    env = os.getenv("ENABLED_ROUTERS", "").strip()
    if env:
        requested = [r.strip().lower() for r in env.split(",") if r.strip()]
        enabled = [r for r in requested if r in discovered]
        unknown = [r for r in requested if r not in discovered]
        if unknown:
            logger.warning(
                "Unknown routers in ENABLED_ROUTERS (not installed): %s", ", ".join(unknown)
            )
        if not enabled:
            logger.warning("No valid routers in ENABLED_ROUTERS; enabling all discovered")
            return list(discovered.keys())
        logger.info("Enabled routers (from ENABLED_ROUTERS env): %s", ", ".join(enabled))
        return enabled

    from_config = load_enabled_routers()
    if from_config is not None:
        enabled = [r for r in from_config if r in discovered]
        skipped = [r for r in from_config if r not in discovered]
        if skipped:
            logger.warning("Routers in config but not installed: %s", ", ".join(skipped))
        logger.info("Enabled routers (from routers.json): %s", ", ".join(enabled))
        return enabled

    logger.info(
        "No router config found; enabling all %d discovered routers: %s",
        len(discovered),
        ", ".join(discovered.keys()),
    )
    return list(discovered.keys())


def _load_and_mount_routers(mcp: FastMCP) -> list[str]:
    """Discover, filter, and mount routers. Returns list of mounted names."""
    discovered = _discover_routers()
    if not discovered:
        logger.warning(
            "No router plugins discovered. Install router packages or check entry points."
        )
        return []

    enabled_names = _get_enabled_router_names(discovered)
    mounted = []

    for name in enabled_names:
        ep = discovered[name]
        try:
            router = ep.load()
            mcp.mount(router)
            mounted.append(name)
            logger.debug("Mounted router: %s", name)
        except Exception as e:
            logger.error("Failed to load/mount router %r: %s", name, e)

    return mounted


# ---------------------------------------------------------------------------
# Auth plugin discovery
# ---------------------------------------------------------------------------


def _discover_auth_plugin() -> object | None:
    """Discover and activate an auth plugin via entry points.

    Iterates through installed psmcp.auth plugins. The first factory
    that returns a non-None AuthProvider wins.

    Returns:
        An AuthProvider instance, or None if no plugin activates.
    """
    eps = importlib.metadata.entry_points(group="psmcp.auth")
    for ep in eps:
        try:
            factory = ep.load()
            provider = factory()
            if provider is not None:
                logger.info("Auth plugin activated: %s", ep.name)
                return provider
        except Exception as e:
            logger.error(
                "Auth plugin %r failed to load/activate: %s",
                ep.name,
                e,
                exc_info=True,
            )
            raise
    return None


# ---------------------------------------------------------------------------
# Lazy server initialization
# ---------------------------------------------------------------------------

_mcp: FastMCP | None = None
_mounted_routers: list[str] = []


def _init_server() -> FastMCP:
    """Create and configure the FastMCP server instance. Called once on serve."""
    global _mcp, _mounted_routers

    if _mcp is not None:
        return _mcp

    # Auth provider selection: plugin > USE_ARCGIS_AUTH > none
    auth_provider = _discover_auth_plugin()

    if auth_provider is not None:
        if os.getenv("USE_ARCGIS_AUTH") == "True":
            logger.warning(
                "USE_ARCGIS_AUTH is set but an auth plugin is active; USE_ARCGIS_AUTH is ignored."
            )
    elif os.getenv("USE_ARCGIS_AUTH") == "True":
        from psmcp.core.auth.arcgis_provider import ArcGISAuthProvider

        auth_provider = ArcGISAuthProvider()
        logger.info("ArcGIS Enterprise authentication enabled")

    _mcp = FastMCP("ps-mcp", auth=auth_provider)
    _mounted_routers = _load_and_mount_routers(_mcp)

    @_mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        return JSONResponse({"status": "healthy", "service": "ps-mcp"})

    return _mcp
