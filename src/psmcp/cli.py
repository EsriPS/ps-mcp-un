"""PS-MCP CLI — router management and server startup commands."""

import argparse
import logging
import os
import pathlib
import subprocess
import sys
from typing import Any, Literal, cast

from psmcp.core.config import (
    add_router,
    get_config_dir,
    load_enabled_routers,
    remove_router,
)
from psmcp.core.utils import setup_logging

from . import server as _server
from .server import (
    _build_startup_banner,
    _discover_routers,
    _get_enabled_router_names,
    _init_server,
)

logger = logging.getLogger(__name__)

_GREEN = "\x1b[92m"
_RESET = "\x1b[0m"


def _ansi_green(text: str) -> str:
    return f"{_GREEN}{text}{_RESET}"


# ============================================================================
# Argparse
# ============================================================================


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psmcp",
        description="PS-MCP Server — pluggable MCP server with router plugins",
    )
    parser.add_argument("--config-dir", help="Override config directory (sets PSMCP_CONFIG_DIR)")
    parser.add_argument("--env-file", help="Load environment variables from a .env file")
    sub = parser.add_subparsers(dest="command")

    # ── serve ──
    serve = sub.add_parser("serve", help="Start the MCP server (default)")
    serve.add_argument("--transport", help="MCP transport (http, stdio, sse, streamable-http)")
    serve.add_argument("--host", help="Host interface to bind")
    serve.add_argument("--port", type=int, help="Port to listen on")
    serve.add_argument("--token", help="ArcGIS token (sets ARCGIS_TOKEN env var)")
    serve.add_argument("--ssl-keyfile", help="Path to SSL private key file (PEM)")
    serve.add_argument("--ssl-certfile", help="Path to SSL certificate file (PEM)")

    # ── router ──
    router_parser = sub.add_parser("router", help="Manage router plugins")
    router_sub = router_parser.add_subparsers(dest="router_command")

    router_sub.add_parser("list", help="List discovered routers and their status")

    enable_p = router_sub.add_parser("enable", help="Enable one or more routers")
    enable_p.add_argument("names", nargs="+", help="Router name(s) — space or comma-separated")

    disable_p = router_sub.add_parser("disable", help="Disable one or more routers")
    disable_p.add_argument("names", nargs="+", help="Router name(s) — space or comma-separated")

    install_p = router_sub.add_parser(
        "install", help="Install a router wheel and enable it (dev convenience)"
    )
    install_p.add_argument("whl_path", help="Path to .whl file")

    # ── build ──
    build_parser = sub.add_parser("build", help="Build a deployment package with wheels and config")
    build_parser.add_argument("--outdir", default="dist", help="Output directory (default: dist)")
    build_parser.add_argument(
        "--include-deps",
        action="store_true",
        help="Also download third-party dependencies into the package",
    )

    return parser


# ============================================================================
# Router subcommands
# ============================================================================


def _cmd_router_list():
    discovered = _discover_routers()
    enabled_cfg = load_enabled_routers()

    print(f"\nConfig dir: {get_config_dir()}")
    print(f"Discovered {len(discovered)} router(s):\n")

    if not discovered:
        print("  (none — install router packages to get started)")
        return

    for name, ep in sorted(discovered.items()):
        if enabled_cfg is None:
            status = "enabled (all)"
        elif name in enabled_cfg:
            status = "enabled"
        else:
            status = "disabled"
        print(f"  {name:30s}  [{status}]  ({ep.value})")
    print()


def _parse_names(raw: list[str]) -> list[str]:
    """Expand a list of names that may contain comma-separated values."""
    names = []
    for item in raw:
        for part in item.split(","):
            part = part.strip()
            if part:
                names.append(part)
    return names


def _cmd_router_enable(raw_names: list[str]):
    names = _parse_names(raw_names)
    discovered = _discover_routers()
    unknown = [n for n in names if n not in discovered]
    if unknown:
        print(
            f"Error: Unknown router(s): {', '.join(unknown)}. Discovered: {', '.join(discovered.keys()) or '(none)'}"
        )
        sys.exit(1)
    updated = []
    for name in names:
        updated = add_router(name)
    print(f"Enabled: {', '.join(names)}. Active routers: {', '.join(updated)}")


def _cmd_router_disable(raw_names: list[str]):
    names = _parse_names(raw_names)
    discovered = _discover_routers()
    updated = []
    for name in names:
        updated = remove_router(name, all_discovered=list(discovered.keys()))
    print(f"Disabled: {', '.join(names)}. Active routers: {', '.join(updated) or '(none)'}")


def _cmd_router_install(whl_path: str):
    print(f"Installing {whl_path} ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", whl_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"pip install failed:\n{result.stderr}")
        sys.exit(1)
    print(result.stdout)

    # Discover newly installed router(s) and auto-enable
    discovered = _discover_routers()
    enabled_cfg = load_enabled_routers() or []
    newly_found = [n for n in discovered if n not in enabled_cfg]
    for name in newly_found:
        add_router(name)
        print(f"Auto-enabled router '{name}'")


# ============================================================================
# Build subcommand
# ============================================================================


def _find_project_root() -> pathlib.Path:
    """Walk up from this file to find the project root (contains pyproject.toml + packages/)."""
    # Try common locations: CWD first, then relative to the package
    cwd = pathlib.Path.cwd()
    if (cwd / "pyproject.toml").exists() and (cwd / "packages").is_dir():
        return cwd
    # Fallback: walk up from this source file
    p = pathlib.Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "pyproject.toml").exists() and (p / "packages").is_dir():
            return p
        p = p.parent
    return cwd


def _router_name_to_pkg_dir(name: str, project_root: pathlib.Path) -> pathlib.Path | None:
    """Map a router entry-point name (e.g. 'feature_service') to its package directory.

    Checks the local packages/ directory first (for built-in routers), then
    falls back to the installed package's source location (for third-party routers).
    """
    import importlib.metadata as _meta

    # Convention: underscores in entry-point name → hyphens in directory name
    hyphenated = name.replace("_", "-")
    pkg_dir = project_root / "packages" / f"psmcp-router-{hyphenated}"
    if pkg_dir.is_dir():
        return pkg_dir

    # Try to find the source directory from installed package metadata
    # (works for editable installs of external routers)
    dist_name = f"psmcp-router-{hyphenated}"
    try:
        dist = _meta.distribution(dist_name)
        # direct_url.json is set for editable installs and contains the source path
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            import json as _json

            info = _json.loads(direct_url)
            url = info.get("url", "")
            if url.startswith("file://"):
                source_dir = pathlib.Path(url.removeprefix("file://"))
                if source_dir.is_dir() and (source_dir / "pyproject.toml").exists():
                    return source_dir
    except (_meta.PackageNotFoundError, Exception):
        pass

    # Also try without the psmcp-router- prefix (third-party routers with custom names)
    # Look up the entry point to get the module, then find the distribution
    try:
        eps = _meta.entry_points(group="psmcp.routers")
        for ep in eps:
            if ep.name == name and ep.dist:
                dist = ep.dist
                direct_url = dist.read_text("direct_url.json")
                if direct_url:
                    import json as _json

                    info = _json.loads(direct_url)
                    url = info.get("url", "")
                    if url.startswith("file://"):
                        source_dir = pathlib.Path(url.removeprefix("file://"))
                        if source_dir.is_dir() and (source_dir / "pyproject.toml").exists():
                            return source_dir
    except Exception:
        pass

    return None


def _cmd_build(outdir: str, include_deps: bool):
    """Build a deployment package containing wheels for enabled routers + config."""
    import datetime
    import importlib.metadata
    import shutil
    import textwrap

    project_root = _find_project_root()

    # Read version from server package
    try:
        version = importlib.metadata.version("ps-mcp")
    except importlib.metadata.PackageNotFoundError:
        version = "0.1.0"

    date_str = datetime.date.today().strftime("%Y%m%d")
    deploy_name = f"ps-mcp-deploy-{version}-{date_str}"
    deploy_dir = pathlib.Path(outdir) / deploy_name
    wheels_dir = deploy_dir / "wheels"

    # Clean previous build with same name
    if deploy_dir.exists():
        shutil.rmtree(deploy_dir)
    wheels_dir.mkdir(parents=True)

    # Determine which routers are enabled
    discovered = _discover_routers()
    enabled_names = _get_enabled_router_names(discovered)

    print(f"Building deployment package: {deploy_name}")
    print(f"Enabled routers: {', '.join(enabled_names)}")
    print()

    # Ensure build tool is available
    try:
        import build as _build_check  # noqa: F401
    except ImportError:
        print("  Installing build tool...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "build"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR: Failed to install 'build' package:\n{result.stderr}")
            sys.exit(1)

    def _build_wheel(pkg_path: pathlib.Path, label: str):
        print(f"  Building {label}...")
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheels_dir), str(pkg_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR building {label}:\n{result.stderr}")
            sys.exit(1)

    # Build each enabled router. We collect failures and exit non-zero at the
    # end so the operator never gets a "success" message for an incomplete
    # deployment package.
    build_failures: list[str] = []
    for name in enabled_names:
        pkg_dir = _router_name_to_pkg_dir(name, project_root)
        if pkg_dir:
            _build_wheel(pkg_dir, f"psmcp-router-{name.replace('_', '-')}")
        else:
            # No source directory found — try to build a wheel from the installed package
            # using pip wheel (works for non-editable installs)
            hyphenated = name.replace("_", "-")
            dist_name = f"psmcp-router-{hyphenated}"
            print(f"  Building {dist_name} (from installed package)...")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    str(wheels_dir),
                    dist_name,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Try finding the actual distribution name from the entry point
                ep = discovered.get(name)
                if ep and ep.dist:
                    actual_name = ep.dist.metadata["Name"]
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "wheel",
                            "--no-deps",
                            "--wheel-dir",
                            str(wheels_dir),
                            actual_name,
                        ],
                        capture_output=True,
                        text=True,
                    )
                if result.returncode != 0:
                    print(
                        f"  ERROR: Could not build wheel for router '{name}'.\n"
                        f"  pip stderr:\n{result.stderr}"
                    )
                    build_failures.append(name)

    if build_failures:
        print()
        print(
            f"ERROR: Failed to build wheels for {len(build_failures)} router(s): "
            f"{', '.join(build_failures)}"
        )
        print("Refusing to produce a partial deployment package.")
        sys.exit(1)

    # Build the server package
    if (project_root / "pyproject.toml").exists() and (project_root / "src" / "psmcp").is_dir():
        _build_wheel(project_root, "ps-mcp (server)")
    else:
        print("  Building ps-mcp (from installed package)...")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(wheels_dir),
                "ps-mcp",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: Could not build ps-mcp server wheel:\n{result.stderr}")
            sys.exit(1)

    # Optionally download third-party dependencies
    if include_deps:
        print("  Downloading third-party dependencies...")
        all_whls = list(wheels_dir.glob("*.whl"))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(wheels_dir),
                "--no-deps",  # we'll resolve transitively below
            ]
            + [str(w) for w in all_whls],
            capture_output=True,
            text=True,
        )
        # Better approach: download deps based on requirements
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(wheels_dir),
                "--find-links",
                str(wheels_dir),
                "ps-mcp",
            ],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        if result.returncode != 0:
            print(f"  WARNING: Some dependencies may not have downloaded:\n{result.stderr}")

    # Copy .env.sample or generate one from .env
    env_sample = project_root / ".env.sample"
    env_file = project_root / ".env"
    if env_sample.exists():
        shutil.copy2(env_sample, deploy_dir / ".env.sample")
    elif env_file.exists():
        # Strip values, keep keys as a template
        lines = env_file.read_text().splitlines()
        stripped = []
        for line in lines:
            if line.strip().startswith("#") or "=" not in line or not line.strip():
                stripped.append(line)
            else:
                key = line.split("=", 1)[0]
                stripped.append(f"{key}=")
        (deploy_dir / ".env.sample").write_text("\n".join(stripped) + "\n")

    # Copy routers.json if it exists
    config_dir = get_config_dir()
    routers_json = config_dir / "routers.json"
    config_out = deploy_dir / "config"
    config_out.mkdir(exist_ok=True)
    if routers_json.exists():
        shutil.copy2(routers_json, config_out / "routers.json")

    # Copy deploy helper files
    deploy_src = project_root / "deploy"
    for helper in ["ps-mcp.service", "nginx.conf", "Dockerfile", "docker.sh"]:
        src = deploy_src / helper
        if src.exists():
            shutil.copy2(src, deploy_dir / helper)
    # Ensure docker.sh is executable
    docker_sh = deploy_dir / "docker.sh"
    if docker_sh.exists():
        os.chmod(docker_sh, 0o755)

    # Generate install scripts
    (deploy_dir / "install.sh").write_text(
        textwrap.dedent("""\
        #!/usr/bin/env bash
        # PS-MCP Deployment Installer (Linux / macOS)
        set -euo pipefail

        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        INSTALL_DIR="${1:-$(pwd)}"

        echo "Installing PS-MCP to: ${INSTALL_DIR}"
        mkdir -p "${INSTALL_DIR}"

        # Create venv if it doesn't exist
        if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
            echo "Creating virtual environment..."
            uv venv --python 3.13 --seed "${INSTALL_DIR}/.venv" 2>/dev/null || \\
                python3.13 -m venv "${INSTALL_DIR}/.venv"
        fi

        echo "Installing wheels..."
        "${INSTALL_DIR}/.venv/bin/pip" install --no-index --find-links "${SCRIPT_DIR}/wheels" \\
            "${SCRIPT_DIR}"/wheels/*.whl

        # Copy config if included and not already present
        if [[ -d "${SCRIPT_DIR}/config" && ! -d "${INSTALL_DIR}/.psmcp" ]]; then
            mkdir -p "${INSTALL_DIR}/.psmcp"
            cp "${SCRIPT_DIR}"/config/* "${INSTALL_DIR}/.psmcp/"
            echo "Copied router config to ${INSTALL_DIR}/.psmcp/"
        fi

        # Copy sample env if no .env exists yet
        if [[ ! -f "${INSTALL_DIR}/.env" && -f "${SCRIPT_DIR}/.env.sample" ]]; then
            cp "${SCRIPT_DIR}/.env.sample" "${INSTALL_DIR}/.env"
            echo "Created .env from sample — edit it with your settings"
        fi

        echo ""
        echo "Installation complete!"
        echo ""
        echo "Start the server:"
        echo "  ${INSTALL_DIR}/.venv/bin/psmcp --env-file ${INSTALL_DIR}/.env serve"
    """)
    )
    os.chmod(deploy_dir / "install.sh", 0o755)

    (deploy_dir / "install.ps1").write_text(
        textwrap.dedent("""\
        # PS-MCP Deployment Installer (Windows)
        param([string]$InstallDir = (Get-Location))
        $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        Write-Host "Installing PS-MCP to: $InstallDir"
        if (-not (Test-Path "$InstallDir\\.venv")) {
            Write-Host "Creating virtual environment..."
            try { uv venv --python 3.13 --seed "$InstallDir\\.venv" }
            catch { py -3.13 -m venv "$InstallDir\\.venv" }
        }
        Write-Host "Installing wheels..."
        & "$InstallDir\\.venv\\Scripts\\pip.exe" install --no-index --find-links "$ScriptDir\\wheels" `
            (Get-ChildItem "$ScriptDir\\wheels\\*.whl" | ForEach-Object { $_.FullName })
        if ((Test-Path "$ScriptDir\\config") -and -not (Test-Path "$InstallDir\\.psmcp")) {
            New-Item -ItemType Directory -Force -Path "$InstallDir\\.psmcp" | Out-Null
            Copy-Item "$ScriptDir\\config\\*" "$InstallDir\\.psmcp\\"
            Write-Host "Copied router config to $InstallDir\\.psmcp\\"
        }
        if (-not (Test-Path "$InstallDir\\.env") -and (Test-Path "$ScriptDir\\.env.sample")) {
            Copy-Item "$ScriptDir\\.env.sample" "$InstallDir\\.env"
            Write-Host "Created .env from sample - edit it with your settings"
        }
        Write-Host ""
        Write-Host "Installation complete!"
        Write-Host "Start the server:"
        Write-Host "  $InstallDir\\.venv\\Scripts\\psmcp.exe --env-file $InstallDir\\.env serve"
    """)
    )

    # List built wheels
    print()
    print("Wheels built:")
    for whl in sorted(wheels_dir.glob("*.whl")):
        print(f"  {whl.name}")

    # Create tar.gz archive
    print()
    print("Creating archive...")
    archive_path = pathlib.Path(outdir) / f"{deploy_name}.tar.gz"
    import tarfile

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(deploy_dir, arcname=deploy_name)

    print()
    print("Deployment package ready:")
    print(f"  Directory: {deploy_dir}/")
    print(f"  Archive:   {archive_path}")
    print()
    print("To deploy, copy the archive to the target machine and run:")
    print(f"  tar xzf {deploy_name}.tar.gz")
    print(f"  cd {deploy_name}")
    print("  ./install.sh /opt/ps-mcp")


# ============================================================================
# Serve helpers
# ============================================================================


def _get_server_config(
    args: argparse.Namespace,
) -> tuple[Literal["stdio", "http", "sse", "streamable-http"], str, int, str | None, str | None]:
    """Resolve transport/host/port/ssl from CLI > ENV > defaults."""
    default_transport: Literal["stdio", "http", "sse", "streamable-http"] = "http"
    default_host = "0.0.0.0"
    default_port = 8888

    env_transport = os.getenv("MCP_TRANSPORT")
    env_host = os.getenv("MCP_HOST")
    env_port_raw = os.getenv("MCP_PORT")

    requested_transport = getattr(args, "transport", None) or env_transport or default_transport
    if requested_transport not in {"stdio", "http", "sse", "streamable-http"}:
        logger.warning(
            "Invalid MCP transport %r; falling back to %r", requested_transport, default_transport
        )
        transport = default_transport
    else:
        transport = cast(Literal["stdio", "http", "sse", "streamable-http"], requested_transport)

    host = getattr(args, "host", None) or env_host or default_host

    port: int
    cli_port = getattr(args, "port", None)
    if cli_port is not None:
        port = cli_port
    elif env_port_raw:
        try:
            port = int(env_port_raw)
        except ValueError:
            logger.warning("Invalid MCP_PORT=%r; falling back to %d", env_port_raw, default_port)
            port = default_port
    else:
        port = default_port

    # SSL: CLI args take precedence over env vars
    ssl_keyfile = getattr(args, "ssl_keyfile", None) or os.getenv("MCP_SSL_KEYFILE") or None
    ssl_certfile = getattr(args, "ssl_certfile", None) or os.getenv("MCP_SSL_CERTFILE") or None

    if ssl_keyfile and not ssl_certfile:
        logger.warning("--ssl-keyfile provided without --ssl-certfile; SSL will not be enabled")
        ssl_keyfile = None
    elif ssl_certfile and not ssl_keyfile:
        logger.warning("--ssl-certfile provided without --ssl-keyfile; SSL will not be enabled")
        ssl_certfile = None

    return transport, host, port, ssl_keyfile, ssl_certfile


# ============================================================================
# Main entry point
# ============================================================================


def main(argv: list[str] | None = None):
    """Main entry point for the PS-MCP CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Apply --env-file before anything else so vars are available
    env_file = getattr(args, "env_file", None)
    if env_file:
        from dotenv import load_dotenv

        if not os.path.isfile(env_file):
            print(f"Error: env file not found: {env_file}")
            sys.exit(1)
        load_dotenv(env_file, override=True)

    # Configure logging *after* the env file is loaded so LOG_LEVEL from
    # `.env` is honored on the first call (setup_logging is idempotent).
    setup_logging()
    if env_file:
        logger.info("Loaded environment from %s", env_file)

    # Apply --config-dir before any config functions are called
    config_dir = getattr(args, "config_dir", None)
    if config_dir:
        os.environ["PSMCP_CONFIG_DIR"] = config_dir

    command = args.command

    # ── router subcommand ──
    if command == "router":
        rc = getattr(args, "router_command", None)
        if rc == "list":
            _cmd_router_list()
        elif rc == "enable":
            _cmd_router_enable(args.names)
        elif rc == "disable":
            _cmd_router_disable(args.names)
        elif rc == "install":
            _cmd_router_install(args.whl_path)
        else:
            parser.parse_args(["router", "--help"])
        return

    # ── build subcommand ──
    if command == "build":
        _cmd_build(
            outdir=getattr(args, "outdir", "dist"),
            include_deps=getattr(args, "include_deps", False),
        )
        return

    # ── serve (default when no subcommand) ──
    mcp = _init_server()
    transport, host, port, ssl_keyfile, ssl_certfile = _get_server_config(args)

    token = getattr(args, "token", None)
    if token:
        os.environ["ARCGIS_TOKEN"] = token
        logger.info("ArcGIS token set from --token CLI argument")

    framed = _build_startup_banner(
        transport=transport, host=host, port=port, routers=_server._mounted_routers
    )
    for line in framed:
        print(_ansi_green(line))

    if transport == "stdio":
        logger.info("Starting MCP server in stdio mode")
        mcp.run(transport=transport)
    else:
        uvicorn_config: dict[str, str] = {}
        if ssl_keyfile and ssl_certfile:
            uvicorn_config["ssl_keyfile"] = ssl_keyfile
            uvicorn_config["ssl_certfile"] = ssl_certfile
            logger.info("SSL enabled: cert=%s key=%s", ssl_certfile, ssl_keyfile)
        # Run HTTP transports statelessly with plain JSON responses. Stateful
        # streamable-HTTP keeps a standalone SSE GET stream open per session, and
        # browser MCP clients (which open a new session per tool call) quickly hit
        # the 6-connections-per-origin limit and hang on later tool calls. Stateless
        # + json_response makes each request independent with a normal JSON reply.
        http_kwargs: dict[str, Any] = {}
        if transport in ("http", "streamable-http"):
            http_kwargs = {"stateless_http": True, "json_response": True}
        mcp.run(
            transport=transport,
            host=host,
            port=port,
            uvicorn_config=uvicorn_config if uvicorn_config else None,
            **http_kwargs,
        )
