"""Tests for ``psmcp.core.config`` — routers.json management."""

from __future__ import annotations

from psmcp.core.config import (
    add_router,
    get_config_dir,
    load_enabled_routers,
    remove_router,
    save_enabled_routers,
)

# ── get_config_dir ───────────────────────────────────────────────────────────


def test_get_config_dir_from_env(tmp_config_dir):
    assert get_config_dir() == tmp_config_dir


def test_get_config_dir_creates_directory(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "config"
    monkeypatch.setenv("PSMCP_CONFIG_DIR", str(target))
    result = get_config_dir()
    assert result == target
    assert target.is_dir()


# ── load / save ──────────────────────────────────────────────────────────────


def test_load_returns_none_when_no_file(tmp_config_dir):
    assert load_enabled_routers() is None


def test_save_then_load(tmp_config_dir):
    save_enabled_routers(["arcgis", "feature_service"])
    assert load_enabled_routers() == ["arcgis", "feature_service"]


def test_save_deduplicates_and_sorts(tmp_config_dir):
    save_enabled_routers(["mongo", "arcgis", "mongo"])
    assert load_enabled_routers() == ["arcgis", "mongo"]


def test_load_with_corrupt_json(tmp_config_dir):
    (tmp_config_dir / "routers.json").write_text("NOT JSON {{{{")
    assert load_enabled_routers() is None


# ── add / remove ─────────────────────────────────────────────────────────────


def test_add_router(tmp_config_dir):
    result = add_router("arcgis")
    assert "arcgis" in result
    assert load_enabled_routers() == ["arcgis"]


def test_add_router_idempotent(tmp_config_dir):
    add_router("arcgis")
    result = add_router("arcgis")
    assert result.count("arcgis") == 1


def test_add_multiple_routers(tmp_config_dir):
    add_router("arcgis")
    add_router("feature_service")
    enabled = load_enabled_routers()
    assert "arcgis" in enabled
    assert "feature_service" in enabled


def test_remove_router(tmp_config_dir):
    add_router("arcgis")
    add_router("feature_service")
    result = remove_router("arcgis")
    assert "arcgis" not in result
    assert "feature_service" in result


def test_remove_nonexistent_is_noop(tmp_config_dir):
    add_router("arcgis")
    assert remove_router("nonexistent") == ["arcgis"]
