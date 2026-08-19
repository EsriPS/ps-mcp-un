#!/bin/bash

# Create a group
sudo groupadd mcp

# Create the user with the group, home directory, and shell
sudo useradd -m -g mcp -s /bin/bash mcp

# Set the password
echo "mcp:mcp" | sudo chpasswd

# Add to sudoers
sudo usermod -aG sudo mcp

# Create working directories
sudo mkdir -p /opt/mcp
sudo mkdir -p /opt/mcp/py
sudo mkdir -p /opt/mcp/config

# Grant user write access to /opt/mcp
sudo chown -R mcp:mcp /opt/mcp

# Switch to the new user
su mcp

# Install the latest version of uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Refresh shell
source $HOME/.local/bin/env

# Create Python virtual environment and install everything
cd /opt/mcp
uv venv mcp-env --python 3.13
source ./mcp-env/bin/activate

# Install ps-mcp and dependencies
uv pip install --find-links /opt/mcp/py/dist