"""Tests for auth plugin discovery and server auth mode selection.

Validates Requirements 5.1, 5.2, 5.3:
- Plugin discovery activates the first non-None provider
- Plugin takes precedence over USE_ARCGIS_AUTH
- Fallback to USE_ARCGIS_AUTH when no plugin activates
- No auth when neither plugin nor USE_ARCGIS_AUTH is set
"""

from __future__ import annotations

import importlib.metadata
import logging

import pytest
from conftest import FakeEntryPoint

from psmcp.server import _discover_auth_plugin, _init_server

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_server_globals(monkeypatch):
    """Reset module-level server globals before each test."""
    import psmcp.server as srv

    monkeypatch.setattr(srv, "_mcp", None)
    monkeypatch.setattr(srv, "_mounted_routers", [])


@pytest.fixture()
def fake_auth_entry_points(monkeypatch):
    """Factory for installing a controlled set of fake auth entry points.

    Usage::

        def test_x(fake_auth_entry_points):
            fake_auth_entry_points([
                FakeEntryPoint("my_plugin", "my_mod:factory", group="psmcp.auth",
                               loader=lambda: my_factory_fn),
            ])
    """

    def _install(eps: list[FakeEntryPoint]):
        def _fake_entry_points(group: str | None = None, **_kwargs):
            if group == "psmcp.auth":
                return eps
            # Fall through to empty for other groups (routers, etc.)
            return []

        monkeypatch.setattr(importlib.metadata, "entry_points", _fake_entry_points)
        return eps

    return _install


@pytest.fixture()
def no_routers(monkeypatch):
    """Prevent router loading during _init_server tests."""
    import psmcp.server as srv

    monkeypatch.setattr(srv, "_load_and_mount_routers", lambda mcp: [])


# ---------------------------------------------------------------------------
# Tests for _discover_auth_plugin()
# ---------------------------------------------------------------------------


class TestDiscoverAuthPlugin:
    """Tests for the _discover_auth_plugin() function."""

    def test_activates_first_provider(self, fake_auth_entry_points):
        """First factory returning non-None wins; subsequent factories are not called."""
        sentinel_provider = object()
        second_called = []

        def factory_a():
            return sentinel_provider

        def factory_b():
            second_called.append(True)
            return object()

        fake_auth_entry_points(
            [
                FakeEntryPoint(
                    "plugin_a", "mod_a:factory", group="psmcp.auth", loader=lambda: factory_a
                ),
                FakeEntryPoint(
                    "plugin_b", "mod_b:factory", group="psmcp.auth", loader=lambda: factory_b
                ),
            ]
        )

        result = _discover_auth_plugin()

        assert result is sentinel_provider
        assert second_called == [], "Second factory should not be called"

    def test_returns_none_when_no_plugins(self, fake_auth_entry_points):
        """Empty entry points returns None."""
        fake_auth_entry_points([])

        result = _discover_auth_plugin()

        assert result is None

    def test_raises_on_plugin_error(self, fake_auth_entry_points):
        """Plugin exception propagates to caller (fail-fast)."""

        def bad_factory():
            raise RuntimeError("plugin init failed")

        fake_auth_entry_points(
            [
                FakeEntryPoint(
                    "bad_plugin", "mod:factory", group="psmcp.auth", loader=lambda: bad_factory
                ),
            ]
        )

        with pytest.raises(RuntimeError, match="plugin init failed"):
            _discover_auth_plugin()

    def test_skips_none_returning_factory(self, fake_auth_entry_points):
        """A factory returning None is skipped; next factory is tried."""
        sentinel_provider = object()

        def factory_none():
            return None

        def factory_good():
            return sentinel_provider

        fake_auth_entry_points(
            [
                FakeEntryPoint(
                    "skip_me", "mod:factory", group="psmcp.auth", loader=lambda: factory_none
                ),
                FakeEntryPoint(
                    "use_me", "mod:factory", group="psmcp.auth", loader=lambda: factory_good
                ),
            ]
        )

        result = _discover_auth_plugin()

        assert result is sentinel_provider


# ---------------------------------------------------------------------------
# Tests for _init_server() auth mode selection
# ---------------------------------------------------------------------------


class TestInitServerAuthMode:
    """Tests for auth mode selection in _init_server()."""

    def test_plugin_precedence_over_use_arcgis_auth(
        self, fake_auth_entry_points, no_routers, monkeypatch, caplog
    ):
        """Plugin wins over USE_ARCGIS_AUTH=True, WARNING is logged."""
        sentinel_provider = object()

        def factory():
            return sentinel_provider

        fake_auth_entry_points(
            [
                FakeEntryPoint(
                    "oauth_plugin", "mod:factory", group="psmcp.auth", loader=lambda: factory
                ),
            ]
        )
        monkeypatch.setenv("USE_ARCGIS_AUTH", "True")

        with caplog.at_level(logging.WARNING, logger="psmcp.server"):
            mcp = _init_server()

        # The plugin's provider should be used
        assert mcp.auth is sentinel_provider

        # A warning should be logged about USE_ARCGIS_AUTH being ignored
        assert any("USE_ARCGIS_AUTH" in record.getMessage() for record in caplog.records)
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_fallback_to_use_arcgis_auth(self, fake_auth_entry_points, no_routers, monkeypatch):
        """No plugin → USE_ARCGIS_AUTH=True → ArcGISAuthProvider is used."""
        fake_auth_entry_points([])
        monkeypatch.setenv("USE_ARCGIS_AUTH", "True")
        monkeypatch.setenv("ARCGIS_PORTAL_URL", "https://portal.example.com/portal")

        mcp = _init_server()

        from psmcp.core.auth.arcgis_provider import ArcGISAuthProvider

        assert isinstance(mcp.auth, ArcGISAuthProvider)

    def test_no_plugin_no_auth(self, fake_auth_entry_points, no_routers, monkeypatch):
        """No plugin, no USE_ARCGIS_AUTH → auth_provider is None."""
        fake_auth_entry_points([])
        monkeypatch.delenv("USE_ARCGIS_AUTH", raising=False)

        mcp = _init_server()

        assert mcp.auth is None
