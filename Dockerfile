# Initial stage for building the application
FROM python:3.13.12-slim-trixie AS build-stage

# Set working directory
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git \
    && rm -rf /var/lib/apt/lists/*

# Install uv (used for workspace sync). We rely on uv to resolve every package
# in the monorepo from a single lockfile.
RUN pip install uv

# Copy the whole repo so workspace members are visible. Layer caching is less
# important for a multi-package workspace than getting the resolution right.
COPY . .

# Install everything (server + all routers + transitive deps) into the system
# Python interpreter inside the container. --frozen requires uv.lock to exist.
RUN uv sync --all-packages --frozen --no-dev

# Expose port 8888 for the MCP server
EXPOSE 8888

# Create a non-root user to run the application
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${MCP_PORT}/health || exit 1

# Run the application
# When using `docker run --env-file`, env vars are already in the environment.
# For explicit .env loading inside the container:
#   CMD ["psmcp", "--env-file", "/app/.env", "serve"]
CMD ["psmcp", "serve"]
