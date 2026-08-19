"""Tests for the psmcp CLI (argparse + router subcommands)."""

import subprocess
import sys

import pytest


class TestCLIHelp:
    def test_main_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        assert "serve" in result.stdout
        assert "router" in result.stdout

    def test_router_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "router", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "enable" in result.stdout
        assert "disable" in result.stdout
        assert "install" in result.stdout


class TestCLIRouterList:
    def test_router_list_runs_successfully(self):
        """Verify router list runs without error.

        We only check the command succeeds and prints the expected header — we
        do *not* assert specific router names because that would require every
        router package to be installed in the test environment.
        """
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "router", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        assert "Discovered" in result.stdout


def _get_discovered_routers(env=None) -> list[str]:
    """Return names of installed router packages, or empty list if none."""
    result = subprocess.run(
        [sys.executable, "-m", "psmcp", "router", "list"],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )
    if result.returncode != 0:
        return []
    names = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        # Router lines always contain "[enabled...]" or "[disabled]".
        # Other output lines (headers, "(none ...)" messages) do not.
        if "[" in stripped:
            parts = stripped.split()
            if parts:
                names.append(parts[0])
    return names


class TestCLIRouterEnableDisable:
    def test_enable_then_disable(self, monkeypatch, tmp_path):
        env = {
            **dict(__import__("os").environ),
            "PSMCP_CONFIG_DIR": str(tmp_path),
        }

        available = _get_discovered_routers(env=env)
        if not available:
            pytest.skip("No router packages installed; skipping enable/disable test")

        router_name = available[0]

        # Enable
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "router", "enable", router_name],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        assert result.returncode == 0
        assert router_name in result.stdout

        # Verify in list
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "router", "list"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        assert "[enabled]" in result.stdout

        # Disable
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "router", "disable", router_name],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        assert result.returncode == 0

    def test_enable_nonexistent_fails(self):
        result = subprocess.run(
            [sys.executable, "-m", "psmcp", "router", "enable", "nonexistent_router"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
