# PS-MCP Deployment Guide

This package contains pre-built wheels and helper scripts for deploying PS-MCP
without needing to build from source.

## Contents

```
wheels/            → Pre-built .whl files (server + all routers)
install.sh         → Installer for Linux / macOS
install.ps1        → Installer for Windows
.env.sample        → Environment variable template
config/            → Router configuration (routers.json if applicable)
Dockerfile         → Container image build from wheels
docker.sh          → Docker helper script
ps-mcp.service     → systemd unit file (Linux)
DEPLOYMENT.md      → This file
```

## Prerequisites

- **Python 3.13** (required — the wheels target this version)
- **uv** (recommended) or **pip** for virtual environment creation
- Network access is NOT required — all dependencies are bundled as wheels

## Quick Start (Linux / macOS)

```bash
# Extract the release archive
tar xzf ps-mcp-<VERSION>.tar.gz
cd ps-mcp-<VERSION>

# Run the installer (creates a venv and installs all wheels)
./install.sh /opt/ps-mcp

# Edit the environment file
cp /opt/ps-mcp/.env.sample /opt/ps-mcp/.env
nano /opt/ps-mcp/.env

# Start the server
/opt/ps-mcp/.venv/bin/psmcp --env-file /opt/ps-mcp/.env serve
```

## Quick Start (Windows)

```powershell
# Extract the release zip
Expand-Archive ps-mcp-<VERSION>.zip -DestinationPath C:\ps-mcp

# Run the installer
cd C:\ps-mcp\ps-mcp-<VERSION>
.\install.ps1 -InstallDir C:\ps-mcp

# Edit the environment file
copy C:\ps-mcp\.env.sample C:\ps-mcp\.env
notepad C:\ps-mcp\.env

# Start the server
C:\ps-mcp\.venv\Scripts\psmcp.exe --env-file C:\ps-mcp\.env serve
```

## Docker Deployment

```bash
# From inside the extracted package directory:
docker build -t ps-mcp:latest .
docker run -d \
  --name ps-mcp-server \
  -p 8888:8888 \
  --env-file .env \
  ps-mcp:latest
```

Or use the helper script:

```bash
./docker.sh deploy
```

## systemd Service (Linux)

```bash
# Copy the service file
sudo cp ps-mcp.service /etc/systemd/system/

# Edit paths in the service file to match your install location
sudo systemctl daemon-reload
sudo systemctl enable ps-mcp
sudo systemctl start ps-mcp
```

## Configuration

### Required Environment Variables

At minimum, configure these in your `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_TRANSPORT` | Transport protocol (`http`, `stdio`, `sse`) | `http` |
| `MCP_HOST` | Bind address | `0.0.0.0` |
| `MCP_PORT` | Listen port | `8888` |
| `ENABLED_ROUTERS` | Comma-separated list of routers to enable | all installed |
| `ARCGIS_PORTAL_URL` | ArcGIS Enterprise portal URL | — |
| `ARCGIS_TOKEN` | Pre-generated ArcGIS token | — |

See `.env.sample` for the full list of available variables.

### Router Management

```bash
# List available routers
/opt/ps-mcp/.venv/bin/psmcp router list

# Enable/disable specific routers
/opt/ps-mcp/.venv/bin/psmcp router enable feature_service
/opt/ps-mcp/.venv/bin/psmcp router disable mongo
```

## Verifying the Installation

```bash
# Check CLI is working
/opt/ps-mcp/.venv/bin/psmcp --help

# Check server health (after starting)
curl http://localhost:8888/health
```

## Upgrading

1. Stop the running server
2. Extract the new release archive
3. Re-run `install.sh` pointing to the same install directory — it will
   upgrade the wheels in the existing venv
4. Restart the server

## Troubleshooting

- **"No module named psmcp"** — Ensure you're using the venv Python:
  `/opt/ps-mcp/.venv/bin/python -c "import psmcp"`
- **Health check fails** — Check `LOG_LEVEL=DEBUG` in `.env` and review stdout
- **Router not found** — Run `psmcp router list` to see what's installed vs enabled
- **SSL errors to ArcGIS** — Set `ARCGIS_VERIFY_SSL=false` for self-signed certs
