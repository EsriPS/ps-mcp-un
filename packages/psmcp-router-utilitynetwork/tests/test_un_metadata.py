"""Tests for the utility network metadata data-element cache."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from psmcp_router_utilitynetwork import metadata


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Ensure each test starts and ends with an empty module-level cache."""
    metadata._invalidate_data_element_cache()
    yield
    metadata._invalidate_data_element_cache()


class TestGetDataElement:
    def test_first_call_fetches_and_returns(self) -> None:
        data_element = {"domainNetworks": []}
        with (
            patch.object(metadata, "_connect_gis", return_value=MagicMock()) as connect,
            patch.object(metadata, "FeatureLayerCollection", return_value=MagicMock()),
            patch.object(metadata, "_un_data_element", return_value=data_element) as fetch,
        ):
            result = metadata._get_data_element("https://server/UN/FeatureServer")

        assert result is data_element
        connect.assert_called_once()
        fetch.assert_called_once()

    def test_second_call_same_url_returns_cached_without_refetch(self) -> None:
        data_element = {"domainNetworks": []}
        with (
            patch.object(metadata, "_connect_gis", return_value=MagicMock()) as connect,
            patch.object(metadata, "FeatureLayerCollection", return_value=MagicMock()),
            patch.object(metadata, "_un_data_element", return_value=data_element) as fetch,
        ):
            first = metadata._get_data_element("https://server/UN/FeatureServer")
            second = metadata._get_data_element("https://server/UN/FeatureServer")

        assert first is second
        connect.assert_called_once()
        fetch.assert_called_once()

    def test_changing_url_triggers_refetch(self) -> None:
        first_de = {"domainNetworks": ["a"]}
        second_de = {"domainNetworks": ["b"]}
        with (
            patch.object(metadata, "_connect_gis", return_value=MagicMock()) as connect,
            patch.object(metadata, "FeatureLayerCollection", return_value=MagicMock()),
            patch.object(metadata, "_un_data_element", side_effect=[first_de, second_de]) as fetch,
        ):
            first = metadata._get_data_element("https://server/UN-A/FeatureServer")
            second = metadata._get_data_element("https://server/UN-B/FeatureServer")

        assert first is first_de
        assert second is second_de
        assert connect.call_count == 2
        assert fetch.call_count == 2

    def test_invalidate_forces_refetch(self) -> None:
        first_de = {"domainNetworks": ["a"]}
        second_de = {"domainNetworks": ["b"]}
        with (
            patch.object(metadata, "_connect_gis", return_value=MagicMock()) as connect,
            patch.object(metadata, "FeatureLayerCollection", return_value=MagicMock()),
            patch.object(metadata, "_un_data_element", side_effect=[first_de, second_de]) as fetch,
        ):
            first = metadata._get_data_element("https://server/UN/FeatureServer")
            metadata._invalidate_data_element_cache()
            second = metadata._get_data_element("https://server/UN/FeatureServer")

        assert first is first_de
        assert second is second_de
        assert connect.call_count == 2
        assert fetch.call_count == 2

    def test_url_normalized_by_rstrip(self) -> None:
        data_element = {"domainNetworks": []}
        flc_factory = MagicMock(return_value=MagicMock())
        with (
            patch.object(metadata, "_connect_gis", return_value=MagicMock()),
            patch.object(metadata, "FeatureLayerCollection", flc_factory),
            patch.object(metadata, "_un_data_element", return_value=data_element),
        ):
            metadata._get_data_element("https://server/UN/FeatureServer/")

        # The trailing slash is stripped before building the FeatureLayerCollection.
        assert flc_factory.call_args.args[0] == "https://server/UN/FeatureServer"


# ---------------------------------------------------------------------------
# Fixtures / helpers for network_get_metadata domain_networks tests
# ---------------------------------------------------------------------------

_DOMAIN_NETWORKS_SAMPLE_DATA_ELEMENT = {
    "domainNetworks": [
        {
            "domainNetworkName": "ElectricDistribution",
            "domainNetworkId": 4,
            "tierDefinition": "esriTDHierarchical",
            "subnetworkTableName": "UN_5_SubnetworkTable",
            "tierGroups": [
                {
                    "name": "Distribution Group",
                    "tiers": [
                        {"name": "Medium Voltage"},
                        {"name": "Low Voltage"},
                    ],
                },
            ],
            "tiers": [
                {
                    "tierId": 1,
                    "name": "Medium Voltage",
                    "rank": 1,
                    "tierGroupName": "Distribution Group",
                    "topologyType": "esriTTMesh",
                    "subnetworkFieldName": "YOURSUBNETWORKFIELD",
                },
                {
                    "tierId": 2,
                    "name": "Low Voltage",
                    "rank": 2,
                    "tierGroupName": "Distribution Group",
                    "topologyType": "esriTTRadial",
                    "subnetworkFieldName": "YOURSUBNETWORKFIELD_LV",
                },
            ],
        },
        {
            "domainNetworkName": "GasDistribution",
            "domainNetworkId": 6,
            "tierDefinition": "esriTDPartitioned",
            "subnetworkTableName": "UN_7_SubnetworkTable",
            "tierGroups": [
                {
                    "name": "Pressure Group",
                    "tiers": [
                        {"name": "High Pressure"},
                    ],
                },
            ],
            "tiers": [
                {
                    "tierId": 1,
                    "name": "High Pressure",
                    "rank": 1,
                    "tierGroupName": "Pressure Group",
                    "topologyType": "esriTTMesh",
                    "subnetworkFieldName": "GASSUBNETWORKFIELD",
                },
            ],
        },
    ],
}


class TestNetworkGetDomainNetworks:
    @pytest.fixture()
    def _mock_data_element(self):
        """Patch _get_data_element to return _DOMAIN_NETWORKS_SAMPLE_DATA_ELEMENT."""
        with patch.object(
            metadata, "_get_data_element", return_value=_DOMAIN_NETWORKS_SAMPLE_DATA_ELEMENT
        ):
            yield

    @pytest.mark.asyncio
    async def test_returns_all_domain_networks(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="domain_networks",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert result["count"] == 2
        assert len(result["domainNetworks"]) == 2
        names = [dn["domainNetworkName"] for dn in result["domainNetworks"]]
        assert "ElectricDistribution" in names
        assert "GasDistribution" in names

    @pytest.mark.asyncio
    async def test_domain_network_fields_parsed(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="domain_networks",
            network_service_url="https://server/UN/FeatureServer",
        )

        electric = next(
            dn
            for dn in result["domainNetworks"]
            if dn["domainNetworkName"] == "ElectricDistribution"
        )
        assert electric["domainNetworkId"] == 4
        assert electric["tierDefinition"] == "esriTDHierarchical"
        assert electric["subnetworkTableName"] == "UN_5_SubnetworkTable"

    @pytest.mark.asyncio
    async def test_tiers_parsed_correctly(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="domain_networks",
            network_service_url="https://server/UN/FeatureServer",
        )

        electric = next(
            dn
            for dn in result["domainNetworks"]
            if dn["domainNetworkName"] == "ElectricDistribution"
        )
        tiers = electric["tiers"]
        assert len(tiers) == 2

        mv_tier = next(t for t in tiers if t["name"] == "Medium Voltage")
        assert mv_tier["tierId"] == 1
        assert mv_tier["rank"] == 1
        assert mv_tier["tierGroupName"] == "Distribution Group"
        assert mv_tier["topologyType"] == "esriTTMesh"
        assert mv_tier["subnetworkFieldName"] == "YOURSUBNETWORKFIELD"

        lv_tier = next(t for t in tiers if t["name"] == "Low Voltage")
        assert lv_tier["tierId"] == 2
        assert lv_tier["rank"] == 2
        assert lv_tier["tierGroupName"] == "Distribution Group"
        assert lv_tier["topologyType"] == "esriTTRadial"
        assert lv_tier["subnetworkFieldName"] == "YOURSUBNETWORKFIELD_LV"

    @pytest.mark.asyncio
    async def test_tier_groups_parsed(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="domain_networks",
            network_service_url="https://server/UN/FeatureServer",
        )

        electric = next(
            dn
            for dn in result["domainNetworks"]
            if dn["domainNetworkName"] == "ElectricDistribution"
        )
        tier_groups = electric["tierGroups"]
        assert len(tier_groups) == 1
        assert tier_groups[0]["name"] == "Distribution Group"
        assert tier_groups[0]["tierNames"] == ["Medium Voltage", "Low Voltage"]

        gas = next(
            dn for dn in result["domainNetworks"] if dn["domainNetworkName"] == "GasDistribution"
        )
        gas_groups = gas["tierGroups"]
        assert len(gas_groups) == 1
        assert gas_groups[0]["name"] == "Pressure Group"
        assert gas_groups[0]["tierNames"] == ["High Pressure"]

    @pytest.mark.asyncio
    async def test_missing_service_url_raises_value_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_get_metadata(section="domain_networks")

    @pytest.mark.asyncio
    async def test_uses_env_var_when_no_url_provided(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"UTILITY_NETWORK_URL": "https://env-server/UN/FeatureServer"},
            ),
            patch.object(
                metadata,
                "_get_data_element",
                return_value=_DOMAIN_NETWORKS_SAMPLE_DATA_ELEMENT,
            ) as mock_get,
        ):
            result = await metadata.network_get_metadata(section="domain_networks")

        mock_get.assert_called_once_with("https://env-server/UN/FeatureServer", None)
        assert result["count"] == 2


# ---------------------------------------------------------------------------
# Fixtures / helpers for network_get_metadata asset_types tests
# ---------------------------------------------------------------------------

_SAMPLE_DATA_ELEMENT = {
    "domainNetworks": [
        {
            "domainNetworkName": "ElectricDistribution",
            "junctionSources": [
                {
                    "sourceId": 1,
                    "name": "ElectricDistributionDevice",
                    "sourceType": "junction",
                    "assetGroups": [
                        {
                            "assetGroupCode": 10,
                            "assetGroupName": "Switch",
                            "assetTypes": [
                                {
                                    "assetTypeCode": 1,
                                    "assetTypeName": "Disconnect Switch",
                                    "terminalConfigurationId": 100,
                                    "categories": ["Protective"],
                                },
                                {
                                    "assetTypeCode": 2,
                                    "assetTypeName": "Load Break Switch",
                                    "terminalConfigurationId": 100,
                                    "categories": ["Protective", "Subnetwork Controller"],
                                },
                            ],
                        },
                        {
                            "assetGroupCode": 20,
                            "assetGroupName": "Transformer",
                            "assetTypes": [
                                {
                                    "assetTypeCode": 1,
                                    "assetTypeName": "Step Down",
                                    "terminalConfigurationId": 200,
                                    "categories": [],
                                },
                            ],
                        },
                    ],
                },
            ],
            "edgeSources": [
                {
                    "sourceId": 2,
                    "name": "ElectricDistributionLine",
                    "sourceType": "edge",
                    "assetGroups": [
                        {
                            "assetGroupCode": 30,
                            "assetGroupName": "Medium Voltage",
                            "assetTypes": [
                                {
                                    "assetTypeCode": 1,
                                    "assetTypeName": "Overhead Single Phase",
                                    "categories": ["Distribution"],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
        {
            "domainNetworkName": "GasDistribution",
            "junctionSources": [
                {
                    "sourceId": 3,
                    "name": "GasDevice",
                    "sourceType": "junction",
                    "assetGroups": [
                        {
                            "assetGroupCode": 40,
                            "assetGroupName": "Valve",
                            "assetTypes": [
                                {
                                    "assetTypeCode": 1,
                                    "assetTypeName": "Gate Valve",
                                    "categories": ["Isolation"],
                                },
                            ],
                        },
                    ],
                },
            ],
            "edgeSources": [],
        },
    ],
    "terminalConfigurations": [
        {"terminalConfigurationId": 100, "terminalConfigurationName": "Single In/Out"},
        {"terminalConfigurationId": 200, "terminalConfigurationName": "High/Low"},
    ],
}


class TestNetworkGetAssetTypes:
    @pytest.fixture()
    def _mock_data_element(self):
        """Patch _get_data_element to return _SAMPLE_DATA_ELEMENT."""
        with patch.object(metadata, "_get_data_element", return_value=_SAMPLE_DATA_ELEMENT):
            yield

    @pytest.mark.asyncio
    async def test_returns_all_sources_unfiltered(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="asset_types",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert result["totalAssetGroups"] == 4
        assert len(result["sources"]) == 3

        source_names = [(s["sourceName"], s["sourceType"]) for s in result["sources"]]
        assert ("ElectricDistributionDevice", "junction") in source_names
        assert ("ElectricDistributionLine", "edge") in source_names
        assert ("GasDevice", "junction") in source_names

    @pytest.mark.asyncio
    async def test_filter_by_domain_network(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="asset_types",
            domain_network="electricdistribution",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert len(result["sources"]) == 2
        for src in result["sources"]:
            assert src["domainNetworkName"] == "ElectricDistribution"

    @pytest.mark.asyncio
    async def test_filter_by_source_name(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="asset_types",
            source_name="ElectricDistributionDevice",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert len(result["sources"]) == 1
        src = result["sources"][0]
        assert src["sourceName"] == "ElectricDistributionDevice"
        assert src["sourceType"] == "junction"
        assert len(src["assetGroups"]) == 2

    @pytest.mark.asyncio
    async def test_terminal_config_resolved_to_name(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="asset_types",
            source_name="ElectricDistributionDevice",
            network_service_url="https://server/UN/FeatureServer",
        )

        switch_group = result["sources"][0]["assetGroups"][0]
        disconnect = switch_group["assetTypes"][0]
        assert disconnect["terminalConfigurationId"] == 100
        assert disconnect["terminalConfigurationName"] == "Single In/Out"

        transformer_group = result["sources"][0]["assetGroups"][1]
        step_down = transformer_group["assetTypes"][0]
        assert step_down["terminalConfigurationId"] == 200
        assert step_down["terminalConfigurationName"] == "High/Low"

    @pytest.mark.asyncio
    async def test_edge_source_without_terminal_config(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="asset_types",
            source_name="ElectricDistributionLine",
            network_service_url="https://server/UN/FeatureServer",
        )

        edge_type = result["sources"][0]["assetGroups"][0]["assetTypes"][0]
        assert "terminalConfigurationId" not in edge_type
        assert "terminalConfigurationName" not in edge_type
        assert edge_type["categories"] == ["Distribution"]

    @pytest.mark.asyncio
    async def test_empty_result_when_filter_matches_nothing(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="asset_types",
            domain_network="WaterDistribution",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert result["sources"] == []
        assert result["totalAssetGroups"] == 0

    @pytest.mark.asyncio
    async def test_missing_service_url_raises_value_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_get_metadata(section="asset_types")


# ---------------------------------------------------------------------------
# Extended sample data element for network_attributes, terminal_configurations,
# categories tests
# ---------------------------------------------------------------------------

_EXTENDED_SAMPLE_DATA_ELEMENT = {
    **_SAMPLE_DATA_ELEMENT,
    "networkAttributes": [
        {
            "networkAttributeId": 1,
            "name": "Shape length",
            "dataType": "esriNADTDouble",
            "domain": None,
            "usageType": "esriUNAUTSystem",
            "isApportionable": False,
        },
        {
            "networkAttributeId": 2,
            "name": "Phases Current",
            "dataType": "esriNADTInteger",
            "domain": {"domainName": "Phases"},
            "usageType": "esriUNAUTJunction",
            "isApportionable": True,
        },
    ],
    "terminalConfigurations": [
        {
            "terminalConfigurationId": 100,
            "terminalConfigurationName": "Single In/Out",
            "terminals": [
                {
                    "terminalId": 1,
                    "terminalName": "Single",
                    "isUpstreamTerminal": True,
                },
            ],
            "traversabilityModel": "bidirectional",
        },
        {
            "terminalConfigurationId": 200,
            "terminalConfigurationName": "High/Low",
            "terminals": [
                {
                    "terminalId": 1,
                    "terminalName": "High",
                    "isUpstreamTerminal": True,
                },
                {
                    "terminalId": 2,
                    "terminalName": "Low",
                    "isUpstreamTerminal": False,
                },
            ],
            "traversabilityModel": "unidirectional",
            "terminalPaths": [
                {
                    "id": 1,
                    "name": "Path 1",
                    "fromTerminalId": 1,
                    "toTerminalId": 2,
                    "isDefaultPath": True,
                },
            ],
        },
    ],
    "categories": [
        {"name": "Protective"},
        {"name": "Subnetwork Controller"},
        {"name": "Distribution"},
        {"name": "Isolation"},
    ],
}


class TestNetworkGetNetworkAttributes:
    @pytest.fixture()
    def _mock_data_element(self):
        """Patch _get_data_element to return _EXTENDED_SAMPLE_DATA_ELEMENT."""
        with patch.object(
            metadata, "_get_data_element", return_value=_EXTENDED_SAMPLE_DATA_ELEMENT
        ):
            yield

    @pytest.mark.asyncio
    async def test_returns_all_attributes(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="network_attributes",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert result["count"] == 2
        assert len(result["networkAttributes"]) == 2

    @pytest.mark.asyncio
    async def test_attribute_fields_parsed_correctly(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="network_attributes",
            network_service_url="https://server/UN/FeatureServer",
        )

        shape_attr = result["networkAttributes"][0]
        assert shape_attr["networkAttributeId"] == 1
        assert shape_attr["name"] == "Shape length"
        assert shape_attr["dataType"] == "esriNADTDouble"
        assert shape_attr["domainName"] is None
        assert shape_attr["usageType"] == "esriUNAUTSystem"
        assert shape_attr["isApportionable"] is False

        phases_attr = result["networkAttributes"][1]
        assert phases_attr["networkAttributeId"] == 2
        assert phases_attr["name"] == "Phases Current"
        assert phases_attr["dataType"] == "esriNADTInteger"
        assert phases_attr["domainName"] == "Phases"
        assert phases_attr["usageType"] == "esriUNAUTJunction"
        assert phases_attr["isApportionable"] is True

    @pytest.mark.asyncio
    async def test_missing_service_url_raises_value_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_get_metadata(section="network_attributes")


class TestNetworkGetTerminalConfigurations:
    @pytest.fixture()
    def _mock_data_element(self):
        """Patch _get_data_element to return _EXTENDED_SAMPLE_DATA_ELEMENT."""
        with patch.object(
            metadata, "_get_data_element", return_value=_EXTENDED_SAMPLE_DATA_ELEMENT
        ):
            yield

    @pytest.mark.asyncio
    async def test_returns_all_configurations(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="terminal_configurations",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert result["count"] == 2
        assert len(result["terminalConfigurations"]) == 2

    @pytest.mark.asyncio
    async def test_terminal_config_fields_parsed_correctly(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="terminal_configurations",
            network_service_url="https://server/UN/FeatureServer",
        )

        single_cfg = result["terminalConfigurations"][0]
        assert single_cfg["terminalConfigurationId"] == 100
        assert single_cfg["terminalConfigurationName"] == "Single In/Out"
        assert single_cfg["traversabilityModel"] == "bidirectional"
        assert len(single_cfg["terminals"]) == 1
        assert single_cfg["terminals"][0]["terminalId"] == 1
        assert single_cfg["terminals"][0]["terminalName"] == "Single"
        assert single_cfg["terminals"][0]["isUpstreamTerminal"] is True

        hl_cfg = result["terminalConfigurations"][1]
        assert hl_cfg["terminalConfigurationId"] == 200
        assert hl_cfg["terminalConfigurationName"] == "High/Low"
        assert hl_cfg["traversabilityModel"] == "unidirectional"
        assert len(hl_cfg["terminals"]) == 2
        assert hl_cfg["terminals"][0]["terminalName"] == "High"
        assert hl_cfg["terminals"][0]["isUpstreamTerminal"] is True
        assert hl_cfg["terminals"][1]["terminalName"] == "Low"
        assert hl_cfg["terminals"][1]["isUpstreamTerminal"] is False

        # terminalPaths present on unidirectional config
        assert "terminalPaths" in hl_cfg
        assert len(hl_cfg["terminalPaths"]) == 1
        path = hl_cfg["terminalPaths"][0]
        assert path["id"] == 1
        assert path["name"] == "Path 1"
        assert path["fromTerminalId"] == 1
        assert path["toTerminalId"] == 2
        assert path["isDefaultPath"] is True

        # terminalPaths absent on bidirectional config (key not included)
        assert "terminalPaths" not in single_cfg

    @pytest.mark.asyncio
    async def test_missing_service_url_raises_value_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_get_metadata(section="terminal_configurations")


class TestNetworkGetCategories:
    @pytest.fixture()
    def _mock_data_element(self):
        """Patch _get_data_element to return _EXTENDED_SAMPLE_DATA_ELEMENT."""
        with patch.object(
            metadata, "_get_data_element", return_value=_EXTENDED_SAMPLE_DATA_ELEMENT
        ):
            yield

    @pytest.mark.asyncio
    async def test_returns_all_categories(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="categories",
            network_service_url="https://server/UN/FeatureServer",
        )

        assert result["count"] == 4
        cat_names = [c["name"] for c in result["categories"]]
        assert "Protective" in cat_names
        assert "Subnetwork Controller" in cat_names
        assert "Distribution" in cat_names
        assert "Isolation" in cat_names

    @pytest.mark.asyncio
    async def test_protective_category_members(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="categories",
            network_service_url="https://server/UN/FeatureServer",
        )

        protective = next(c for c in result["categories"] if c["name"] == "Protective")
        members = protective["memberAssetTypes"]
        assert len(members) == 2

        member_names = [m["assetTypeName"] for m in members]
        assert "Disconnect Switch" in member_names
        assert "Load Break Switch" in member_names

        disconnect = next(m for m in members if m["assetTypeName"] == "Disconnect Switch")
        assert disconnect["domainNetworkName"] == "ElectricDistribution"
        assert disconnect["sourceName"] == "ElectricDistributionDevice"
        assert disconnect["assetGroupName"] == "Switch"
        assert disconnect["assetTypeCode"] == 1

    @pytest.mark.asyncio
    async def test_isolation_category_has_gas_member(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="categories",
            network_service_url="https://server/UN/FeatureServer",
        )

        isolation = next(c for c in result["categories"] if c["name"] == "Isolation")
        members = isolation["memberAssetTypes"]
        assert len(members) == 1
        assert members[0]["assetTypeName"] == "Gate Valve"
        assert members[0]["domainNetworkName"] == "GasDistribution"

    @pytest.mark.asyncio
    async def test_empty_category_has_no_members(self, _mock_data_element) -> None:
        """Distribution category has one member in our sample data."""
        result = await metadata.network_get_metadata(
            section="categories",
            network_service_url="https://server/UN/FeatureServer",
        )

        distribution = next(c for c in result["categories"] if c["name"] == "Distribution")
        assert len(distribution["memberAssetTypes"]) == 1
        assert distribution["memberAssetTypes"][0]["assetTypeName"] == "Overhead Single Phase"

    @pytest.mark.asyncio
    async def test_missing_service_url_raises_value_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_get_metadata(section="categories")


class TestNetworkRefreshMetadata:
    @pytest.mark.asyncio
    async def test_refresh_invalidates_and_refetches(self) -> None:
        first_de = {"domainNetworks": ["a"], "networkAttributes": []}
        second_de = {"domainNetworks": ["b"], "networkAttributes": []}
        with (
            patch.object(metadata, "_connect_gis", return_value=MagicMock()),
            patch.object(metadata, "FeatureLayerCollection", return_value=MagicMock()),
            patch.object(metadata, "_un_data_element", side_effect=[first_de, second_de]) as fetch,
        ):
            # Initial fetch to populate cache
            metadata._get_data_element("https://server/UN/FeatureServer")
            assert fetch.call_count == 1

            # Refresh should invalidate and re-fetch
            result = await metadata.network_refresh_metadata(
                network_service_url="https://server/UN/FeatureServer"
            )

            assert fetch.call_count == 2
            assert result["message"] == "Metadata cache invalidated and refreshed successfully."
            assert result["serviceUrl"] == "https://server/UN/FeatureServer"

    @pytest.mark.asyncio
    async def test_refresh_missing_service_url_raises_value_error(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_refresh_metadata()


# ---------------------------------------------------------------------------
# New tests: section dispatch, topology_rules, propagators
# ---------------------------------------------------------------------------


class TestNetworkGetMetadataDispatch:
    """Tests for the section dispatch and error handling."""

    @pytest.mark.asyncio
    async def test_invalid_section_returns_error(self) -> None:
        """Invalid section returns error dict listing valid sections."""
        result = await metadata.network_get_metadata(
            section="bogus",
            network_service_url="https://server/UN/FeatureServer",
        )
        assert "error" in result
        assert "bogus" in result["error"]
        assert "domain_networks" in result["error"]
        assert "topology_rules" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_service_url_raises_for_valid_section(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Provide network_service_url"),
        ):
            await metadata.network_get_metadata(section="domain_networks")

    @pytest.mark.asyncio
    async def test_invalid_section_does_not_require_service_url(self) -> None:
        """Invalid section check happens before URL validation."""
        result = await metadata.network_get_metadata(section="invalid_thing")
        assert "error" in result


class TestParseTopologyRules:
    """Tests for the topology_rules section parser."""

    @pytest.fixture()
    def _mock_data_element(self):
        data_element = {
            "domainNetworks": [
                {
                    "domainNetworkName": "ElectricDistribution",
                    "junctionSources": [
                        {
                            "name": "ElectricDevice",
                            "connectivityRules": [
                                {
                                    "type": "junctionJunction",
                                    "fromAssetGroupCode": 4,
                                    "fromAssetTypeCode": 12,
                                    "fromTerminalId": 2,
                                    "toAssetGroupCode": 5,
                                    "toAssetTypeCode": 1,
                                    "toTerminalId": 1,
                                }
                            ],
                        }
                    ],
                    "edgeSources": [],
                }
            ],
        }
        with patch.object(metadata, "_get_data_element", return_value=data_element):
            yield

    @pytest.mark.asyncio
    async def test_returns_connectivity_rules(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="topology_rules",
            network_service_url="https://server/UN/FeatureServer",
        )
        assert result["count"] == 1
        rule = result["topologyRules"][0]
        assert rule["domainNetworkName"] == "ElectricDistribution"
        assert rule["sourceName"] == "ElectricDevice"
        assert rule["ruleType"] == "junctionJunction"
        assert rule["fromAssetGroupCode"] == 4
        assert rule["toAssetGroupCode"] == 5

    @pytest.mark.asyncio
    async def test_empty_when_no_rules(self) -> None:
        data_element = {
            "domainNetworks": [
                {
                    "domainNetworkName": "X",
                    "junctionSources": [{"name": "S", "connectivityRules": []}],
                    "edgeSources": [],
                }
            ],
        }
        with patch.object(metadata, "_get_data_element", return_value=data_element):
            result = await metadata.network_get_metadata(
                section="topology_rules",
                network_service_url="https://server/UN/FeatureServer",
            )
        assert result["count"] == 0
        assert result["topologyRules"] == []


class TestParsePropagators:
    """Tests for the propagators section parser."""

    @pytest.fixture()
    def _mock_data_element(self):
        data_element = {
            "domainNetworks": [
                {
                    "domainNetworkName": "ElectricDistribution",
                    "tiers": [
                        {
                            "name": "Medium Voltage",
                            "propagators": [
                                {
                                    "networkAttributeName": "Phases Current",
                                    "propagatorFunctionType": "esriPFTBitwiseOr",
                                    "operator": "esriNAOBitwiseOr",
                                    "value": 0,
                                    "substitutionAttributeName": "Phases Normal",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        with patch.object(metadata, "_get_data_element", return_value=data_element):
            yield

    @pytest.mark.asyncio
    async def test_returns_propagators(self, _mock_data_element) -> None:
        result = await metadata.network_get_metadata(
            section="propagators",
            network_service_url="https://server/UN/FeatureServer",
        )
        assert result["count"] == 1
        prop = result["propagators"][0]
        assert prop["domainNetworkName"] == "ElectricDistribution"
        assert prop["tierName"] == "Medium Voltage"
        assert prop["networkAttributeName"] == "Phases Current"
        assert prop["propagatorFunctionType"] == "esriPFTBitwiseOr"

    @pytest.mark.asyncio
    async def test_empty_when_no_propagators(self) -> None:
        data_element = {
            "domainNetworks": [
                {
                    "domainNetworkName": "X",
                    "tiers": [{"name": "T", "propagators": []}],
                }
            ],
        }
        with patch.object(metadata, "_get_data_element", return_value=data_element):
            result = await metadata.network_get_metadata(
                section="propagators",
                network_service_url="https://server/UN/FeatureServer",
            )
        assert result["count"] == 0
        assert result["propagators"] == []
