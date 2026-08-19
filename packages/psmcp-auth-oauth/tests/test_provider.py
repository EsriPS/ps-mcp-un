"""Unit tests for the psmcp_auth_oauth provider factory function."""

from __future__ import annotations

import pytest
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from psmcp_auth_oauth import ArcGISOAuthConfigError, create_auth_provider

# ---------------------------------------------------------------------------
# Requirement 1.8, 6.1 — Factory returns None when not enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "use_oauth_value",
    [
        None,  # unset
        "",  # empty
        "false",
        "0",
    ],
    ids=["unset", "empty", "false", "zero"],
)
def test_factory_returns_none_when_not_enabled(clean_oauth_env, monkeypatch, use_oauth_value):
    """Factory returns None for values that are not case-insensitive 'true'."""
    if use_oauth_value is not None:
        monkeypatch.setenv("USE_ARCGIS_OAUTH", use_oauth_value)

    result = create_auth_provider()
    assert result is None


@pytest.mark.parametrize(
    "use_oauth_value",
    ["False", "FALSE", "no"],
    ids=["False", "FALSE", "no"],
)
def test_factory_returns_none_case_insensitive(clean_oauth_env, monkeypatch, use_oauth_value):
    """Factory returns None for various non-'true' casing variants."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", use_oauth_value)

    result = create_auth_provider()
    assert result is None


# ---------------------------------------------------------------------------
# Requirements 1.3, 1.4, 1.5, 6.6 — Factory raises on missing config
# ---------------------------------------------------------------------------


def test_factory_raises_missing_portal_url(clean_oauth_env, monkeypatch):
    """Raises ArcGISOAuthConfigError naming ARCGIS_PORTAL_URL when missing."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")

    with pytest.raises(ArcGISOAuthConfigError, match="ARCGIS_PORTAL_URL"):
        create_auth_provider()


def test_factory_raises_missing_client_id(clean_oauth_env, monkeypatch):
    """Raises ArcGISOAuthConfigError naming ARCGIS_OAUTH_CLIENT_ID when missing."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")

    with pytest.raises(ArcGISOAuthConfigError, match="ARCGIS_OAUTH_CLIENT_ID"):
        create_auth_provider()


def test_factory_raises_missing_client_secret(clean_oauth_env, monkeypatch):
    """Raises ArcGISOAuthConfigError naming ARCGIS_OAUTH_CLIENT_SECRET when missing."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")

    with pytest.raises(ArcGISOAuthConfigError, match="ARCGIS_OAUTH_CLIENT_SECRET"):
        create_auth_provider()


def test_factory_raises_multiple_missing(clean_oauth_env, monkeypatch):
    """Error message names all missing variables when multiple are absent."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    # All three required vars are missing

    with pytest.raises(ArcGISOAuthConfigError) as exc_info:
        create_auth_provider()

    error_msg = str(exc_info.value)
    assert "ARCGIS_PORTAL_URL" in error_msg
    assert "ARCGIS_OAUTH_CLIENT_ID" in error_msg
    assert "ARCGIS_OAUTH_CLIENT_SECRET" in error_msg


# ---------------------------------------------------------------------------
# Requirements 1.1, 1.6, 1.7 — Factory returns configured OAuthProxy
# ---------------------------------------------------------------------------


def test_factory_returns_proxy_when_configured(oauth_env):
    """Returns an OAuthProxy instance with correctly derived endpoints."""
    result = create_auth_provider()

    assert isinstance(result, OAuthProxy)
    # Verify upstream endpoints are derived from ARCGIS_PORTAL_URL
    assert (
        result._upstream_authorization_endpoint
        == "https://portal.example.com/portal/sharing/rest/oauth2/authorize"
    )
    assert (
        result._upstream_token_endpoint
        == "https://portal.example.com/portal/sharing/rest/oauth2/token"
    )


def test_endpoint_derivation_strips_trailing_slash(clean_oauth_env, monkeypatch):
    """Portal URLs with trailing slashes are normalized before endpoint derivation."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal/")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    assert (
        result._upstream_authorization_endpoint
        == "https://portal.example.com/portal/sharing/rest/oauth2/authorize"
    )
    assert (
        result._upstream_token_endpoint
        == "https://portal.example.com/portal/sharing/rest/oauth2/token"
    )

    # Also test multiple trailing slashes
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal///")
    result2 = create_auth_provider()
    assert isinstance(result2, OAuthProxy)
    assert (
        result2._upstream_authorization_endpoint
        == "https://portal.example.com/portal/sharing/rest/oauth2/authorize"
    )
    assert (
        result2._upstream_token_endpoint
        == "https://portal.example.com/portal/sharing/rest/oauth2/token"
    )


# ---------------------------------------------------------------------------
# Requirements 6.4 — Base URL default
# ---------------------------------------------------------------------------


def test_base_url_default(clean_oauth_env, monkeypatch):
    """Defaults to http://localhost:8888 when MCP_SERVER_BASE_URL is unset."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")
    # MCP_SERVER_BASE_URL is NOT set (cleaned by clean_oauth_env)

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    assert str(result.base_url).rstrip("/") == "http://localhost:8888"


# ---------------------------------------------------------------------------
# Requirements 4.5 — TLS verification settings
# ---------------------------------------------------------------------------


def test_verify_ssl_default_true(oauth_env, monkeypatch):
    """TLS verification is enabled by default."""
    monkeypatch.delenv("ARCGIS_VERIFY_SSL", raising=False)

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    # The token_validator should have verify_ssl=True
    assert result._token_validator.verify_ssl is True


def test_verify_ssl_false(oauth_env, monkeypatch):
    """TLS verification is disabled when ARCGIS_VERIFY_SSL=false."""
    monkeypatch.setenv("ARCGIS_VERIFY_SSL", "false")

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    assert result._token_validator.verify_ssl is False


# ---------------------------------------------------------------------------
# ArcGIS Online compatibility
# ---------------------------------------------------------------------------


def test_factory_works_with_arcgis_online_url(clean_oauth_env, monkeypatch):
    """Factory correctly derives endpoints for ArcGIS Online."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://www.arcgis.com")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    assert (
        result._upstream_authorization_endpoint
        == "https://www.arcgis.com/sharing/rest/oauth2/authorize"
    )
    assert result._upstream_token_endpoint == "https://www.arcgis.com/sharing/rest/oauth2/token"


def test_factory_normalizes_arcgis_online_sharing_rest_url(clean_oauth_env, monkeypatch):
    """Factory strips /sharing/rest suffix from ArcGIS Online URLs."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://www.arcgis.com/sharing/rest")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    assert (
        result._upstream_authorization_endpoint
        == "https://www.arcgis.com/sharing/rest/oauth2/authorize"
    )
    assert result._upstream_token_endpoint == "https://www.arcgis.com/sharing/rest/oauth2/token"


def test_factory_works_with_org_subdomain(clean_oauth_env, monkeypatch):
    """Factory correctly derives endpoints for org-specific ArcGIS Online URLs."""
    monkeypatch.setenv("USE_ARCGIS_OAUTH", "true")
    monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://myorg.maps.arcgis.com")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_ID", "test-id")
    monkeypatch.setenv("ARCGIS_OAUTH_CLIENT_SECRET", "test-secret")

    result = create_auth_provider()
    assert isinstance(result, OAuthProxy)
    assert (
        result._upstream_authorization_endpoint
        == "https://myorg.maps.arcgis.com/sharing/rest/oauth2/authorize"
    )
    assert (
        result._upstream_token_endpoint == "https://myorg.maps.arcgis.com/sharing/rest/oauth2/token"
    )
