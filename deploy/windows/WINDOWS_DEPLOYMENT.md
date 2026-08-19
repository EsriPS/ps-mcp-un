# Windows Deployment Guide

Deploy PS-MCP on Windows as a standalone process or a persistent Windows service.
---

## Prerequisites

| Requirement | Minimum version | Notes |
| --- | --- | --- |
| uv | latest | |
---

## 1. Create Python Environment

This assumes you have installed uv and it is available in your command prompt. It also assumes that you have all the required wheel files in a directory named C:\temp\ps-mcp\dist

```cmd
# Create a virtual environment
uv venv mcp-env --python 3.13

# Activate that new environment
mcp-env\Scripts\activate

# Install psmcp and all dependencies into virtual environment
uv pip install --find-links C:\temp\ps-mcp\dist
```

---

## 2. Configure the environment

PS MCP requires a `.env` file to load configurable settings. Ensure that you've moved a copy of the [.env template](../../.env.sample) to your machine. It can be anywhere, but these instructions assume it will be located at C:\temp\ps-mcp.

---

## 3. Verify the server starts manually

We assume that you have the Python virtual environment active.

```cmd
psmcp --env-file C:\temp\ps-mcp\.env serve
```

In addition to the startup banner that should appear in the terminal, you can navigate to http://localhost:8888/health to ensure the application is responding.

---

## 4. Running as a service

At the time of writing, it would be best to review tooling like [NSSM](https://nssm.cc/) or [Servy](https://servy-win.github.io/) to run this as a service on Windows.