"""Tests for the generic utility network trace tool."""

from unittest.mock import MagicMock, patch

import pytest
from psmcp_router_utilitynetwork import utility_network_service as traces
from psmcp_router_utilitynetwork.utility_network_service import (
    _enrich_trace_elements,
    network_trace,
)

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_DATA_ELEMENT = {
    "domainNetworks": [
        {
            "domainNetworkName": "ElectricDistribution",
            "junctionSources": [
                {
                    "sourceId": 9,
                    "name": "ElectricDevice",
                    "assetGroups": [
                        {
                            "assetGroupCode": 4,
                            "assetGroupName": "Medium Voltage Transformer",
                            "assetTypes": [
                                {"assetTypeCode": 12, "assetTypeName": "Three Phase Padmount"}
                            ],
                        }
                    ],
                }
            ],
            "edgeSources": [
                {
                    "sourceId": 11,
                    "name": "ElectricLine",
                    "assetGroups": [
                        {
                            "assetGroupCode": 2,
                            "assetGroupName": "Medium Voltage",
                            "assetTypes": [
                                {"assetTypeCode": 1, "assetTypeName": "Underground Single Phase"}
                            ],
                        }
                    ],
                }
            ],
        }
    ],
    "terminalConfigurations": [
        {
            "terminalConfigurationId": 1,
            "terminalConfigurationName": "Two Terminal",
            "terminals": [
                {"terminalId": 1, "terminalName": "High"},
                {"terminalId": 2, "terminalName": "Low"},
            ],
        }
    ],
}

MOCK_TRACE_RAW = {
    "traceResults": {
        "elements": [
            {
                "networkSourceId": 9,
                "globalId": "{ELEM-1}",
                "objectId": 100,
                "terminalId": 1,
                "assetGroupCode": 4,
                "assetTypeCode": 12,
            }
        ],
        "sourceMapping": {"9": "ElectricDevice"},
    }
}


# ---------------------------------------------------------------------------
# Tests for _enrich_trace_elements
# ---------------------------------------------------------------------------


class TestEnrichTraceElements:
    def test_adds_resolved_names_to_elements(self) -> None:
        raw = {
            "traceResults": {
                "elements": [
                    {
                        "networkSourceId": 9,
                        "globalId": "{ELEM-1}",
                        "objectId": 100,
                        "terminalId": 1,
                        "assetGroupCode": 4,
                        "assetTypeCode": 12,
                    }
                ],
            }
        }

        with patch.object(traces, "_get_data_element", return_value=MOCK_DATA_ELEMENT):
            result = _enrich_trace_elements(raw, "https://server/FeatureServer", None)

        elem = result["traceResults"]["elements"][0]
        assert elem["sourceName"] == "ElectricDevice"
        assert elem["assetGroupName"] == "Medium Voltage Transformer"
        assert elem["assetTypeName"] == "Three Phase Padmount"

    def test_handles_empty_elements(self) -> None:
        raw = {"traceResults": {"elements": []}}

        result = _enrich_trace_elements(raw, "https://server/FeatureServer", None)

        assert result["traceResults"]["elements"] == []

    def test_handles_missing_elements_key(self) -> None:
        raw = {"traceResults": {}}

        result = _enrich_trace_elements(raw, "https://server/FeatureServer", None)

        assert result == {"traceResults": {}}

    def test_handles_unknown_source_id(self) -> None:
        raw = {
            "traceResults": {
                "elements": [
                    {
                        "networkSourceId": 999,
                        "globalId": "{UNKNOWN}",
                        "objectId": 1,
                        "assetGroupCode": 1,
                        "assetTypeCode": 1,
                    }
                ],
            }
        }

        with patch.object(traces, "_get_data_element", return_value=MOCK_DATA_ELEMENT):
            result = _enrich_trace_elements(raw, "https://server/FeatureServer", None)

        elem = result["traceResults"]["elements"][0]
        assert elem["sourceName"] == ""
        assert elem["assetGroupName"] == ""
        assert elem["assetTypeName"] == ""


# ---------------------------------------------------------------------------
# Tests for network_trace tool
# ---------------------------------------------------------------------------


class TestNetworkTrace:
    async def test_passes_correct_trace_type(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://server/FeatureServer")

        mock_gis = MagicMock()

        with (
            patch.object(traces, "_connect_gis", return_value=mock_gis),
            patch.object(traces, "run_trace", return_value=MOCK_TRACE_RAW) as mock_run,
            patch.object(traces, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            await network_trace(
                starting_global_id="{START-ID}",
                trace_type="isolation",
            )

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        # trace_type is the 3rd positional argument
        assert call_args[0][2] == "isolation"

    async def test_passes_subnetwork_name_in_configuration(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://server/FeatureServer")

        mock_gis = MagicMock()

        with (
            patch.object(traces, "_connect_gis", return_value=mock_gis),
            patch.object(
                traces, "_run_trace_with_subnetwork", return_value=MOCK_TRACE_RAW
            ) as mock_sub_trace,
            patch.object(traces, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            await network_trace(
                starting_global_id="{START-ID}",
                trace_type="subnetwork",
                subnetwork_name="Sub1",
            )

        mock_sub_trace.assert_called_once()
        call_args = mock_sub_trace.call_args
        # subnetwork_name is the last positional argument
        assert call_args[0][-1] == "Sub1"

    async def test_returns_error_for_invalid_trace_type(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://server/FeatureServer")

        result = await network_trace(
            starting_global_id="{START-ID}",
            trace_type="invalid",
        )

        assert "error" in result
        assert "invalid" in result["error"]
        # All accepted values should be mentioned
        assert "isolation" in result["error"]
        assert "connected" in result["error"]
        assert "subnetwork" in result["error"]

    async def test_enriches_elements_with_names(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://server/FeatureServer")

        mock_gis = MagicMock()

        with (
            patch.object(traces, "_connect_gis", return_value=mock_gis),
            patch.object(traces, "run_trace", return_value=MOCK_TRACE_RAW),
            patch.object(traces, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = await network_trace(
                starting_global_id="{START-ID}",
                trace_type="connected",
            )

        elements = result["traceResults"]["elements"]
        assert len(elements) == 1
        assert elements[0]["sourceName"] == "ElectricDevice"
        assert elements[0]["assetGroupName"] == "Medium Voltage Transformer"
        assert elements[0]["assetTypeName"] == "Three Phase Padmount"

    async def test_raises_without_service_url(self, monkeypatch) -> None:
        monkeypatch.delenv("UTILITY_NETWORK_URL", raising=False)

        with pytest.raises(ValueError, match="Provide network_service_url"):
            await network_trace(
                starting_global_id="{START-ID}",
                trace_type="isolation",
            )

    async def test_uses_env_var_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://env-server/FeatureServer")

        mock_gis = MagicMock()

        with (
            patch.object(traces, "_connect_gis", return_value=mock_gis),
            patch.object(traces, "run_trace", return_value=MOCK_TRACE_RAW) as mock_run,
            patch.object(traces, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = await network_trace(
                starting_global_id="{START-ID}",
                trace_type="isolation",
            )

        # Verify env var URL was used
        call_args = mock_run.call_args
        assert call_args[0][1] == "https://env-server/FeatureServer"
        assert result["networkServiceUrl"] == "https://env-server/FeatureServer"
