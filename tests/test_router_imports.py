"""Tests for individual router package imports + the consolidated psmcp.core API."""

from __future__ import annotations

import re

import pytest
from fastmcp import FastMCP


class TestRouterImports:
    """Each router package exports a FastMCP instance under a known name."""

    def test_import_feature_service(self):
        from psmcp_router_feature_service import feature_service_router

        assert isinstance(feature_service_router, FastMCP)
        assert feature_service_router.name == "Feature Service"

    def test_import_arcgis(self):
        from psmcp_router_arcgis import arcgis_router

        assert isinstance(arcgis_router, FastMCP)

    def test_import_geoprocessing(self):
        from psmcp_router_geoprocessing import geoprocessing_router

        assert isinstance(geoprocessing_router, FastMCP)

    def test_import_location_services(self):
        from psmcp_router_location_services import location_services_router

        assert isinstance(location_services_router, FastMCP)


class TestCoreImports:
    """``psmcp.core`` re-exports the shared utilities used by every router."""

    def test_import_resolve_token(self):
        from psmcp.core.auth import resolve_token

        assert callable(resolve_token)

    def test_import_config(self):
        from psmcp.core.config import get_config_dir, load_enabled_routers

        assert callable(get_config_dir)
        assert callable(load_enabled_routers)

    def test_import_utils(self):
        from psmcp.core.utils import setup_logging

        assert callable(setup_logging)

    def test_top_level_psmcp_core_reexports(self):
        from psmcp import core

        for name in ("resolve_token", "setup_logging", "get_config_dir"):
            assert hasattr(core, name), name


class TestResolveToken:
    def test_returns_none_by_default(self, monkeypatch):
        monkeypatch.delenv("ARCGIS_TOKEN", raising=False)
        from psmcp.core.auth import resolve_token

        assert resolve_token() is None

    def test_explicit(self):
        from psmcp.core.auth import resolve_token

        assert resolve_token("my-token") == "my-token"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("ARCGIS_TOKEN", "env-token")
        from psmcp.core.auth import resolve_token

        assert resolve_token() == "env-token"

    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv("ARCGIS_TOKEN", "env-token")
        from psmcp.core.auth import resolve_token

        assert resolve_token("explicit-token") == "explicit-token"

    def test_required_raises(self, monkeypatch):
        monkeypatch.delenv("ARCGIS_TOKEN", raising=False)
        from psmcp.core.auth import resolve_token

        with pytest.raises(ValueError, match="No authentication token"):
            resolve_token(required=True)


class TestVersion:
    """``psmcp.__version__`` is exposed and looks like a PEP 440 string."""

    def test_version_attribute_exists(self):
        import psmcp

        assert isinstance(psmcp.__version__, str)
        assert psmcp.__version__

    def test_version_looks_like_pep440(self):
        import psmcp

        # Accept any version that starts with digit groups; tolerates dev/local
        # segments produced by hatch-vcs between tags.
        pattern = re.compile(r"^\d+\.\d+(\.\d+)?")
        assert pattern.match(psmcp.__version__), psmcp.__version__


class TestArcGISTokenVerifier:
    """Unit tests for the ``verify_ssl`` default in :class:`ArcGISTokenVerifier`."""

    def test_verify_ssl_defaults_to_true_when_env_unset(self, monkeypatch):
        """When ARCGIS_VERIFY_SSL is not set, SSL verification must default to True."""
        monkeypatch.delenv("ARCGIS_VERIFY_SSL", raising=False)
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com")
        assert verifier.verify_ssl is True

    def test_verify_ssl_false_when_env_is_false(self, monkeypatch):
        """Setting ARCGIS_VERIFY_SSL=false must disable SSL verification."""
        monkeypatch.setenv("ARCGIS_VERIFY_SSL", "false")
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com")
        assert verifier.verify_ssl is False

    def test_verify_ssl_false_when_env_is_False_capitalised(self, monkeypatch):
        """ARCGIS_VERIFY_SSL comparison is case-insensitive."""
        monkeypatch.setenv("ARCGIS_VERIFY_SSL", "False")
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com")
        assert verifier.verify_ssl is False

    def test_verify_ssl_explicit_true_overrides_env(self, monkeypatch):
        """Explicit verify_ssl=True overrides a 'false' env var."""
        monkeypatch.setenv("ARCGIS_VERIFY_SSL", "false")
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", verify_ssl=True)
        assert verifier.verify_ssl is True

    def test_verify_ssl_explicit_false_overrides_env(self, monkeypatch):
        """Explicit verify_ssl=False overrides a 'true' env var."""
        monkeypatch.setenv("ARCGIS_VERIFY_SSL", "true")
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", verify_ssl=False)
        assert verifier.verify_ssl is False

    def test_missing_portal_url_raises(self, monkeypatch):
        """Constructor raises ValueError when neither argument nor env var provides a URL."""
        monkeypatch.delenv("ARCGIS_PORTAL_URL", raising=False)
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        with pytest.raises(ValueError, match="ARCGIS_PORTAL_URL"):
            ArcGISTokenVerifier()
