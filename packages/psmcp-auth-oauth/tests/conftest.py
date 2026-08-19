"""Shared pytest fixtures for the psmcp-auth-oauth test suite."""

from __future__ import annotations

import pytest

# OAuth-related environment variables managed by these fixtures.
OAUTH_ENV_VARS = (
    "USE_ARCGIS_OAUTH",
    "ARCGIS_PORTAL_URL",
    "ARCGIS_OAUTH_CLIENT_ID",
    "ARCGIS_OAUTH_CLIENT_SECRET",
    "MCP_SERVER_BASE_URL",
    "ARCGIS_VERIFY_SSL",
)


@pytest.fixture()
def clean_oauth_env(monkeypatch):
    """Clear all OAuth-related environment variables for a clean test slate.

    Removes each variable from the environment before the test runs.
    Variables are automatically restored after the test by monkeypatch teardown.
    """
    for var in OAUTH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def oauth_env(monkeypatch, clean_oauth_env):
    """Set all required OAuth environment variables to valid test values.

    Depends on ``clean_oauth_env`` to ensure a clean baseline before setting
    values. Provides a fully configured environment suitable for tests that
    expect ``create_auth_provider()`` to succeed.
    """
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("MCP_SERVER_BASE_URL", "http://localhost:8888")
    monkeypatch.setenv("ARCGIS_VERIFY_SSL", "true")
