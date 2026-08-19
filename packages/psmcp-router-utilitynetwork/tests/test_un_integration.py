"""Integration tests for utility network metadata and trace tools.

These tests run against a live ArcGIS Enterprise utility network service.
They require the following environment variables to be set:

- UN_TEST_PORTAL_URL: Portal URL (e.g. https://util-ent01.esri.com/portal)
- UN_TEST_USERNAME: Portal username
- UN_TEST_PASSWORD: Portal password
- UN_TEST_SERVICE_URL: FeatureServer URL
- UN_TEST_GLOBAL_ID: A valid network feature GlobalID for trace tests

Run with::

    pytest -m integration packages/psmcp-router-utilitynetwork/tests/test_un_integration.py -v
"""

import os
from typing import Any

import pytest
from arcgis.gis import GIS
from psmcp_router_utilitynetwork import metadata
from psmcp_router_utilitynetwork.metadata import (
    network_get_metadata,
    network_refresh_metadata,
)
from psmcp_router_utilitynetwork.utility_network_service import (
    network_device_terminals,
    network_downstream_trace,
    network_list_named_traces,
    network_upstream_trace,
)

# ---------------------------------------------------------------------------
# Module-level skip + integration marker
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not all(
            [
                os.getenv("UN_TEST_PORTAL_URL"),
                os.getenv("UN_TEST_USERNAME"),
                os.getenv("UN_TEST_PASSWORD"),
                os.getenv("UN_TEST_SERVICE_URL"),
            ]
        ),
        reason="UN integration env vars not set",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def un_connection() -> dict[str, Any]:
    """Connect to the ArcGIS portal and return service connection details.

    Returns a dict with keys: service_url, token, global_id.
    """
    portal_url = os.environ["UN_TEST_PORTAL_URL"]
    username = os.environ["UN_TEST_USERNAME"]
    password = os.environ["UN_TEST_PASSWORD"]
    service_url = os.environ["UN_TEST_SERVICE_URL"]
    global_id = os.getenv("UN_TEST_GLOBAL_ID", "")

    # Disable SSL verification for self-signed certs in test environments
    os.environ["ARCGIS_VERIFY_SSL"] = "false"

    gis = GIS(url=portal_url, username=username, password=password, verify_cert=False)
    token = gis._con.token

    return {
        "service_url": service_url,
        "token": token,
        "global_id": global_id,
    }


@pytest.fixture(autouse=True)
def _reset_metadata_cache() -> None:
    """Invalidate the metadata cache before each test for isolation."""
    metadata._invalidate_data_element_cache()
    yield
    metadata._invalidate_data_element_cache()


# ---------------------------------------------------------------------------
# Metadata tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_domain_networks_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_get_metadata(section='domain_networks') returns at least one domain network."""
    result = await network_get_metadata(
        section="domain_networks",
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["count"] >= 1
    for dn in result["domainNetworks"]:
        assert "domainNetworkName" in dn
        assert isinstance(dn["tiers"], list)


@pytest.mark.asyncio
async def test_get_asset_types_returns_sources(
    un_connection: dict[str, Any],
) -> None:
    """network_get_metadata(section='asset_types') returns sources with asset groups."""
    result = await network_get_metadata(
        section="asset_types",
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["totalAssetGroups"] >= 1
    assert len(result["sources"]) > 0


@pytest.mark.asyncio
async def test_get_asset_types_filter_by_domain_network(
    un_connection: dict[str, Any],
) -> None:
    """network_get_metadata(section='asset_types') filtered by domain_network returns only that domain."""
    # First get available domain networks
    domains = await network_get_metadata(
        section="domain_networks",
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )
    assert domains["count"] >= 1
    domain_name = domains["domainNetworks"][0]["domainNetworkName"]

    # Filter asset types by that domain network
    result = await network_get_metadata(
        section="asset_types",
        domain_network=domain_name,
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert len(result["sources"]) > 0
    for source in result["sources"]:
        assert source["domainNetworkName"].lower() == domain_name.lower()


@pytest.mark.asyncio
async def test_get_network_attributes_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_get_metadata(section='network_attributes') returns attributes with name and dataType."""
    result = await network_get_metadata(
        section="network_attributes",
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["count"] >= 1
    for attr in result["networkAttributes"]:
        assert "name" in attr
        assert "dataType" in attr


@pytest.mark.asyncio
async def test_get_terminal_configurations_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_get_metadata(section='terminal_configurations') returns configs with terminals."""
    result = await network_get_metadata(
        section="terminal_configurations",
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["count"] >= 1
    for cfg in result["terminalConfigurations"]:
        assert "terminalConfigurationName" in cfg
        assert isinstance(cfg["terminals"], list)


@pytest.mark.asyncio
async def test_get_categories_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_get_metadata(section='categories') returns categories with name field."""
    result = await network_get_metadata(
        section="categories",
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["count"] >= 1
    for cat in result["categories"]:
        assert "name" in cat


@pytest.mark.asyncio
async def test_refresh_metadata_succeeds(
    un_connection: dict[str, Any],
) -> None:
    """network_refresh_metadata invalidates cache and re-fetches successfully."""
    result = await network_refresh_metadata(
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert "successfully" in result["message"].lower()


# ---------------------------------------------------------------------------
# Trace tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_named_traces_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_list_named_traces returns a list of named trace configurations."""
    result = await network_list_named_traces(
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["count"] >= 0
    for trace in result["namedTraces"]:
        assert "name" in trace
        assert "traceType" in trace


@pytest.mark.asyncio
async def test_device_terminals_returns_terminal_info(
    un_connection: dict[str, Any],
) -> None:
    """network_device_terminals returns terminal info for a network feature."""
    global_id = un_connection["global_id"]
    if not global_id:
        pytest.skip("UN_TEST_GLOBAL_ID not set")

    result = await network_device_terminals(
        global_id=global_id,
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["globalId"] == global_id.strip()
    assert isinstance(result["terminals"], list)
    assert result["terminalCount"] >= 1
    assert "domainNetworkName" in result


@pytest.mark.asyncio
async def test_downstream_trace_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_downstream_trace returns trace results from a valid starting point."""
    global_id = un_connection["global_id"]
    if not global_id:
        pytest.skip("UN_TEST_GLOBAL_ID not set")

    # Get terminals to find the appropriate one for downstream
    terminals_result = await network_device_terminals(
        global_id=global_id,
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    terminals = terminals_result["terminals"]
    # Pick terminal recommended for downstream, or fall back to first
    terminal_id = next(
        (t["terminalId"] for t in terminals if t.get("recommendedFor") == "downstream"),
        terminals[0]["terminalId"] if terminals else None,
    )

    result = await network_downstream_trace(
        starting_global_id=global_id,
        terminal_id=terminal_id,
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["traceType"] == "downstream"
    assert "traceResults" in result


@pytest.mark.asyncio
async def test_upstream_trace_returns_results(
    un_connection: dict[str, Any],
) -> None:
    """network_upstream_trace returns trace results from a valid starting point."""
    global_id = un_connection["global_id"]
    if not global_id:
        pytest.skip("UN_TEST_GLOBAL_ID not set")

    # Get terminals to find the appropriate one for upstream
    terminals_result = await network_device_terminals(
        global_id=global_id,
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    terminals = terminals_result["terminals"]
    # Pick terminal recommended for upstream, or fall back to first
    terminal_id = next(
        (t["terminalId"] for t in terminals if t.get("recommendedFor") == "upstream"),
        terminals[0]["terminalId"] if terminals else None,
    )

    result = await network_upstream_trace(
        starting_global_id=global_id,
        terminal_id=terminal_id,
        network_service_url=un_connection["service_url"],
        token=un_connection["token"],
    )

    assert result["traceType"] == "upstream"
    assert "traceResults" in result
