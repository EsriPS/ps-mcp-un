"""Tests for the utility network associations query tool and helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from psmcp_router_utilitynetwork import utility_network_service as associations
from psmcp_router_utilitynetwork.utility_network_service import (
    _build_source_lookup,
    _build_terminal_lookup,
    _query_associations_sync,
    _resolve_feature_identity,
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

MOCK_ASSOCIATIONS_RESPONSE = {
    "associations": [
        {
            "associationType": 1,
            "fromNetworkSourceId": 9,
            "fromAssetGroupCode": 4,
            "fromAssetTypeCode": 12,
            "fromTerminalId": 2,
            "fromGlobalId": "{AAAA-BBBB-CCCC}",
            "toNetworkSourceId": 11,
            "toAssetGroupCode": 2,
            "toAssetTypeCode": 1,
            "toTerminalId": None,
            "toGlobalId": "{DDDD-EEEE-FFFF}",
            "toPercentAlong": 0.5,
        },
        {
            "associationType": 2,
            "fromNetworkSourceId": 9,
            "fromAssetGroupCode": 4,
            "fromAssetTypeCode": 12,
            "fromTerminalId": None,
            "fromGlobalId": "{AAAA-BBBB-CCCC}",
            "toNetworkSourceId": 9,
            "toAssetGroupCode": 4,
            "toAssetTypeCode": 12,
            "toTerminalId": None,
            "toGlobalId": "{GGGG-HHHH-IIII}",
            "isContentVisible": True,
        },
    ]
}


# ---------------------------------------------------------------------------
# Tests for _build_source_lookup
# ---------------------------------------------------------------------------


class TestBuildSourceLookup:
    def test_maps_source_id_to_metadata(self) -> None:
        lookup = _build_source_lookup(MOCK_DATA_ELEMENT)

        assert 9 in lookup
        assert lookup[9]["sourceName"] == "ElectricDevice"
        assert lookup[9]["sourceType"] == "junction"
        assert lookup[9]["domainNetworkName"] == "ElectricDistribution"

    def test_maps_edge_source_correctly(self) -> None:
        lookup = _build_source_lookup(MOCK_DATA_ELEMENT)

        assert 11 in lookup
        assert lookup[11]["sourceName"] == "ElectricLine"
        assert lookup[11]["sourceType"] == "edge"
        assert lookup[11]["domainNetworkName"] == "ElectricDistribution"

    def test_includes_asset_group_lookup(self) -> None:
        lookup = _build_source_lookup(MOCK_DATA_ELEMENT)

        asset_groups = lookup[9]["assetGroups"]
        assert 4 in asset_groups
        assert asset_groups[4]["assetGroupName"] == "Medium Voltage Transformer"

    def test_includes_asset_type_lookup(self) -> None:
        lookup = _build_source_lookup(MOCK_DATA_ELEMENT)

        asset_types = lookup[9]["assetGroups"][4]["assetTypes"]
        assert 12 in asset_types
        assert asset_types[12] == "Three Phase Padmount"

    def test_handles_empty_data_element(self) -> None:
        lookup = _build_source_lookup({"domainNetworks": []})

        assert lookup == {}

    def test_handles_missing_domain_networks_key(self) -> None:
        lookup = _build_source_lookup({})

        assert lookup == {}


# ---------------------------------------------------------------------------
# Tests for _build_terminal_lookup
# ---------------------------------------------------------------------------


class TestBuildTerminalLookup:
    def test_maps_terminal_id_to_name(self) -> None:
        lookup = _build_terminal_lookup(MOCK_DATA_ELEMENT)

        assert lookup[1] == "High"
        assert lookup[2] == "Low"

    def test_handles_empty_terminal_configurations(self) -> None:
        lookup = _build_terminal_lookup({"terminalConfigurations": []})

        assert lookup == {}

    def test_handles_missing_terminal_configurations_key(self) -> None:
        lookup = _build_terminal_lookup({})

        assert lookup == {}

    def test_handles_multiple_configurations(self) -> None:
        data_element = {
            "terminalConfigurations": [
                {
                    "terminalConfigurationId": 1,
                    "terminalConfigurationName": "Config A",
                    "terminals": [
                        {"terminalId": 10, "terminalName": "Source"},
                        {"terminalId": 11, "terminalName": "Load"},
                    ],
                },
                {
                    "terminalConfigurationId": 2,
                    "terminalConfigurationName": "Config B",
                    "terminals": [
                        {"terminalId": 20, "terminalName": "Input"},
                    ],
                },
            ]
        }
        lookup = _build_terminal_lookup(data_element)

        assert lookup[10] == "Source"
        assert lookup[11] == "Load"
        assert lookup[20] == "Input"


# ---------------------------------------------------------------------------
# Tests for _resolve_feature_identity
# ---------------------------------------------------------------------------


class TestResolveFeatureIdentity:
    @pytest.fixture()
    def lookups(self):
        source_lookup = _build_source_lookup(MOCK_DATA_ELEMENT)
        terminal_lookup = _build_terminal_lookup(MOCK_DATA_ELEMENT)
        return source_lookup, terminal_lookup

    def test_resolves_from_feature_with_terminal(self, lookups) -> None:
        source_lookup, terminal_lookup = lookups
        record = MOCK_ASSOCIATIONS_RESPONSE["associations"][0]

        identity = _resolve_feature_identity(record, "from", source_lookup, terminal_lookup)

        assert identity["globalId"] == "{AAAA-BBBB-CCCC}"
        assert identity["networkSourceId"] == 9
        assert identity["sourceName"] == "ElectricDevice"
        assert identity["assetGroupCode"] == 4
        assert identity["assetGroupName"] == "Medium Voltage Transformer"
        assert identity["assetTypeCode"] == 12
        assert identity["assetTypeName"] == "Three Phase Padmount"
        assert identity["terminalId"] == 2
        assert identity["terminalName"] == "Low"

    def test_resolves_to_feature_without_terminal(self, lookups) -> None:
        source_lookup, terminal_lookup = lookups
        record = MOCK_ASSOCIATIONS_RESPONSE["associations"][0]

        identity = _resolve_feature_identity(record, "to", source_lookup, terminal_lookup)

        assert identity["globalId"] == "{DDDD-EEEE-FFFF}"
        assert identity["networkSourceId"] == 11
        assert identity["sourceName"] == "ElectricLine"
        assert identity["assetGroupCode"] == 2
        assert identity["assetGroupName"] == "Medium Voltage"
        assert identity["assetTypeCode"] == 1
        assert identity["assetTypeName"] == "Underground Single Phase"
        # No terminal fields when terminalId is None
        assert "terminalId" not in identity
        assert "terminalName" not in identity

    def test_handles_unknown_source_id(self) -> None:
        source_lookup = _build_source_lookup(MOCK_DATA_ELEMENT)
        terminal_lookup = _build_terminal_lookup(MOCK_DATA_ELEMENT)
        record = {
            "fromNetworkSourceId": 999,
            "fromAssetGroupCode": 1,
            "fromAssetTypeCode": 1,
            "fromTerminalId": None,
            "fromGlobalId": "{UNKNOWN}",
        }

        identity = _resolve_feature_identity(record, "from", source_lookup, terminal_lookup)

        assert identity["globalId"] == "{UNKNOWN}"
        assert identity["networkSourceId"] == 999
        assert identity["sourceName"] == ""
        assert identity["assetGroupName"] == ""
        assert identity["assetTypeName"] == ""


# ---------------------------------------------------------------------------
# Tests for _query_associations_sync
# ---------------------------------------------------------------------------


class TestQueryAssociationsSync:
    @pytest.fixture()
    def mock_gis(self):
        """Create a mock GIS instance with a _con.post() method."""
        gis = MagicMock()
        gis._con = MagicMock()
        return gis

    def test_resolves_association_types_to_names(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        assocs = result["associations"]
        assert assocs[0]["associationType"] == "connectivity"
        assert assocs[1]["associationType"] == "containment"

    def test_resolves_source_names(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        first_assoc = result["associations"][0]
        assert first_assoc["fromFeature"]["sourceName"] == "ElectricDevice"
        assert first_assoc["toFeature"]["sourceName"] == "ElectricLine"

    def test_resolves_asset_group_and_type_names(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        from_feature = result["associations"][0]["fromFeature"]
        assert from_feature["assetGroupName"] == "Medium Voltage Transformer"
        assert from_feature["assetTypeName"] == "Three Phase Padmount"

        to_feature = result["associations"][0]["toFeature"]
        assert to_feature["assetGroupName"] == "Medium Voltage"
        assert to_feature["assetTypeName"] == "Underground Single Phase"

    def test_resolves_terminal_names(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        from_feature = result["associations"][0]["fromFeature"]
        assert from_feature["terminalId"] == 2
        assert from_feature["terminalName"] == "Low"

    def test_preserves_containment_is_content_visible(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        containment_assoc = result["associations"][1]
        assert containment_assoc["associationType"] == "containment"
        assert containment_assoc["isContentVisible"] is True

    def test_preserves_percent_along(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        connectivity_assoc = result["associations"][0]
        assert connectivity_assoc["toPercentAlong"] == 0.5

    def test_handles_error_response(self, mock_gis) -> None:
        mock_gis._con.post.return_value = {"error": {"code": 400, "message": "Invalid global ID"}}

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{BAD-ID}",
                None,
                None,
            )

        assert "error" in result
        assert "Invalid global ID" in result["error"]
        assert result["globalId"] == "{BAD-ID}"

    def test_returns_correct_association_count(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        assert result["associationCount"] == 2
        assert result["globalId"] == "{AAAA-BBBB-CCCC}"
        assert result["serviceUrl"] == "https://server/UN/FeatureServer"

    def test_containment_assoc_does_not_have_percent_along(self, mock_gis) -> None:
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

        containment_assoc = result["associations"][1]
        assert "toPercentAlong" not in containment_assoc
        assert "fromPercentAlong" not in containment_assoc


# ---------------------------------------------------------------------------
# Tests for the async network_query_associations tool
# ---------------------------------------------------------------------------


class TestNetworkQueryAssociations:
    async def test_raises_value_error_when_no_service_url(self, monkeypatch) -> None:
        monkeypatch.delenv("UTILITY_NETWORK_URL", raising=False)

        with pytest.raises(ValueError, match="Provide network_service_url"):
            await associations.network_query_associations(
                global_id="{AAAA-BBBB-CCCC}",
            )

    async def test_uses_env_var_when_no_url_provided(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://env-server/UN/FeatureServer")

        mock_gis = MagicMock()
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            result = await associations.network_query_associations(
                global_id="{AAAA-BBBB-CCCC}",
            )

        assert result["serviceUrl"] == "https://env-server/UN/FeatureServer"
        assert result["associationCount"] == 2

    async def test_delegates_to_sync_implementation(self, monkeypatch) -> None:
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://server/UN/FeatureServer")

        expected_result = {
            "globalId": "{TEST}",
            "associations": [],
            "associationCount": 0,
            "serviceUrl": "https://server/UN/FeatureServer",
        }

        with patch.object(
            associations, "_query_associations_sync", return_value=expected_result
        ) as mock_sync:
            result = await associations.network_query_associations(
                global_id="{TEST}",
                association_types=["connectivity"],
            )

        mock_sync.assert_called_once_with(
            "https://server/UN/FeatureServer",
            "{TEST}",
            ["connectivity"],
            None,
        )
        assert result is expected_result


# ---------------------------------------------------------------------------
# Tests for code resolution completeness (no raw numeric codes in output)
# ---------------------------------------------------------------------------


class TestNoUnresolvedNumericCodes:
    """Verify that when data element provides mappings, output has no raw codes without names."""

    @pytest.fixture()
    def result(self):
        """Call _query_associations_sync with full mock data and return the result."""
        mock_gis = MagicMock()
        mock_gis._con.post.return_value = MOCK_ASSOCIATIONS_RESPONSE

        with (
            patch.object(associations, "_connect_gis", return_value=mock_gis),
            patch.object(associations, "_get_data_element", return_value=MOCK_DATA_ELEMENT),
        ):
            return _query_associations_sync(
                "https://server/UN/FeatureServer",
                "{AAAA-BBBB-CCCC}",
                None,
                None,
            )

    def test_all_source_ids_have_resolved_names(self, result) -> None:
        """Every networkSourceId in output must have a non-empty sourceName."""
        for assoc in result["associations"]:
            for side in ("fromFeature", "toFeature"):
                feature = assoc[side]
                if feature.get("networkSourceId") is not None:
                    assert "sourceName" in feature
                    assert isinstance(feature["sourceName"], str)
                    assert len(feature["sourceName"]) > 0, (
                        f"sourceName is empty for networkSourceId={feature['networkSourceId']}"
                    )

    def test_all_asset_codes_have_resolved_names(self, result) -> None:
        """Every assetGroupCode/assetTypeCode must have non-empty resolved names."""
        for assoc in result["associations"]:
            for side in ("fromFeature", "toFeature"):
                feature = assoc[side]
                if feature.get("assetGroupCode") is not None:
                    assert "assetGroupName" in feature
                    assert isinstance(feature["assetGroupName"], str)
                    assert len(feature["assetGroupName"]) > 0, (
                        f"assetGroupName is empty for assetGroupCode={feature['assetGroupCode']}"
                    )
                if feature.get("assetTypeCode") is not None:
                    assert "assetTypeName" in feature
                    assert isinstance(feature["assetTypeName"], str)
                    assert len(feature["assetTypeName"]) > 0, (
                        f"assetTypeName is empty for assetTypeCode={feature['assetTypeCode']}"
                    )

    def test_all_terminal_ids_have_resolved_names(self, result) -> None:
        """Every terminal with a terminalId must have a non-empty terminalName."""
        for assoc in result["associations"]:
            for side in ("fromFeature", "toFeature"):
                feature = assoc[side]
                if feature.get("terminalId") is not None:
                    assert "terminalName" in feature
                    assert isinstance(feature["terminalName"], str)
                    assert len(feature["terminalName"]) > 0, (
                        f"terminalName is empty for terminalId={feature['terminalId']}"
                    )

    def test_association_type_is_string_not_int(self, result) -> None:
        """associationType field must always be a string name, not an integer code."""
        for assoc in result["associations"]:
            assert "associationType" in assoc
            assert isinstance(assoc["associationType"], str), (
                f"associationType should be str, got {type(assoc['associationType'])}"
            )
            # Should be a known name, not a stringified integer
            assert assoc["associationType"] in (
                "connectivity",
                "containment",
                "structuralAttachment",
            ), f"Unexpected associationType value: {assoc['associationType']}"
