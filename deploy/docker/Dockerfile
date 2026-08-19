# --------------------------------------------------------------------------
# PS-MCP — wheel-based deployment Dockerfile
#
# Build a container image from pre-built wheel files produced by `psmcp build`.
# This Dockerfile is included in the deployment package and expects a `wheels/`
# directory next to it containing all .whl files.
#
# Usage (from inside the extracted deployment package):
#   docker build -t ps-mcp:latest .
#   docker run -d --name ps-mcp-server -p 8888:8888 --env-file .env ps-mcp:latest
#
# Or use the included docker.sh helper:
#   ./docker.sh deploy
# --------------------------------------------------------------------------
FROM python:3.13-slim

WORKDIR /opt/ps-mcp

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install curl for the health check
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels and install
COPY wheels/ /tmp/wheels/
RUN pip install --no-index --find-links /tmp/wheels /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels

# Copy .env.sample as a reference (actual .env is passed at runtime)
COPY .env.sample .env.sample

# Copy router config (routers.json) if present in the deployment package.
# The psmcp build command always creates this directory (may be empty).
COPY config/ .psmcp/

EXPOSE 8888

# Create a non-root user
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /opt/ps-mcp
USER mcp

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${MCP_PORT:-8888}/health || exit 1

CMD ["psmcp", "serve"]
