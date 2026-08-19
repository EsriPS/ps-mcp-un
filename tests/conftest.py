"""Shared pytest fixtures for the PS-MCP test suite."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable

import pytest

# ---------------------------------------------------------------------------
# Filesystem / config dir fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_config_dir(tmp_path, monkeypatch):
    """Point ``PSMCP_CONFIG_DIR`` at an isolated temp directory.

    Most config-touching tests should depend on this fixture so they don't
    pollute the user's real ``~/.psmcp/`` directory.
    """
    monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def clean_env(monkeypatch):
    """Strip PS-MCP-related environment variables to give tests a clean slate."""
    for var in (
        "ARCGIS_TOKEN",
        "ARCGIS_PORTAL_URL",
        "ARCGIS_VERIFY_SSL",
        "USE_ARCGIS_AUTH",
        "ENABLED_ROUTERS",
        "MCP_TRANSPORT",
        "MCP_HOST",
        "MCP_PORT",
        "MCP_STATELESS_HTTP",
        "FASTMCP_STATELESS_HTTP",
        "PSMCP_CONFIG_DIR",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Entry-point fakes for router-discovery tests
# ---------------------------------------------------------------------------


class FakeEntryPoint:
    """Minimal stand-in for ``importlib.metadata.EntryPoint``.

    Tests that exercise router discovery don't need the real packages installed;
    they just need objects with ``.name``, ``.value``, ``.group``, and an
    optional ``.load()`` callable.
    """

    def __init__(
        self,
        name: str,
        value: str,
        *,
        group: str = "psmcp.routers",
        loader=None,
    ):
        self.name = name
        self.value = value
        self.group = group
        self._loader = loader

    def load(self):
        if self._loader is None:
            raise RuntimeError(f"FakeEntryPoint {self.name!r} has no loader configured")
        return self._loader()


@pytest.fixture()
def fake_router_entry_points(monkeypatch):
    """Factory for installing a controlled set of fake router entry points.

    Usage::

        def test_x(fake_router_entry_points):
            fake_router_entry_points(["arcgis", "mongo"])
            # importlib.metadata.entry_points(group="psmcp.routers") now returns
            # only those two entries.
    """

    def _install(names: Iterable[str]):
        eps = [FakeEntryPoint(name, f"psmcp_router_{name}:router") for name in names]

        def _fake_entry_points(group: str | None = None, **_kwargs):
            return eps if group == "psmcp.routers" else []

        monkeypatch.setattr(importlib.metadata, "entry_points", _fake_entry_points)
        return eps

    return _install
