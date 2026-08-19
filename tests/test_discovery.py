"""Tests for entry-point discovery and router enablement priority."""

from __future__ import annotations

import json

import pytest

from psmcp.server import _discover_routers, _get_enabled_router_names

EXPECTED_ROUTERS = {
    "arcgis",
    "feature_service",
    "geoprocessing",
    "location_services",
    "mongo",
    "postgres",
}


@pytest.fixture()
def all_fakes(fake_router_entry_points):
    """Install fake entry points for the canonical router set."""
    fake_router_entry_points(EXPECTED_ROUTERS)
    return EXPECTED_ROUTERS


class TestDiscoverRouters:
    def test_all_routers_discovered(self, all_fakes):
        assert set(_discover_routers().keys()) == all_fakes

    @pytest.mark.parametrize("name", sorted(EXPECTED_ROUTERS))
    def test_entry_point_valid(self, name, all_fakes):
        ep = _discover_routers()[name]
        assert ep.group == "psmcp.routers"
        assert ep.name == name
        assert ep.value


class TestGetEnabledRouterNames:
    """``_get_enabled_router_names`` honors env > config > all-discovered priority."""

    @staticmethod
    def _fake() -> dict[str, None]:
        return {n: None for n in EXPECTED_ROUTERS}

    def test_defaults_to_all(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ENABLED_ROUTERS", raising=False)
        monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
        assert set(_get_enabled_router_names(self._fake())) == EXPECTED_ROUTERS

    def test_env_var_overrides(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENABLED_ROUTERS", "arcgis,feature_service")
        monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
        assert _get_enabled_router_names(self._fake()) == ["arcgis", "feature_service"]

    def test_env_var_ignores_unknown(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENABLED_ROUTERS", "arcgis,bogus")
        monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
        assert _get_enabled_router_names(self._fake()) == ["arcgis"]

    def test_env_all_unknown_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENABLED_ROUTERS", "bogus1,bogus2")
        monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
        assert set(_get_enabled_router_names(self._fake())) == EXPECTED_ROUTERS

    def test_config_file_used(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ENABLED_ROUTERS", raising=False)
        monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
        (tmp_path / "routers.json").write_text(json.dumps({"enabled": ["arcgis", "mongo"]}))
        assert _get_enabled_router_names(self._fake()) == ["arcgis", "mongo"]

    def test_env_beats_config(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENABLED_ROUTERS", "geoprocessing")
        monkeypatch.setenv("PSMCP_CONFIG_DIR", str(tmp_path))
        (tmp_path / "routers.json").write_text(json.dumps({"enabled": ["arcgis"]}))
        assert _get_enabled_router_names(self._fake()) == ["geoprocessing"]
