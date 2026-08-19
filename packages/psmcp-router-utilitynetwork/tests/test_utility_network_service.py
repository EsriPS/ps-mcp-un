"""Tests for the utility network router service."""

from __future__ import annotations

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
            "traceConfigurations": [{"globalId": "{guid}", "title": "Distribution Isolation Trace"}],
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
            features=[MagicMock(attributes={"meter_id": "M1", "full_name": "Jane", "account_status": "active"})]
        )

        with patch.object(svc, "_find_layer", return_value=cust_layer):
            result = svc.get_customer_data(gis, "https://server/UN/FeatureServer", [], meter_ids=["M1"])

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
            "traceConfigurations": [{"globalId": "{cfg-id}", "name": "Downstream Service Point Trace", "traceType": "downstream"}],
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
            "traceConfigurations": [{"globalId": "{cfg-id}", "name": "Some Trace", "traceType": "downstream"}],
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
                {"globalId": "{cfg-id}", "name": "Downstream - XFR Load and Customer Count", "traceType": "downstream"},
            ],
        }
        terminals_info = {
            "assetGroupName": "Medium Voltage Transformer",
            "assetTypeName": "Overhead Single Phase - MV->LV",
            "usageType": "esriUNFCUTDevice",
            "terminals": [
                {"terminalId": 7, "terminalName": "2wXFR:Primary", "recommendedFor": "upstream"},
                {"terminalId": 8, "terminalName": "2wXFR:Secondary", "recommendedFor": "downstream"},
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
            "traceConfigurations": [{"globalId": "{cfg-id}", "name": "Some Trace", "traceType": "downstream"}],
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
            "traceConfigurations": [{"globalId": "{cfg-id}", "name": "Some Trace", "traceType": "downstream"}],
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
            "traceConfigurations": [{"globalId": "{cfg-id}", "name": "Downstream Service Point Trace", "traceType": "downstream"}],
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
            features=[MagicMock(attributes={"SUBNETWORKNAME": subnetworkname, "TIERNAME": subnet_rank})]
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
            MagicMock(), "https://server/UN/FeatureServer", "{x}", {"title": "T", "traceConfiguration": {}}
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
            result = svc.get_device_terminals(
                MagicMock(), "https://server/UN/FeatureServer", "{a}"
            )

        assert result["terminalCount"] == 2
        assert result["terminalConfigurationId"] == 5
        assert result["assetTypeName"] == "Overhead Single Phase"
        assert [t["terminalId"] for t in result["terminals"]] == [1, 2]
        assert result["usageType"] == "esriUNFCUTDevice"
        recommended = {t["terminalId"]: t["recommendedFor"] for t in result["terminals"]}
        assert recommended == {1: "upstream", 2: "downstream"}

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
                svc.get_device_terminals(
                    MagicMock(), "https://server/UN/FeatureServer", "{a}"
                )


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
