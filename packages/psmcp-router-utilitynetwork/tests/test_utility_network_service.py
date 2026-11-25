"""Tests for the utility network router service."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
from psmcp_router_utilitynetwork import utility_network_service as svc


class TestUtilityNetworkUrl:
    def test_from_feature_server(self) -> None:
        url = "https://server/arcgis/rest/services/UN/FeatureServer"
        assert svc._utility_network_url(url).endswith("/UtilityNetworkServer")


class TestStartingPoint:
    def test_format(self) -> None:
        loc = svc._starting_point("{abc}")
        assert loc[0]["traceLocationType"] == "startingPoint"
        assert loc[0]["globalId"] == "{abc}"


class TestNamedTraceGlobalId:
    def test_resolves_name(self) -> None:
        manager = MagicMock()
        manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [{"globalId": "{guid}", "name": "My Trace"}],
        }
        assert svc._named_trace_global_id(manager, "My Trace") == "{guid}"

    def test_not_found(self) -> None:
        manager = MagicMock()
        manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [],
        }
        with pytest.raises(ValueError, match="not found"):
            svc._named_trace_global_id(manager, "Missing")

    def test_resolves_paraphrase_missing_trace_word(self) -> None:
        manager = MagicMock()
        manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [{"globalId": "{guid}", "name": "Subnetwork Trace"}],
        }
        # Agent drops the trailing "Trace" word — still resolves to the saved config.
        assert svc._named_trace_global_id(manager, "Subnetwork") == "{guid}"

    def test_resolves_paraphrase_case_insensitive(self) -> None:
        manager = MagicMock()
        manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {"globalId": "{guid}", "title": "Distribution Isolation Trace"}
            ],
        }
        assert svc._named_trace_global_id(manager, "distribution isolation") == "{guid}"

    def test_ambiguous_paraphrase_raises(self) -> None:
        manager = MagicMock()
        manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {"globalId": "{a}", "name": "Downstream Service Point Trace"},
                {"globalId": "{b}", "name": "Downstream - XFR Load and Customer Count"},
            ],
        }
        # "Downstream" fits two configs — refuse to guess, list the real names.
        with pytest.raises(ValueError, match="not found"):
            svc._named_trace_global_id(manager, "Downstream")


class TestGetCustomerData:
    def test_queries_cis_view_with_meter_ids(self) -> None:
        gis = MagicMock()
        cust_layer = MagicMock()
        cust_layer.properties.fields = [
            {"name": "meter_id"},
            {"name": "full_name"},
            {"name": "account_status"},
        ]
        cust_layer.query.return_value = MagicMock(
            features=[
                MagicMock(
                    attributes={"meter_id": "M1", "full_name": "Jane", "account_status": "active"}
                )
            ]
        )

        with patch.object(svc, "_find_layer", return_value=cust_layer):
            result = svc.get_customer_data(
                gis, "https://server/UN/FeatureServer", [], meter_ids=["M1"]
            )

        assert result["customers"] == [{"meter_id": "M1", "account_status": "active"}]

    def test_resolves_meter_ids_from_global_ids(self) -> None:
        gis = MagicMock()
        device_layer = MagicMock()
        device_layer.query.return_value = MagicMock(
            features=[MagicMock(attributes={"globalid": "{a}", "meter_id": "M1"})]
        )
        cust_layer = MagicMock()
        cust_layer.properties.fields = [{"name": "meter_id"}]
        cust_layer.query.return_value = MagicMock(
            features=[MagicMock(attributes={"meter_id": "M1"})]
        )

        with patch.object(svc, "_find_layer", side_effect=[device_layer, cust_layer]):
            result = svc.get_customer_data(gis, "https://server/UN/FeatureServer", ["{a}"])

        assert result["globalIdMeterMap"] == [{"globalId": "{a}", "meterId": "M1"}]
        assert result["customers"] == [{"meter_id": "M1"}]


class TestRunNamedTrace:
    def test_calls_trace_with_named_config(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [{"globalId": "{cfg-id}", "name": "Isolation Trace"}],
        }
        un_manager.trace.return_value = {"success": True, "traceResults": {"elements": []}}

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=None),
            patch.object(svc, "_terminal_selection_prompt", return_value=None),
        ):
            result = svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Isolation Trace",
                "{device-id}",
            )

        assert result["success"] is True
        un_manager.trace.assert_called_once()

    def test_not_found_lists_available(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {"globalId": "{a}", "name": "Downstream Service Point Trace"},
                {"globalId": "{b}", "name": "Subnetwork Trace"},
            ],
        }

        with patch.object(svc, "UtilityNetworkManager", return_value=un_manager):
            with pytest.raises(ValueError, match="Downstream Service Point Trace"):
                svc.run_named_trace(
                    gis,
                    "https://server/UN/FeatureServer",
                    "Balanced Distribution - Transformer Load and Count",
                    "{device-id}",
                )

    def test_derives_trace_type_from_config(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {
                    "globalId": "{cfg-id}",
                    "name": "Downstream Service Point Trace",
                    "traceType": "downstream",
                }
            ],
        }
        un_manager.trace.return_value = {"success": True, "traceResults": {}}

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=None),
            patch.object(svc, "_terminal_selection_prompt", return_value=None),
        ):
            svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Downstream Service Point Trace",
                "{device-id}",
            )

        assert un_manager.trace.call_args.kwargs["trace_type"] == "downstream"

    def test_explicit_trace_type_overrides_config(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {"globalId": "{cfg-id}", "name": "Some Trace", "traceType": "downstream"}
            ],
        }
        un_manager.trace.return_value = {"success": True, "traceResults": {}}

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=None),
            patch.object(svc, "_terminal_selection_prompt", return_value=None),
        ):
            svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Some Trace",
                "{device-id}",
                trace_type="upstream",
            )

        assert un_manager.trace.call_args.kwargs["trace_type"] == "upstream"

    def test_prompts_for_terminal_when_multi_terminal_and_none_supplied(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {
                    "globalId": "{cfg-id}",
                    "name": "Downstream - XFR Load and Customer Count",
                    "traceType": "downstream",
                },
            ],
        }
        terminals_info = {
            "assetGroupName": "Medium Voltage Transformer",
            "assetTypeName": "Overhead Single Phase - MV->LV",
            "usageType": "esriUNFCUTDevice",
            "terminals": [
                {"terminalId": 7, "terminalName": "2wXFR:Primary", "recommendedFor": "upstream"},
                {
                    "terminalId": 8,
                    "terminalName": "2wXFR:Secondary",
                    "recommendedFor": "downstream",
                },
            ],
        }

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=None),
            patch.object(svc, "get_device_terminals", return_value=terminals_info),
        ):
            result = svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Downstream - XFR Load and Customer Count",
                "{device-id}",
            )

        assert result["status"] == svc.NEEDS_TERMINAL_SELECTION
        assert result["needs"] == "terminal_id"
        assert result["recommendedTerminalId"] == 8  # downstream trace -> downstream terminal
        assert [o["terminalId"] for o in result["terminalOptions"]] == [7, 8]
        un_manager.trace.assert_not_called()

    def test_single_terminal_device_runs_without_prompt(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {"globalId": "{cfg-id}", "name": "Some Trace", "traceType": "downstream"}
            ],
        }
        un_manager.trace.return_value = {"success": True, "traceResults": {}}
        single = {"terminals": [{"terminalId": 1, "terminalName": "T", "recommendedFor": None}]}

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=None),
            patch.object(svc, "get_device_terminals", return_value=single),
        ):
            result = svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Some Trace",
                "{device-id}",
            )

        assert result["success"] is True
        un_manager.trace.assert_called_once()

    def test_explicit_terminal_skips_prompt(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {"globalId": "{cfg-id}", "name": "Some Trace", "traceType": "downstream"}
            ],
        }
        un_manager.trace.return_value = {"success": True, "traceResults": {}}

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=None),
            patch.object(svc, "get_device_terminals") as terminals,
        ):
            result = svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Some Trace",
                "{device-id}",
                terminal_id=8,
            )

        assert result["success"] is True
        terminals.assert_not_called()
        un_manager.trace.assert_called_once()

    def test_rejects_start_feature_in_wrong_tier(self) -> None:
        gis = MagicMock()
        un_manager = MagicMock()
        un_manager.trace_configurations.return_value.query.return_value = {
            "traceConfigurations": [
                {
                    "globalId": "{cfg-id}",
                    "name": "Downstream Service Point Trace",
                    "traceType": "downstream",
                }
            ],
        }
        invalid = {
            "status": svc.INVALID_START_POINT,
            "reason": "tier_mismatch",
            "requiredTier": "Electric Distribution",
        }

        with (
            patch.object(svc, "UtilityNetworkManager", return_value=un_manager),
            patch.object(svc, "_validate_start_in_tier", return_value=invalid),
        ):
            result = svc.run_named_trace(
                gis,
                "https://server/UN/FeatureServer",
                "Downstream Service Point Trace",
                "{hv-device-id}",
            )

        assert result["status"] == svc.INVALID_START_POINT
        assert result["requiredTier"] == "Electric Distribution"
        un_manager.trace.assert_not_called()


@pytest.mark.asyncio
async def test_network_named_trace_tool() -> None:
    with (
        patch.dict(svc.os.environ, {"UTILITY_NETWORK_URL": "https://server/UN/FeatureServer"}),
        patch.object(svc, "_connect_gis", return_value=MagicMock()),
        patch.object(svc, "run_named_trace", return_value={"success": True, "traceResults": {}}),
    ):
        result = await svc.network_named_trace(
            named_trace_name="Isolation Trace",
            starting_global_id="{device-id}",
        )

    assert result["namedTraceName"] == "Isolation Trace"


@pytest.mark.asyncio
async def test_network_named_trace_tool_passes_terminal_prompt_through() -> None:
    prompt = {
        "status": svc.NEEDS_TERMINAL_SELECTION,
        "needs": "terminal_id",
        "terminalOptions": [{"terminalId": 7}, {"terminalId": 8}],
        "recommendedTerminalId": 8,
    }
    with (
        patch.dict(svc.os.environ, {"UTILITY_NETWORK_URL": "https://server/UN/FeatureServer"}),
        patch.object(svc, "_connect_gis", return_value=MagicMock()),
        patch.object(svc, "run_named_trace", return_value=prompt),
    ):
        result = await svc.network_named_trace(
            named_trace_name="Downstream - XFR Load and Customer Count",
            starting_global_id="{device-id}",
        )

    assert result["status"] == svc.NEEDS_TERMINAL_SELECTION
    assert result["recommendedTerminalId"] == 8
    assert "traceResults" not in result


@pytest.mark.asyncio
async def test_network_named_trace_tool_passes_invalid_start_point_through() -> None:
    invalid = {
        "status": svc.INVALID_START_POINT,
        "reason": "tier_mismatch",
        "requiredTier": "Electric Distribution",
        "featureTiers": ["Electric Transmission"],
    }
    with (
        patch.dict(svc.os.environ, {"UTILITY_NETWORK_URL": "https://server/UN/FeatureServer"}),
        patch.object(svc, "_connect_gis", return_value=MagicMock()),
        patch.object(svc, "run_named_trace", return_value=invalid),
    ):
        result = await svc.network_named_trace(
            named_trace_name="Downstream Service Point Trace",
            starting_global_id="{hv-device-id}",
        )

    assert result["status"] == svc.INVALID_START_POINT
    assert result["requiredTier"] == "Electric Distribution"
    assert "traceResults" not in result


class TestValidateStartInTier:
    _CONFIG = {
        "title": "Downstream Service Point Trace",
        "traceConfiguration": {
            "domainNetworkName": "Electric",
            "sourceTierName": "Electric Distribution",
        },
    }
    _DATA_ELEMENT = {
        "domainNetworks": [
            {
                "domainNetworkName": "Electric",
                "subnetworkLayerId": 6,
                "tiers": [
                    {"rank": 2, "name": "Electric Transmission"},
                    {"rank": 5, "name": "Electric Distribution"},
                ],
                "junctionSources": [
                    {"layerId": 3, "utilityNetworkFeatureClassUsageType": "esriUNFCUTDevice"},
                ],
                "edgeSources": [],
            }
        ]
    }

    def _flc(self, subnetworkname: str, subnet_rank: int) -> MagicMock:
        # Source layer (id 3) holding the start feature.
        device_layer = MagicMock()
        device_layer.properties.id = 3
        device_layer.query.return_value = MagicMock(
            features=[MagicMock(attributes={"assetid": "XFR-1", "subnetworkname": subnetworkname})]
        )
        # Subnetwork line layer (id 6 == subnetworkLayerId) mapping subnet -> tier rank.
        subnet_layer = MagicMock()
        subnet_layer.properties.id = 6
        subnet_layer.query.return_value = MagicMock(
            features=[
                MagicMock(attributes={"SUBNETWORKNAME": subnetworkname, "TIERNAME": subnet_rank})
            ]
        )
        flc = MagicMock()
        flc.layers = [device_layer, subnet_layer]
        return flc

    def test_rejects_transmission_start_for_distribution_trace(self) -> None:
        flc = self._flc("138 kV - 6", subnet_rank=2)  # Electric Transmission
        with (
            patch.object(svc, "FeatureLayerCollection", return_value=flc),
            patch.object(svc, "_un_data_element", return_value=self._DATA_ELEMENT),
        ):
            result = svc._validate_start_in_tier(
                MagicMock(), "https://server/UN/FeatureServer", "{hv}", self._CONFIG
            )

        assert result is not None
        assert result["status"] == svc.INVALID_START_POINT
        assert result["requiredTier"] == "Electric Distribution"
        assert result["featureTiers"] == ["Electric Transmission"]

    def test_allows_distribution_start_for_distribution_trace(self) -> None:
        flc = self._flc("RMT003", subnet_rank=5)  # Electric Distribution
        with (
            patch.object(svc, "FeatureLayerCollection", return_value=flc),
            patch.object(svc, "_un_data_element", return_value=self._DATA_ELEMENT),
        ):
            result = svc._validate_start_in_tier(
                MagicMock(), "https://server/UN/FeatureServer", "{mv}", self._CONFIG
            )

        assert result is None

    def test_skips_when_trace_has_no_tier(self) -> None:
        result = svc._validate_start_in_tier(
            MagicMock(),
            "https://server/UN/FeatureServer",
            "{x}",
            {"title": "T", "traceConfiguration": {}},
        )
        assert result is None


@pytest.mark.asyncio
async def test_query_customer_data_tool() -> None:
    with (
        patch.object(svc, "_connect_gis", return_value=MagicMock()),
        patch.object(svc, "get_customer_data", return_value={"meterIds": ["M1"], "customers": []}),
    ):
        result = await svc.query_customer_data(
            global_ids=["{a}"],
            meter_ids=["M1"],
            network_service_url="https://server/UN/FeatureServer",
        )

    assert result["meterIds"] == ["M1"]


def _un_data_element() -> dict:
    return {
        "domainNetworks": [
            {
                "domainNetworkName": "ElectricDistribution",
                "junctionSources": [
                    {
                        "layerId": 6,
                        "utilityNetworkFeatureClassUsageType": "esriUNFCUTDevice",
                        "assetGroups": [
                            {
                                "assetGroupCode": 1,
                                "assetGroupName": "Transformer",
                                "assetTypes": [
                                    {
                                        "assetTypeCode": 2,
                                        "assetTypeName": "Overhead Single Phase",
                                        "terminalConfigurationId": 5,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "edgeSources": [],
            }
        ],
        "terminalConfigurations": [
            {
                "terminalConfigurationId": 5,
                "terminalConfigurationName": "High/Low",
                "terminals": [
                    {"terminalId": 1, "terminalName": "High", "isUpstreamTerminal": True},
                    {"terminalId": 2, "terminalName": "Low", "isUpstreamTerminal": False},
                ],
            }
        ],
    }


class TestGetDeviceTerminals:
    def _flc(self, feature_attrs: dict | None) -> MagicMock:
        flc = MagicMock()
        flc.properties.get.return_value = {"utilityNetworkLayerId": 50}
        flc.query_data_elements.return_value = {
            "layerDataElements": [{"dataElement": _un_data_element()}]
        }
        layer = MagicMock()
        layer.properties.id = 6
        features = [MagicMock(attributes=feature_attrs)] if feature_attrs else []
        layer.query.return_value = MagicMock(features=features)
        flc.layers = [layer]
        return flc

    def test_resolves_terminals(self) -> None:
        flc = self._flc({"globalid": "{a}", "assetgroup": 1, "assettype": 2})
        with patch.object(svc, "FeatureLayerCollection", return_value=flc):
            result = svc.get_device_terminals(MagicMock(), "https://server/UN/FeatureServer", "{a}")

        assert result["terminalCount"] == 2
        assert result["terminalConfigurationId"] == 5
        assert result["assetTypeName"] == "Overhead Single Phase"
        assert [t["terminalId"] for t in result["terminals"]] == [1, 2]
        assert result["usageType"] == "esriUNFCUTDevice"
        recommended = {t["terminalId"]: t["recommendedFor"] for t in result["terminals"]}
        assert recommended == {1: "upstream", 2: "downstream"}
        assert "terminalNote" not in result

    @pytest.mark.parametrize("is_upstream", [False, True, None])
    def test_single_terminal_is_recommended_for_any_direction(self, is_upstream) -> None:
        flc = self._flc({"globalid": "{a}", "assetgroup": 1, "assettype": 2})
        de = flc.query_data_elements.return_value["layerDataElements"][0]["dataElement"]
        de["terminalConfigurations"][0]["terminals"] = [
            {"terminalId": 1, "terminalName": "Single Terminal", "isUpstreamTerminal": is_upstream}
        ]
        with patch.object(svc, "FeatureLayerCollection", return_value=flc):
            result = svc.get_device_terminals(MagicMock(), "https://server/UN/FeatureServer", "{a}")
        assert result["terminalCount"] == 1
        assert result["terminals"][0]["recommendedFor"] == svc.TERMINAL_ANY_DIRECTION
        # The raw flag is still reported for transparency.
        assert result["terminals"][0]["isUpstreamTerminal"] is is_upstream
        assert result["terminalNote"] == svc.SINGLE_TERMINAL_NOTE

    def test_feature_not_found(self) -> None:
        flc = self._flc(None)
        with patch.object(svc, "FeatureLayerCollection", return_value=flc):
            with pytest.raises(ValueError, match="No network feature found"):
                svc.get_device_terminals(
                    MagicMock(), "https://server/UN/FeatureServer", "{missing}"
                )

    def test_not_a_utility_network(self) -> None:
        flc = MagicMock()
        flc.properties.get.return_value = {}
        with patch.object(svc, "FeatureLayerCollection", return_value=flc):
            with pytest.raises(ValueError, match="not a utility network"):
                svc.get_device_terminals(MagicMock(), "https://server/UN/FeatureServer", "{a}")


@pytest.mark.asyncio
async def test_network_device_terminals_tool() -> None:
    with (
        patch.object(svc, "_connect_gis", return_value=MagicMock()),
        patch.object(
            svc,
            "get_device_terminals",
            return_value={"globalId": "{a}", "terminals": [], "terminalCount": 0},
        ),
    ):
        result = await svc.network_device_terminals(
            global_id="{a}",
            network_service_url="https://server/UN/FeatureServer",
        )

    assert result["globalId"] == "{a}"


# ---------------------------------------------------------------------------
# Tier resolution + subnetwork-definition trace configuration
# ---------------------------------------------------------------------------


def _tier_data_element(tier_definition: str = "esriTDPartitioned") -> dict:
    """A data element with one Electric domain, two tiers, and a subnetwork
    trace definition on the Distribution tier.

    Mirrors the live structure confirmed against the mcp_une service: the
    partitioned/hierarchical designation lives on the domain network's
    ``tierDefinition``, and the condition barriers live on the tier's
    ``updateSubnetworkTraceConfiguration``.
    """
    return {
        "domainNetworks": [
            {
                "domainNetworkName": "Electric",
                "tierDefinition": tier_definition,
                "subnetworkLayerId": 6,
                "junctionSources": [
                    {"layerId": 3, "utilityNetworkFeatureClassUsageType": "esriUNFCUTDevice"},
                ],
                "edgeSources": [],
                "tiers": [
                    {
                        "tierID": 2,
                        "name": "Electric Transmission",
                        "rank": 2,
                        "tierTopology": "esriTTTRadial",
                        "validDevices": [
                            {
                                "assetGroupCode": 10,
                                "assetTypes": [{"assetTypeCode": 100}],
                            },
                        ],
                    },
                    {
                        "tierID": 5,
                        "name": "Electric Distribution",
                        "rank": 5,
                        "tierTopology": "esriTTTMesh",
                        "validDevices": [
                            {
                                "assetGroupCode": 1,
                                "assetTypes": [
                                    {"assetTypeCode": 2},
                                    {"assetTypeCode": 3},
                                ],
                            },
                        ],
                        "updateSubnetworkTraceConfiguration": {
                            "includeContainers": True,
                            "includeContent": True,
                            "includeStructures": True,
                            "includeBarriers": True,
                            "conditionBarriers": [
                                {
                                    "name": "E:Operating Status Normal",
                                    "type": "networkAttribute",
                                    "operator": "equal",
                                    "value": 1,
                                },
                            ],
                        },
                    },
                ],
            }
        ]
    }


def _tier_flc(
    subnetworkname: str,
    subnet_rank: int,
    assetgroup: int = 1,
    assettype: int = 2,
) -> MagicMock:
    """Build a FeatureLayerCollection mock: a device layer (id 3) holding the
    start feature and a subnetwork layer (id 6) mapping subnetwork -> tier rank.

    assetgroup/assettype default to the Distribution-valid 1/2 so configured-tier
    lookups also resolve for these features.
    """
    device_layer = MagicMock()
    device_layer.properties.id = 3
    device_layer.query.return_value = MagicMock(
        features=[
            MagicMock(
                attributes={
                    "assetid": "XFR-1",
                    "subnetworkname": subnetworkname,
                    "assetgroup": assetgroup,
                    "assettype": assettype,
                }
            )
        ]
    )
    subnet_layer = MagicMock()
    subnet_layer.properties.id = 6
    rows = (
        [MagicMock(attributes={"SUBNETWORKNAME": subnetworkname, "TIERNAME": subnet_rank})]
        # An empty subnetworkname means the subnetwork layer query returns nothing.
        if subnetworkname
        else []
    )
    subnet_layer.query.return_value = MagicMock(features=rows)
    flc = MagicMock()
    flc.layers = [device_layer, subnet_layer]
    return flc


def _tier_flc_multi(subnetworkname: str, rows: list[tuple[str, int]]) -> MagicMock:
    """Like _tier_flc but the subnetwork layer returns several rows (used for the
    barrier-object case where a feature is a member of multiple subnetworks that
    belong to different tiers).

    Args:
        subnetworkname: The comma-separated SUBNETWORKNAME on the start feature.
        rows: (subnetwork name, tier rank) pairs the subnetwork layer returns.
    """
    device_layer = MagicMock()
    device_layer.properties.id = 3
    device_layer.query.return_value = MagicMock(
        features=[
            MagicMock(
                attributes={
                    "assetid": "BARRIER-1",
                    "subnetworkname": subnetworkname,
                    "assetgroup": 1,
                    "assettype": 2,
                }
            )
        ]
    )
    subnet_layer = MagicMock()
    subnet_layer.properties.id = 6
    subnet_layer.query.return_value = MagicMock(
        features=[
            MagicMock(attributes={"SUBNETWORKNAME": name, "TIERNAME": rank}) for name, rank in rows
        ]
    )
    flc = MagicMock()
    flc.layers = [device_layer, subnet_layer]
    return flc


class TestParseTierDefinition:
    def test_returns_domain_and_tier(self) -> None:
        de = _tier_data_element()
        found = svc._parse_tier_definition(de, "Electric", "Electric Distribution")
        assert found is not None
        domain, tier = found
        assert domain["domainNetworkName"] == "Electric"
        assert tier["name"] == "Electric Distribution"

    def test_case_insensitive(self) -> None:
        de = _tier_data_element()
        found = svc._parse_tier_definition(de, "electric", "electric distribution")
        assert found is not None

    def test_missing_tier_returns_none(self) -> None:
        de = _tier_data_element()
        assert svc._parse_tier_definition(de, "Electric", "No Such Tier") is None


class TestIsHierarchical:
    def test_partitioned_is_not_hierarchical(self) -> None:
        de = _tier_data_element("esriTDPartitioned")
        domain = de["domainNetworks"][0]
        assert svc._is_hierarchical(domain) is False

    def test_hierarchical(self) -> None:
        de = _tier_data_element("esriTDHierarchical")
        domain = de["domainNetworks"][0]
        assert svc._is_hierarchical(domain) is True


class TestTierTraceConfiguration:
    def test_lifts_subnetwork_definition(self) -> None:
        de = _tier_data_element()
        _, tier = svc._parse_tier_definition(de, "Electric", "Electric Distribution")
        config = svc._parse_tier_trace_configuration(tier)
        assert config["includeContainers"] is True
        assert config["includeBarriers"] is True
        assert len(config["conditionBarriers"]) == 1

    def test_returns_copy_not_reference(self) -> None:
        de = _tier_data_element()
        _, tier = svc._parse_tier_definition(de, "Electric", "Electric Distribution")
        config = svc._parse_tier_trace_configuration(tier)
        config["conditionBarriers"].append({"name": "injected"})
        # Mutating the returned config must not affect the source tier.
        assert len(tier["updateSubnetworkTraceConfiguration"]["conditionBarriers"]) == 1

    def test_missing_definition_returns_empty(self) -> None:
        assert svc._parse_tier_trace_configuration({"name": "No Config Tier"}) == {}


class TestResolveFeatureTier:
    def _run(self, de: dict, flc: MagicMock, **kwargs) -> dict:
        with patch.object(svc, "FeatureLayerCollection", return_value=flc):
            return svc._resolve_feature_tier(
                MagicMock(), "https://server/UN/FeatureServer", "{dev}", de, **kwargs
            )

    def test_partitioned_single_member_auto_resolves(self) -> None:
        # Feature is an actual member of one Distribution subnetwork (rank 5),
        # so it resolves to a single tier via membership.
        de = _tier_data_element("esriTDPartitioned")
        flc = _tier_flc("RMT001", subnet_rank=5)
        result = self._run(de, flc)
        assert result["status"] == svc.TIER_RESOLVED
        assert result["tierName"] == "Electric Distribution"
        assert result["subnetworkNames"] == ["RMT001"]
        assert result["resolvedBy"] == "membership"

    def test_barrier_object_member_of_two_tiers_is_ambiguous(self) -> None:
        # A barrier object between subnetworks is an actual member of two
        # subnetworks in different tiers — ambiguous even in a partitioned domain.
        de = _tier_data_element("esriTDPartitioned")
        flc = _tier_flc_multi(
            subnetworkname="RMT001, 138 kV - 6",
            rows=[("RMT001", 5), ("138 kV - 6", 2)],
        )
        result = self._run(de, flc)
        assert result["status"] == svc.TIER_AMBIGUOUS
        assert sorted(result["memberTiers"]) == ["Electric Distribution", "Electric Transmission"]

    def test_barrier_object_disambiguated_by_tier_name(self) -> None:
        de = _tier_data_element("esriTDPartitioned")
        flc = _tier_flc_multi(
            subnetworkname="RMT001, 138 kV - 6",
            rows=[("RMT001", 5), ("138 kV - 6", 2)],
        )
        result = self._run(de, flc, tier_name="Electric Distribution")
        assert result["status"] == svc.TIER_RESOLVED
        assert result["tierName"] == "Electric Distribution"
        assert result["resolvedBy"] == "membership"

    def test_matching_tier_name_resolves(self) -> None:
        de = _tier_data_element()
        flc = _tier_flc("RMT001", subnet_rank=5)
        result = self._run(
            de, flc, domain_network_name="Electric", tier_name="Electric Distribution"
        )
        assert result["status"] == svc.TIER_RESOLVED
        assert result["tierName"] == "Electric Distribution"
        assert result["resolvedBy"] == "membership"

    def test_wrong_tier_name_is_rejected(self) -> None:
        de = _tier_data_element()
        flc = _tier_flc("RMT001", subnet_rank=5)
        result = self._run(de, flc, tier_name="Electric Transmission")
        assert result["status"] == svc.TIER_AMBIGUOUS
        assert result["memberTiers"] == ["Electric Distribution"]

    def test_feature_not_located_is_no_membership(self) -> None:
        de = _tier_data_element()
        flc = MagicMock()
        flc.layers = []  # no layers -> feature cannot be located
        result = self._run(de, flc)
        assert result["status"] == svc.TIER_NO_MEMBERSHIP

    def test_no_membership_falls_back_to_single_configured_tier(self) -> None:
        # Subnetwork not built (empty SUBNETWORKNAME), but the feature's asset
        # type (group 1 / type 2) is a configured valid object of exactly one
        # tier (Electric Distribution). The from-tier is inferred best-effort.
        de = _tier_data_element()
        flc = _tier_flc("", subnet_rank=5, assetgroup=1, assettype=2)
        result = self._run(de, flc)
        assert result["status"] == svc.TIER_RESOLVED
        assert result["tierName"] == "Electric Distribution"
        assert result["resolvedBy"] == "configured"

    def test_no_membership_multiple_configured_tiers_is_ambiguous(self) -> None:
        # Asset type 3 is configured-valid only in Distribution here, so to get a
        # multi-configured case we make the feature valid in both tiers by using
        # a data element where group 1 / type 2 is valid in both.
        de = _tier_data_element()
        # Make the feature (group 1 / type 2) also valid in Transmission.
        de["domainNetworks"][0]["tiers"][0]["validDevices"] = [
            {"assetGroupCode": 1, "assetTypes": [{"assetTypeCode": 2}]},
        ]
        flc = _tier_flc("", subnet_rank=5, assetgroup=1, assettype=2)
        result = self._run(de, flc)
        assert result["status"] == svc.TIER_AMBIGUOUS
        assert sorted(result["configuredTiers"]) == [
            "Electric Distribution",
            "Electric Transmission",
        ]
        assert result["resolvedBy"] == "configured"

    def test_no_membership_multiple_configured_resolved_by_tier_name(self) -> None:
        de = _tier_data_element()
        de["domainNetworks"][0]["tiers"][0]["validDevices"] = [
            {"assetGroupCode": 1, "assetTypes": [{"assetTypeCode": 2}]},
        ]
        flc = _tier_flc("", subnet_rank=5, assetgroup=1, assettype=2)
        result = self._run(de, flc, tier_name="Electric Distribution")
        assert result["status"] == svc.TIER_RESOLVED
        assert result["tierName"] == "Electric Distribution"
        assert result["resolvedBy"] == "configured"

    def test_no_membership_and_not_configured_is_no_membership(self) -> None:
        # Feature's asset type is not a valid object of any tier -> no membership.
        de = _tier_data_element()
        flc = _tier_flc("", subnet_rank=5, assetgroup=999, assettype=999)
        result = self._run(de, flc)
        assert result["status"] == svc.TIER_NO_MEMBERSHIP


class TestTraceResponseErrorHandling:
    def test_multiple_subnetwork_controllers_actionable_error(self) -> None:
        raw = {
            "success": False,
            "error": {
                "extendedCode": svc._MULTIPLE_SUBNETWORK_CONTROLLERS,
                "message": "multiple subnetwork controllers ...",
            },
        }
        with pytest.raises(RuntimeError, match="multiple subnetworks"):
            svc._trace_response("downstream", "https://server/UN/FeatureServer", "{a}", raw)

    def test_generic_error_still_raises(self) -> None:
        raw = {"success": False, "error": {"extendedCode": -1, "message": "boom"}}
        with pytest.raises(RuntimeError, match="Trace failed"):
            svc._trace_response("downstream", "https://server/UN/FeatureServer", "{a}", raw)

    def test_resolution_status_passthrough(self) -> None:
        raw = {"status": svc.TIER_AMBIGUOUS, "memberTiers": ["A", "B"]}
        result = svc._trace_response("downstream", "https://server/UN/FeatureServer", "{a}", raw)
        assert result["status"] == svc.TIER_AMBIGUOUS
        assert result["memberTiers"] == ["A", "B"]

    def test_success_builds_response(self) -> None:
        raw = {"success": True, "traceResults": {"elements": [1, 2, 3]}}
        result = svc._trace_response("downstream", "https://server/UN/FeatureServer", "{a}", raw)
        assert result["traceType"] == "downstream"
        assert result["traceResults"]["elements"] == [1, 2, 3]

    def test_configured_resolution_adds_best_effort_note(self) -> None:
        raw = {
            "success": True,
            "traceResults": {"elements": [1]},
            "_tierResolution": {"resolvedBy": "configured", "tierName": "Electric Distribution"},
        }
        result = svc._trace_response("downstream", "https://server/UN/FeatureServer", "{a}", raw)
        assert result["tierResolution"]["resolvedBy"] == "configured"
        assert result["tierResolution"]["tierName"] == "Electric Distribution"
        assert "best-effort" in result["tierResolution"]["note"]
        # The internal marker must not leak into traceResults.
        assert "_tierResolution" not in result["traceResults"]

    def test_membership_resolution_adds_no_note(self) -> None:
        raw = {
            "success": True,
            "traceResults": {"elements": [1]},
            "_tierResolution": {"resolvedBy": "membership", "tierName": "Electric Distribution"},
        }
        result = svc._trace_response("downstream", "https://server/UN/FeatureServer", "{a}", raw)
        assert "tierResolution" not in result


class TestConfiguredTiersForFeature:
    def test_matches_single_tier(self) -> None:
        de = _tier_data_element()
        domain = de["domainNetworks"][0]
        tiers = svc._parse_configured_tiers_for_feature(domain, {"assetgroup": 1, "assettype": 2})
        assert tiers == ["Electric Distribution"]

    def test_matches_multiple_tiers(self) -> None:
        de = _tier_data_element()
        domain = de["domainNetworks"][0]
        domain["tiers"][0]["validDevices"] = [
            {"assetGroupCode": 1, "assetTypes": [{"assetTypeCode": 2}]},
        ]
        tiers = svc._parse_configured_tiers_for_feature(domain, {"assetgroup": 1, "assettype": 2})
        assert sorted(tiers) == ["Electric Distribution", "Electric Transmission"]

    def test_no_match_returns_empty(self) -> None:
        de = _tier_data_element()
        domain = de["domainNetworks"][0]
        tiers = svc._parse_configured_tiers_for_feature(
            domain, {"assetgroup": 999, "assettype": 999}
        )
        assert tiers == []

    def test_missing_attrs_returns_empty(self) -> None:
        de = _tier_data_element()
        domain = de["domainNetworks"][0]
        assert svc._parse_configured_tiers_for_feature(domain, {}) == []


class TestNormalizeTraceLocation:
    def test_snake_case_keys_become_rest_keys(self) -> None:
        loc = svc._normalize_trace_location(
            {"global_id": "{a}", "terminal_id": 2, "percent_along": 0.5}, "startingPoint", "s"
        )
        assert loc == {
            "traceLocationType": "startingPoint",
            "globalId": "{a}",
            "terminalId": 2,
            "percentAlong": 0.5,
        }

    def test_camel_case_keys_pass_through_and_none_dropped(self) -> None:
        loc = svc._normalize_trace_location(
            {"globalId": "{a}", "terminalId": None}, "startingPoint", "s"
        )
        assert loc == {"traceLocationType": "startingPoint", "globalId": "{a}"}

    def test_barrier_keeps_filter_flag_but_start_drops_it(self) -> None:
        barrier = svc._normalize_trace_location(
            {"global_id": "{a}", "is_filter_barrier": True}, "barrier", "b"
        )
        start = svc._normalize_trace_location(
            {"global_id": "{a}", "is_filter_barrier": True}, "startingPoint", "s"
        )
        assert barrier["isFilterBarrier"] is True
        assert "isFilterBarrier" not in start

    def test_missing_global_id_raises(self) -> None:
        with pytest.raises(ValueError, match="global_id"):
            svc._normalize_trace_location({"terminal_id": 1}, "startingPoint", "starting_points[0]")

    def test_percent_along_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="percent_along"):
            svc._normalize_trace_location(
                {"global_id": "{a}", "percent_along": 1.5}, "startingPoint", "s"
            )

    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            svc._normalize_trace_location("{a}", "startingPoint", "s")  # type: ignore[arg-type]


class TestNormalizeResultTypes:
    def test_default_is_elements(self) -> None:
        assert svc._normalize_result_types(None) == [{"type": "elements"}]
        assert svc._normalize_result_types([]) == [{"type": "elements"}]

    def test_strings_and_snake_case_objects(self) -> None:
        result = svc._normalize_result_types(
            ["connectivity", {"type": "features", "include_geometry": True}]
        )
        assert result == [
            {"type": "connectivity"},
            {"type": "features", "includeGeometry": True},
        ]

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid result type"):
            svc._normalize_result_types(["bogus"])

    def test_non_string_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="string or an object"):
            svc._normalize_result_types([5])  # type: ignore[list-item]


class TestValidateTraceRequest:
    def test_invalid_trace_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid trace_type"):
            svc._validate_trace_request("nope", [{"global_id": "{a}"}], None, None)

    @pytest.mark.parametrize("trace_type", sorted(svc._UN_TRACE_TYPES - {"shortestPath"}))
    def test_every_type_accepts_one_start(self, trace_type: str) -> None:
        starts, barriers, stops = svc._validate_trace_request(
            trace_type, [{"global_id": "{a}"}], [{"global_id": "{b}"}], None
        )
        assert len(starts) == 1 and starts[0]["traceLocationType"] == "startingPoint"
        assert barriers[0]["traceLocationType"] == "barrier"
        assert stops == []

    def test_no_start_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one starting point"):
            svc._validate_trace_request("downstream", [], None, None)

    def test_shortest_path_needs_two_starts(self) -> None:
        with pytest.raises(ValueError, match="two starting points"):
            svc._validate_trace_request("shortestPath", [{"global_id": "{a}"}], None, None)

    def test_subnetwork_by_name_has_empty_locations(self) -> None:
        starts, barriers, stops = svc._validate_trace_request("subnetwork", None, None, "RMT001")
        assert starts == [] and barriers == [] and stops == []

    def test_subnetwork_name_does_not_exempt_other_types(self) -> None:
        with pytest.raises(ValueError, match="At least one starting point"):
            svc._validate_trace_request("downstream", None, None, "RMT001")


class TestBuildTraceConfiguration:
    def test_hints_do_not_override_supplied_config(self) -> None:
        config = svc._build_trace_configuration(
            {"tierName": "Mine", "includeContainers": True}, "Electric", "Other", "S1"
        )
        assert config == {
            "tierName": "Mine",
            "includeContainers": True,
            "domainNetworkName": "Electric",
            "subnetworkName": "S1",
        }

    def test_does_not_mutate_input(self) -> None:
        original = {"conditionBarriers": [{"name": "x"}]}
        svc._build_trace_configuration(original, "Electric", None, None)
        assert original == {"conditionBarriers": [{"name": "x"}]}

    def test_empty_when_nothing_supplied(self) -> None:
        assert svc._build_trace_configuration(None, None, None, None) == {}


class TestRunUtilityNetworkTrace:
    URL = "https://server/arcgis/rest/services/UN/FeatureServer"

    def _run(self, **kwargs):
        manager = MagicMock()
        manager.trace.return_value = {"success": True, "traceResults": {"elements": []}}
        with patch.object(svc, "UtilityNetworkManager", return_value=manager):
            raw = svc.run_utility_network_trace(MagicMock(), self.URL, **kwargs)
        return manager, raw

    def test_passes_locations_configuration_and_result_types(self) -> None:
        config = {"includeContainers": True}
        manager, _ = self._run(
            trace_type="connected",
            starting_points=[{"global_id": "{a}", "terminal_id": 1}],
            barriers=[{"global_id": "{b}"}],
            trace_configuration=config,
            result_types=["elements", "aggregatedGeometry"],
            tier_name="Dist",
            moment=123,
            out_sr=3857,
        )
        kwargs = manager.trace.call_args.kwargs
        assert [loc["traceLocationType"] for loc in kwargs["locations"]] == [
            "startingPoint",
            "barrier",
        ]
        assert kwargs["trace_type"] == "connected"
        assert kwargs["configuration"] == {"includeContainers": True, "tierName": "Dist"}
        assert kwargs["result_types"] == [{"type": "elements"}, {"type": "aggregatedGeometry"}]
        assert kwargs["moment"] == 123 and kwargs["out_sr"] == 3857
        assert config == {"includeContainers": True}

    def test_no_configuration_sends_none(self) -> None:
        manager, _ = self._run(trace_type="loops", starting_points=[{"global_id": "{a}"}])
        assert manager.trace.call_args.kwargs["configuration"] is None

    def test_subnetwork_by_name_sends_empty_locations(self) -> None:
        manager, _ = self._run(
            trace_type="subnetwork", starting_points=None, subnetwork_name="RMT001"
        )
        kwargs = manager.trace.call_args.kwargs
        assert kwargs["locations"] == []
        assert kwargs["configuration"] == {"subnetworkName": "RMT001"}

    def test_downstream_applies_tier_definition(self) -> None:
        tier_config = {"conditionBarriers": [{"name": "ctrl"}]}
        resolution = {
            "status": svc.TIER_RESOLVED,
            "domainNetworkName": "Electric",
            "tierName": "Dist",
            "resolvedBy": "membership",
        }
        tier = {"updateSubnetworkTraceConfiguration": tier_config}
        with (
            patch.object(svc, "_get_data_element", return_value={}),
            patch.object(svc, "_resolve_feature_tier", return_value=resolution),
            patch.object(svc, "_parse_tier_definition", return_value=({}, tier)),
        ):
            manager, raw = self._run(
                trace_type="downstream", starting_points=[{"global_id": "{a}"}]
            )
        assert manager.trace.call_args.kwargs["configuration"] == {
            **tier_config,
            "domainNetworkName": "Electric",
            "tierName": "Dist",
        }
        assert raw["_tierResolution"] == {"resolvedBy": "membership", "tierName": "Dist"}

    def test_ambiguous_tier_returned_without_tracing(self) -> None:
        resolution = {"status": svc.TIER_AMBIGUOUS, "memberTiers": ["A", "B"]}
        manager = MagicMock()
        with (
            patch.object(svc, "UtilityNetworkManager", return_value=manager),
            patch.object(svc, "_get_data_element", return_value={}),
            patch.object(svc, "_resolve_feature_tier", return_value=resolution),
        ):
            raw = svc.run_utility_network_trace(
                MagicMock(),
                self.URL,
                trace_type="upstream",
                starting_points=[{"global_id": "{a}"}],
            )
        assert raw == resolution
        manager.trace.assert_not_called()

    def test_use_tier_defaults_false_skips_resolution(self) -> None:
        with patch.object(svc, "_resolve_feature_tier") as resolve:
            manager, _ = self._run(
                trace_type="downstream",
                starting_points=[{"global_id": "{a}"}],
                use_tier_defaults=False,
            )
        resolve.assert_not_called()
        assert manager.trace.call_args.kwargs["configuration"] is None

    def test_explicit_configuration_skips_tier_resolution(self) -> None:
        with patch.object(svc, "_resolve_feature_tier") as resolve:
            self._run(
                trace_type="downstream",
                starting_points=[{"global_id": "{a}"}],
                trace_configuration={"includeBarriers": False},
            )
        resolve.assert_not_called()

    def test_retries_after_topology_validation_when_no_starting_points(self) -> None:
        manager = MagicMock()
        manager.trace.side_effect = [
            {"error": {"extendedCode": svc._NO_STARTING_POINTS}},
            {"success": True, "traceResults": {"elements": [1]}},
        ]
        with (
            patch.object(svc, "UtilityNetworkManager", return_value=manager),
            patch.object(svc, "_validate_topology") as validate,
        ):
            raw = svc.run_utility_network_trace(
                MagicMock(),
                self.URL,
                trace_type="connected",
                starting_points=[{"global_id": "{a}"}],
            )
        validate.assert_called_once()
        assert manager.trace.call_count == 2
        assert raw["traceResults"]["elements"] == [1]

    def test_invalid_request_raises_before_calling_server(self) -> None:
        with (
            patch.object(svc, "UtilityNetworkManager") as manager_cls,
            pytest.raises(ValueError),
        ):
            svc.run_utility_network_trace(
                MagicMock(), self.URL, trace_type="shortestPath", starting_points=[]
            )
        manager_cls.assert_not_called()


class TestLimitTraceElements:
    def test_truncates_and_notes(self) -> None:
        response = {"traceResults": {"elements": list(range(10))}}
        svc._limit_trace_elements(response, 3)
        assert response["traceResults"]["elements"] == [0, 1, 2]
        assert response["traceResults"]["totalElements"] == 10
        assert response["traceResults"]["truncated"] is True

    def test_none_means_no_cap(self) -> None:
        response = {"traceResults": {"elements": list(range(10))}}
        svc._limit_trace_elements(response, None)
        assert len(response["traceResults"]["elements"]) == 10
        assert "truncated" not in response["traceResults"]

    def test_no_elements_is_untouched(self) -> None:
        response = {"traceResults": {"features": []}}
        svc._limit_trace_elements(response, 3)
        assert response == {"traceResults": {"features": []}}


class TestUtilityNetworkTraceTool:
    URL = "https://server/arcgis/rest/services/UN/FeatureServer"

    async def _call(self, **kwargs):
        return await svc.utility_network_trace(network_service_url=self.URL, **kwargs)

    async def test_invalid_input_returns_error_without_connecting(self) -> None:
        with patch.object(svc, "_connect_gis") as connect:
            result = await self._call(trace_type="bogus", starting_points=[{"global_id": "{a}"}])
        assert "Invalid trace_type" in result["error"]
        connect.assert_not_called()

    async def test_success_summarizes_and_limits(self) -> None:
        raw = {
            "success": True,
            "traceResults": {
                "elements": [
                    {"networkSourceId": 1, "assetGroupName": "G", "assetTypeName": "T"}
                    for _ in range(5)
                ]
            },
        }
        with (
            patch.object(svc, "_connect_gis", return_value=MagicMock()),
            patch.object(svc, "run_utility_network_trace", return_value=raw),
            patch.object(svc, "_enrich_trace_elements", side_effect=lambda r, *_: r),
        ):
            result = await self._call(
                trace_type="connected",
                starting_points=[{"global_id": "{a}"}],
                max_elements=2,
                summarize=True,
            )
        assert result["traceType"] == "connected"
        assert result["startingGlobalId"] == "{a}"
        assert len(result["traceResults"]["elements"]) == 2
        assert result["traceResults"]["totalElements"] == 5
        assert result["summary"]["totalElements"] == 5
        assert "elements" not in result["summary"]

    async def test_source_names_filled_from_mapping_and_summary_has_no_paging(self) -> None:
        raw = {
            "success": True,
            "traceResults": {
                "sourceMapping": {"9": "ElectricDevice"},
                "elements": [
                    {"networkSourceId": 9, "sourceName": "", "assetGroupName": "G"}
                    for _ in range(3)
                ],
            },
        }
        with (
            patch.object(svc, "_connect_gis", return_value=MagicMock()),
            patch.object(svc, "run_utility_network_trace", return_value=raw),
            patch.object(svc, "_enrich_trace_elements", side_effect=lambda r, *_: r),
        ):
            result = await self._call(
                trace_type="connected", starting_points=[{"global_id": "{a}"}], summarize=True
            )
        assert {e["sourceName"] for e in result["traceResults"]["elements"]} == {"ElectricDevice"}
        assert result["summary"]["groups"][0]["sourceName"] == "ElectricDevice"
        assert "truncated" not in result["summary"]
        assert "note" not in result["summary"]

    async def test_tier_ambiguity_passthrough(self) -> None:
        resolution = {"status": svc.TIER_AMBIGUOUS, "memberTiers": ["A", "B"]}
        with (
            patch.object(svc, "_connect_gis", return_value=MagicMock()),
            patch.object(svc, "run_utility_network_trace", return_value=resolution),
        ):
            result = await self._call(
                trace_type="downstream", starting_points=[{"global_id": "{a}"}]
            )
        assert result == resolution

    async def test_server_error_raises(self) -> None:
        raw = {"success": False, "error": {"extendedCode": -1, "message": "boom"}}
        with (
            patch.object(svc, "_connect_gis", return_value=MagicMock()),
            patch.object(svc, "run_utility_network_trace", return_value=raw),
            pytest.raises(RuntimeError, match="Trace failed"),
        ):
            await self._call(trace_type="connected", starting_points=[{"global_id": "{a}"}])


class TestSkillFiles:
    def test_every_prompt_skill_file_exists(self) -> None:
        import inspect
        import re

        names = re.findall(r'_read_skill\("([^"]+)"\)', inspect.getsource(svc))
        assert names, "expected prompts that read skill files"
        missing = [n for n in names if not (svc._SKILLS_DIR / n).exists()]
        assert missing == []

    async def test_only_one_ad_hoc_trace_tool_is_exposed(self) -> None:
        tools = {t.name for t in await svc.utilitynetwork_router.list_tools()}
        assert "utility_network_trace" in tools
        assert "network_named_trace" in tools
        for disabled in ("network_downstream_trace", "network_upstream_trace", "network_trace"):
            assert disabled not in tools
            assert not hasattr(svc, disabled)
        assert not any("generic" in name for name in tools)

    async def test_trace_guide_prompt_is_exposed(self) -> None:
        prompts = {p.name for p in await svc.utilitynetwork_router.list_prompts()}
        assert "utility_network_trace_guide" in prompts
        assert not any("generic" in name for name in prompts)

    def test_archived_isolation_skill_is_not_served(self) -> None:
        assert not (svc._SKILLS_DIR / "isolation_analysis.md").exists()
        assert not hasattr(svc, "utility_network_isolation_analysis")

    def test_trace_skill_covers_isolation_post_processing(self) -> None:
        text = svc._read_skill("utilitynetwork_trace.md")
        assert "Remove the starting feature" in text
        assert "esriUNFCUTDevice" in text


class TestUtilityNetworkTraceSkill:
    @pytest.mark.parametrize("trace_type", sorted(svc._UN_TRACE_TYPES))
    def test_skill_has_a_section_for_every_trace_type(self, trace_type: str) -> None:
        text = svc._read_skill("utilitynetwork_trace.md")
        assert f"`{trace_type}`" in text
        assert any(
            line.startswith("### 3.") and f"`{trace_type}`" in line for line in text.splitlines()
        )

    @pytest.mark.parametrize("result_type", sorted(svc._UN_RESULT_TYPES))
    def test_skill_documents_every_result_type(self, result_type: str) -> None:
        assert f"`{result_type}`" in svc._read_skill("utilitynetwork_trace.md")

    def test_skill_documents_every_tool_parameter(self) -> None:
        import inspect

        text = svc._read_skill("utilitynetwork_trace.md")
        for name in inspect.signature(svc.utility_network_trace).parameters:
            if name in {"network_service_url", "token"}:
                continue
            assert f"`{name}`" in text, name

    def test_prompt_serves_skill_file(self) -> None:
        text = svc.utility_network_trace_guide()
        assert "utility_network_trace" in text
        assert text.startswith("---")


class TestTraceTypeRules:
    """Mandatory/optional input rules per trace type (mirrors skills/utilitynetwork_trace.md)."""

    START: ClassVar[list[dict[str, Any]]] = [{"global_id": "{a}"}]

    def test_loops_rejects_multiple_starting_points(self) -> None:
        with pytest.raises(ValueError, match="single starting point"):
            svc._validate_trace_request(
                "loops", [{"global_id": "{a}"}, {"global_id": "{b}"}], None, None
            )

    def test_path_accepts_stopping_points(self) -> None:
        _, _, stops = svc._validate_trace_request(
            "path", self.START, None, None, [{"global_id": "{z}", "terminal_id": 1}]
        )
        assert stops == [{"traceLocationType": "stoppingPoint", "globalId": "{z}", "terminalId": 1}]

    @pytest.mark.parametrize("trace_type", ["downstream", "connected", "isolation", "circuit"])
    def test_stopping_points_rejected_outside_path(self, trace_type: str) -> None:
        with pytest.raises(ValueError, match="only used by path"):
            svc._validate_trace_request(trace_type, self.START, None, None, [{"global_id": "{z}"}])

    def test_circuit_by_name_needs_no_starting_point(self) -> None:
        starts, _, _ = svc._validate_trace_request(
            "circuit", None, None, None, None, {"circuitName": "C1"}
        )
        assert starts == []

    def test_circuit_without_start_or_name_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one starting point"):
            svc._validate_trace_request("circuit", None, None, None)

    def test_subnetwork_name_with_starts_clears_locations(self) -> None:
        starts, _, _ = svc._validate_trace_request(
            "subnetworkController", self.START, None, "RMT001"
        )
        assert starts == []

    def test_shortest_path_message_points_to_path(self) -> None:
        with pytest.raises(ValueError, match="path trace"):
            svc._validate_trace_request("shortestPath", self.START, None, None)

    def test_warnings_for_shortest_path_and_path_without_stop(self) -> None:
        assert "deprecated" in svc._trace_warnings("shortestPath", None)[0]
        assert "stopping point" in svc._trace_warnings("path", None)[0]
        assert svc._trace_warnings("path", [{"global_id": "{z}"}]) == []
        assert svc._trace_warnings("connected", None) == []


class TestFilterBarrierDetection:
    def test_config_filter_barriers(self) -> None:
        assert svc._has_filter_barrier({"filterBarriers": [{"name": "x"}]}, [])

    def test_config_filter_function_barriers(self) -> None:
        assert svc._has_filter_barrier({"filterFunctionBarriers": [{"x": 1}]}, [])

    def test_filter_barrier_location(self) -> None:
        assert svc._has_filter_barrier({}, [{"globalId": "{a}", "isFilterBarrier": True}])

    def test_none_present(self) -> None:
        assert not svc._has_filter_barrier({"filterBarriers": []}, [{"globalId": "{a}"}])


class TestTraceConfigurationMerge:
    def test_empty_hint_values_are_filled_but_populated_are_kept(self) -> None:
        config = svc._build_trace_configuration(
            {"tierName": "", "domainNetworkName": "Keep"}, "Other", "Dist", None
        )
        assert config["tierName"] == "Dist"
        assert config["domainNetworkName"] == "Keep"

    def test_target_tier_hint(self) -> None:
        config = svc._build_trace_configuration(None, "Electric", "Dist", None, "Transmission")
        assert config["targetTierName"] == "Transmission"

    def test_overrides_replace_values(self) -> None:
        config = svc._build_trace_configuration(
            {"includeContainers": False}, None, None, None, None, {"includeContainers": True}
        )
        assert config == {"includeContainers": True}


class TestRunUtilityNetworkTraceByType:
    URL = "https://server/arcgis/rest/services/UN/FeatureServer"
    RESOLUTION: ClassVar[dict[str, Any]] = {
        "status": svc.TIER_RESOLVED,
        "domainNetworkName": "Electric",
        "tierName": "Dist",
        "resolvedBy": "membership",
    }
    TIER: ClassVar[dict[str, Any]] = {
        "updateSubnetworkTraceConfiguration": {"includeBarriers": True}
    }

    def _run(self, **kwargs):
        manager = MagicMock()
        manager.trace.return_value = {"success": True, "traceResults": {"elements": []}}
        with (
            patch.object(svc, "UtilityNetworkManager", return_value=manager),
            patch.object(svc, "_get_data_element", return_value={}),
            patch.object(svc, "_resolve_feature_tier", return_value=self.RESOLUTION),
            patch.object(svc, "_parse_tier_definition", return_value=({}, self.TIER)),
        ):
            svc.run_utility_network_trace(MagicMock(), self.URL, **kwargs)
        return manager.trace.call_args.kwargs

    @pytest.mark.parametrize("trace_type", ["subnetwork", "subnetworkController", "upstream"])
    def test_tier_defaults_applied_to_subnetwork_based_types(self, trace_type: str) -> None:
        kwargs = self._run(trace_type=trace_type, starting_points=[{"global_id": "{a}"}])
        assert kwargs["configuration"]["includeBarriers"] is True
        assert kwargs["configuration"]["tierName"] == "Dist"

    @pytest.mark.parametrize("trace_type", ["connected", "loops", "path"])
    def test_tier_defaults_not_applied_to_network_traces(self, trace_type: str) -> None:
        kwargs = self._run(
            trace_type=trace_type,
            starting_points=[{"global_id": "{a}"}],
            stopping_points=[{"global_id": "{z}"}] if trace_type == "path" else None,
        )
        assert kwargs["configuration"] is None

    def test_subnetwork_by_name_uses_explicit_tier_definition(self) -> None:
        kwargs = self._run(
            trace_type="subnetwork",
            starting_points=None,
            subnetwork_name="RMT001",
            domain_network_name="Electric",
            tier_name="Dist",
        )
        assert kwargs["locations"] == []
        assert kwargs["configuration"]["includeBarriers"] is True
        assert kwargs["configuration"]["subnetworkName"] == "RMT001"

    def test_subnetwork_by_name_without_tier_sends_only_name(self) -> None:
        kwargs = self._run(trace_type="subnetwork", starting_points=None, subnetwork_name="RMT001")
        assert kwargs["configuration"] == {"subnetworkName": "RMT001"}

    def test_overrides_and_target_tier_applied_over_tier_defaults(self) -> None:
        kwargs = self._run(
            trace_type="downstream",
            starting_points=[{"global_id": "{a}"}],
            target_tier_name="Transmission",
            configuration_overrides={"includeBarriers": False, "includeContainers": True},
        )
        config = kwargs["configuration"]
        assert config["targetTierName"] == "Transmission"
        assert config["includeBarriers"] is False
        assert config["includeContainers"] is True

    def test_path_sends_start_and_stop_locations(self) -> None:
        kwargs = self._run(
            trace_type="path",
            starting_points=[{"global_id": "{a}", "terminal_id": 1}],
            stopping_points=[{"global_id": "{z}", "terminal_id": 2}],
            trace_configuration={"shortestPathNetworkAttributeName": "Shape length"},
        )
        assert [loc["traceLocationType"] for loc in kwargs["locations"]] == [
            "startingPoint",
            "stoppingPoint",
        ]
        assert kwargs["trace_type"] == "path"

    def test_isolation_without_filter_barrier_raises(self) -> None:
        with pytest.raises(ValueError, match="filter barrier"):
            self._run(trace_type="isolation", starting_points=[{"global_id": "{a}"}])

    def test_isolation_with_filter_barrier_in_overrides_runs(self) -> None:
        kwargs = self._run(
            trace_type="isolation",
            starting_points=[{"global_id": "{a}"}],
            configuration_overrides={"filterBarriers": [{"name": "Category"}]},
        )
        assert kwargs["configuration"]["filterBarriers"] == [{"name": "Category"}]

    def test_isolation_with_filter_barrier_location_runs(self) -> None:
        kwargs = self._run(
            trace_type="isolation",
            starting_points=[{"global_id": "{a}"}],
            barriers=[{"global_id": "{b}", "is_filter_barrier": True}],
        )
        assert kwargs["locations"][-1]["isFilterBarrier"] is True


class TestUtilityNetworkTraceToolWarnings:
    URL = "https://server/arcgis/rest/services/UN/FeatureServer"

    async def test_isolation_error_returned_not_raised(self) -> None:
        with (
            patch.object(svc, "_connect_gis", return_value=MagicMock()),
            patch.object(
                svc, "run_utility_network_trace", side_effect=ValueError("needs a filter barrier")
            ),
        ):
            result = await svc.utility_network_trace(
                trace_type="isolation",
                starting_points=[{"global_id": "{a}"}],
                network_service_url=self.URL,
            )
        assert result == {"error": "needs a filter barrier"}

    async def test_path_without_stop_adds_warning(self) -> None:
        raw = {"success": True, "traceResults": {"elements": []}}
        with (
            patch.object(svc, "_connect_gis", return_value=MagicMock()),
            patch.object(svc, "run_utility_network_trace", return_value=raw),
            patch.object(svc, "_enrich_trace_elements", side_effect=lambda r, *_: r),
        ):
            result = await svc.utility_network_trace(
                trace_type="path",
                starting_points=[{"global_id": "{a}"}],
                network_service_url=self.URL,
            )
        assert "stopping point" in result["warnings"][0]

    async def test_stopping_points_on_wrong_type_returns_error(self) -> None:
        result = await svc.utility_network_trace(
            trace_type="downstream",
            starting_points=[{"global_id": "{a}"}],
            stopping_points=[{"global_id": "{z}"}],
            network_service_url=self.URL,
        )
        assert "only used by path" in result["error"]
