"""Tests for browser CORS behavior on the generated HTTP app."""

from __future__ import annotations

import importlib.metadata

from starlette.testclient import TestClient

import psmcp.server as srv


def _no_entry_points(group: str | None = None, **_kwargs):
    return []


def _build_preflight_response(client: TestClient, origin: str):
    return client.options(
        "/mcp",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def _build_simple_response(client: TestClient, origin: str):
    return client.get(
        "/health",
        headers={
            "Origin": origin,
        },
    )


def test_http_app_allows_localhost_browser_origins_by_default(monkeypatch):
    """Default CORS settings allow localhost browser apps on other ports."""
    monkeypatch.setattr(importlib.metadata, "entry_points", _no_entry_points)
    monkeypatch.setattr(srv, "_mcp", None)
    monkeypatch.setattr(srv, "_mounted_routers", [])

    app = srv._init_server().http_app(middleware=srv._build_http_middleware())

    with TestClient(app) as client:
        response = _build_preflight_response(client, "http://localhost:3000")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_http_app_exposes_mcp_session_id_header_to_browser_clients(monkeypatch):
    """Browser JS must be allowed to read the MCP session header on HTTP responses."""
    monkeypatch.setattr(importlib.metadata, "entry_points", _no_entry_points)
    monkeypatch.setattr(srv, "_mcp", None)
    monkeypatch.setattr(srv, "_mounted_routers", [])

    app = srv._init_server().http_app(middleware=srv._build_http_middleware())

    with TestClient(app) as client:
        response = _build_simple_response(client, "http://localhost:3000")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-expose-headers"] == "mcp-session-id"


def test_http_app_uses_explicit_allowed_origins_when_configured(monkeypatch):
    """Configured origins replace the localhost wildcard default."""
    monkeypatch.setattr(importlib.metadata, "entry_points", _no_entry_points)
    monkeypatch.setattr(srv, "_mcp", None)
    monkeypatch.setattr(srv, "_mounted_routers", [])
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://app.example.com")

    app = srv._init_server().http_app(middleware=srv._build_http_middleware())

    with TestClient(app) as client:
        allowed = _build_preflight_response(client, "https://app.example.com")
        blocked = _build_preflight_response(client, "http://localhost:3000")

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers