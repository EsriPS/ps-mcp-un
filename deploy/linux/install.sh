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
    uv venv --python 3.13 --seed "${INSTALL_DIR}/.venv" 2>/dev/null || \
        python3.13 -m venv "${INSTALL_DIR}/.venv"
fi

echo "Installing wheels..."
"${INSTALL_DIR}/.venv/bin/pip" install --find-links "${SCRIPT_DIR}/wheels" \
    "${SCRIPT_DIR}"/wheels/*.whl

# Copy config if included and not already present
if [[ -d "${SCRIPT_DIR}/config" && ! -d "${INSTALL_DIR}/.psmcp" ]]; then
    mkdir -p "${INSTALL_DIR}/.psmcp"
    cp "${SCRIPT_DIR}"/config/* "${INSTALL_DIR}/.psmcp/" 2>/dev/null || true
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
