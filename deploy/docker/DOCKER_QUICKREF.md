# Docker Deployment Guide

Deploy PS-MCP in a Docker container using pre-built wheel files from a deployment package. This is the recommended approach for customer and production deployments — no source code is required.

---

## Prerequisites

| Requirement | Minimum version |
| --- | --- |
| Docker | 20.10+ |
| Deployment package | Built with `psmcp build --include-deps` |

---

## 1. Build the deployment package

On a **development machine** with the full source repository:

```bash
psmcp build --include-deps      # or: make build
```

This produces a `.tar.gz` archive in `dist/` containing:

```
ps-mcp-deploy-<version>-<date>/
├── wheels/          ← .whl files (ps-mcp + routers + dependencies)
├── Dockerfile       ← container image definition (installs from wheels)
├── docker.sh        ← helper script for Docker operations
├── .env.sample      ← environment variable template
├── config/          ← routers.json (if configured)
├── install.sh       ← Linux/macOS installer (non-Docker alternative)
└── install.ps1      ← Windows installer (non-Docker alternative)
```

Transfer the archive to the target machine.

---

## 2. Extract and configure

```bash
tar xzf ps-mcp-deploy-*.tar.gz
cd ps-mcp-deploy-*/

# Create your .env from the sample
cp .env.sample .env
# Edit .env with your portal URL, tokens, etc.
```

At minimum, configure:

```dotenv
MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_PORT=8888
ENABLED_ROUTERS=arcgis,feature_service,geoprocessing,location_services
ARCGIS_PORTAL_URL=https://your-portal.domain.com/portal
```

---

## 3. Build and run

### Using the helper script (easiest)

```bash
# Full deployment (build image + start container + tail logs)
./docker.sh deploy

# Or step by step:
./docker.sh build              # build Docker image from wheels
./docker.sh start              # start the container
./docker.sh logs               # view logs (Ctrl+C to exit)
```

### Using Docker CLI directly

```bash
# Build the image
docker build -t ps-mcp:latest .

# Run the container
docker run -d \
    --name ps-mcp-server \
    -p 8888:8888 \
    --env-file .env \
    --restart unless-stopped \
    ps-mcp:latest

# Verify
curl http://localhost:8888/health
# → {"status":"healthy","service":"ps-mcp"}
```

> **Windows users:** All `docker` commands work identically in PowerShell with Docker Desktop. The `docker.sh` helper requires bash (use WSL or Git Bash).

---

## Managing the container

### Helper script commands

| Command | Action |
| --- | --- |
| `./docker.sh build` | Build the Docker image from wheels |
| `./docker.sh start` | Start the container |
| `./docker.sh stop` | Stop and remove the container |
| `./docker.sh restart` | Restart the container |
| `./docker.sh logs` | Tail container logs |
| `./docker.sh status` | Show container status |
| `./docker.sh deploy` | Build + start + tail logs |

### Docker CLI equivalents

```bash
# Stop
docker stop ps-mcp-server && docker rm ps-mcp-server

# Restart
docker restart ps-mcp-server

# View logs
docker logs -f ps-mcp-server

# Status
docker ps -a --filter name=ps-mcp-server

# Shell access
docker exec -it ps-mcp-server /bin/bash

# Resource usage
docker stats ps-mcp-server
```

### Environment variables

You can override the helper script defaults via environment variables:

```bash
IMAGE_NAME=my-ps-mcp PORT=9999 ENV_FILE=/path/to/.env ./docker.sh deploy
```

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE_NAME` | `ps-mcp` | Docker image name |
| `CONTAINER_NAME` | `ps-mcp-server` | Container name |
| `PORT` | `8888` | Host port mapping |
| `ENV_FILE` | `.env` (in deploy dir) | Path to `.env` file |

---

## Updating

When a new version is available, build a fresh deployment package on the dev machine, transfer it, and re-deploy:

```bash
tar xzf ps-mcp-deploy-*.tar.gz
cd ps-mcp-deploy-*/

# Preserve your existing .env
cp /path/to/existing/.env .env

# Rebuild and restart
./docker.sh deploy
```

---

## Troubleshooting

### Container won't start

```bash
docker logs ps-mcp-server
```

### Health check failing

```bash
docker inspect --format='{{.State.Health.Status}}' ps-mcp-server
docker logs --tail 50 ps-mcp-server
```

### Port already in use

```bash
# Check what's using the port
sudo ss -tlnp | grep 8888     # Linux
netstat -ano | findstr :8888   # Windows
```

### Clean rebuild

```bash
./docker.sh stop
docker rmi ps-mcp:latest
./docker.sh deploy
```

### Common issues

| Symptom | Fix |
| --- | --- |
| `No wheel files found` | Run from inside an extracted deployment package |
| `Address already in use` | Stop existing container or change `PORT` |
| `Health check failing` | Check `.env` values, especially `ARCGIS_PORTAL_URL` |
| `ModuleNotFoundError` | Rebuild with `psmcp build --include-deps` |

---

## Server access

- **HTTP Endpoint**: `http://localhost:8888`
- **Health Check**: `http://localhost:8888/health`

---

## Quick links

- **Linux / systemd** → [`LINUX_DEPLOYMENT.md`](LINUX_DEPLOYMENT.md)
- **Windows** → [`WINDOWS_DEPLOYMENT.md`](WINDOWS_DEPLOYMENT.md)
- **Back to project root** → [`../README.md`](../README.md)

