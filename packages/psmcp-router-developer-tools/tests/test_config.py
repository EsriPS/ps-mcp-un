"""Tests for psmcp_router_developer_tools.config — env var parsing."""

import json
import logging

import pytest


@pytest.fixture(autouse=True)
def _clean_config_env(monkeypatch):
    """Remove config-related env vars before each test."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("DEVTOOLS_CACHE_TTL_MINUTES", raising=False)
    monkeypatch.delenv("DEVTOOLS_SKILL_SOURCES", raising=False)
    monkeypatch.delenv("DEVTOOLS_SAMPLE_SOURCES", raising=False)


# ── Module-level constants ───────────────────────────────────────────────────


def test_github_token_reads_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
    # Re-import to pick up the new env value
    import importlib

    import psmcp_router_developer_tools.config as cfg

    importlib.reload(cfg)
    assert cfg.GITHUB_TOKEN == "ghp_test123"


def test_github_token_none_when_unset(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    import importlib

    import psmcp_router_developer_tools.config as cfg

    importlib.reload(cfg)
    assert cfg.GITHUB_TOKEN is None


def test_cache_ttl_default_is_60(monkeypatch):
    monkeypatch.delenv("DEVTOOLS_CACHE_TTL_MINUTES", raising=False)
    import importlib

    import psmcp_router_developer_tools.config as cfg

    importlib.reload(cfg)
    assert cfg.CACHE_TTL_MINUTES == 60


def test_cache_ttl_reads_env(monkeypatch):
    monkeypatch.setenv("DEVTOOLS_CACHE_TTL_MINUTES", "120")
    import importlib

    import psmcp_router_developer_tools.config as cfg

    importlib.reload(cfg)
    assert cfg.CACHE_TTL_MINUTES == 120


# ── load_skill_sources ───────────────────────────────────────────────────────


def test_load_skill_sources_empty_when_unset(monkeypatch):
    monkeypatch.delenv("DEVTOOLS_SKILL_SOURCES", raising=False)
    from psmcp_router_developer_tools.config import load_skill_sources

    assert load_skill_sources() == []


def test_load_skill_sources_empty_string(monkeypatch):
    monkeypatch.setenv("DEVTOOLS_SKILL_SOURCES", "")
    from psmcp_router_developer_tools.config import load_skill_sources

    assert load_skill_sources() == []


def test_load_skill_sources_valid_json_array(monkeypatch):
    sources = [
        {"type": "github", "url": "https://github.com/owner/repo"},
        {"type": "local", "path": "/tmp/skills"},
    ]
    monkeypatch.setenv("DEVTOOLS_SKILL_SOURCES", json.dumps(sources))
    from psmcp_router_developer_tools.config import load_skill_sources

    result = load_skill_sources()
    assert result == sources


def test_load_skill_sources_invalid_json_returns_empty(monkeypatch, caplog):
    monkeypatch.setenv("DEVTOOLS_SKILL_SOURCES", "not valid json {{{")
    from psmcp_router_developer_tools.config import load_skill_sources

    with caplog.at_level(logging.ERROR):
        result = load_skill_sources()
    assert result == []
    assert "Invalid JSON in DEVTOOLS_SKILL_SOURCES" in caplog.text


def test_load_skill_sources_non_array_returns_empty(monkeypatch, caplog):
    monkeypatch.setenv("DEVTOOLS_SKILL_SOURCES", json.dumps({"type": "github"}))
    from psmcp_router_developer_tools.config import load_skill_sources

    with caplog.at_level(logging.ERROR):
        result = load_skill_sources()
    assert result == []
    assert "DEVTOOLS_SKILL_SOURCES must be a JSON array" in caplog.text


# ── load_sample_sources ──────────────────────────────────────────────────────


def test_load_sample_sources_empty_when_unset(monkeypatch):
    monkeypatch.delenv("DEVTOOLS_SAMPLE_SOURCES", raising=False)
    from psmcp_router_developer_tools.config import load_sample_sources

    assert load_sample_sources() == []


def test_load_sample_sources_empty_string(monkeypatch):
    monkeypatch.setenv("DEVTOOLS_SAMPLE_SOURCES", "")
    from psmcp_router_developer_tools.config import load_sample_sources

    assert load_sample_sources() == []


def test_load_sample_sources_valid_json_array(monkeypatch):
    sources = [
        {"type": "github", "name": "samples", "url": "https://github.com/owner/samples"},
        {"type": "local", "name": "local-samples", "path": "/tmp/samples"},
    ]
    monkeypatch.setenv("DEVTOOLS_SAMPLE_SOURCES", json.dumps(sources))
    from psmcp_router_developer_tools.config import load_sample_sources

    result = load_sample_sources()
    assert result == sources


def test_load_sample_sources_invalid_json_returns_empty(monkeypatch, caplog):
    monkeypatch.setenv("DEVTOOLS_SAMPLE_SOURCES", "broken json!!!")
    from psmcp_router_developer_tools.config import load_sample_sources

    with caplog.at_level(logging.ERROR):
        result = load_sample_sources()
    assert result == []
    assert "Invalid JSON in DEVTOOLS_SAMPLE_SOURCES" in caplog.text


def test_load_sample_sources_non_array_returns_empty(monkeypatch, caplog):
    monkeypatch.setenv("DEVTOOLS_SAMPLE_SOURCES", json.dumps("just a string"))
    from psmcp_router_developer_tools.config import load_sample_sources

    with caplog.at_level(logging.ERROR):
        result = load_sample_sources()
    assert result == []
    assert "DEVTOOLS_SAMPLE_SOURCES must be a JSON array" in caplog.text
