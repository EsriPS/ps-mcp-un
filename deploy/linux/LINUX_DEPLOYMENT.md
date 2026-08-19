# Linux Deployment Guide

This document provides an overivew for how you might deploy PS-MCP as a `systemd` service on Ubuntu.

---

## Prerequisites

We assume you are running a recent LTS of Ubunut and have administrative access to your machine. Aside from installing uv for managing the Python virtual environment, no other external libraries should be required. 

| Requirement | Minimum version |
| --- | --- |
| uv | latest |

---

## 1. Prepare the User, Group, Working Directories, and Python

Consult [setup-build.sh](setup-build.sh) for details on setting up the baseline for PS MCP.

---

## 2. Configure the environment

PS MCP requires a `.env` file to load configurable settings. Ensure that you've moved a copy of the [.env template](../../.env.sample) to your machine. It can be anywhere, but these instructions assume it will be located at /opt/mcp/config.

---

## 3. Verify the server starts manually

Once you have a valid Python environment and a .env file, you can run PS MCP as shown below.

```bash
/opt/mcp/mcp-env/bin/python -m psmcp --env-file /opt/mcp/config/.env
```

In addition to the PS-MCP startup banner, you can confirm the health endpoint at http://localhost:8888/health. 

---

## 4. Getting the Service Running

```bash
# Assumes that service file has already been moved to the machine
sudo cp /opt/mcp/config/ps-mcp.service /etc/systemd/system/ps-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable ps-mcp
sudo systemctl start ps-mcp
sudo systemctl status ps-mcp
```

---