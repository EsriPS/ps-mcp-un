#!/bin/bash

GITHUB_URL="$1"
GITHUB_PAT="$2"

if [ -z "$GITHUB_URL" ] || [ -z "$GITHUB_PAT" ]; then
    echo "Usage: ./setup.sh <github-url> <github-pat>"
    exit 1
fi

# Install the latest version of uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Refresh shell
source $HOME/.local/bin/env

# Fetch repo (inject PAT into URL for authentication)
git clone https://${GITHUB_PAT}@${GITHUB_URL#https://} /opt/mcp/ps-mcp

# Create Python virtual environment and install everything
cd /opt/mcp/py
uv venv psmcp --python 3.13
source ./psmcp/bin/activate

# Install PS MCP into virtual environment
cd /opt/mcp/ps-mcp
uv sync --all-packages --active