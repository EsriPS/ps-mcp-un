"""Unit tests for _get_layer_metadata and _invalidate_layer_metadata_cache in domain_resolver."""

from unittest.mock import patch

import httpx
import pytest
import respx
from psmcp_router_utilitynetwork.utility_network_service import (
    _cached_layer_metadata,
    _get_layer_metadata,
    _invalidate_layer_metadata_cache,
    resolve_subtype_domains,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_LAYER_URL = "https://server.example.com/arcgis/rest/services/Electric/FeatureServer/0"

SAMPLE_LAYER_METADATA = {
    "id": 0,
    "name": "ElectricDevice",
    "type": "Feature Layer",
    "subtypeField": "assetgroup",
    "types": [
        {
            "id": 10,
            "name": "Switch",
            "domains": {
                "status": {
                    "type": "codedValue",
                    "codedValues": [
                        {"code": 1, "name": "Open"},
                        {"code": 2, "name": "Closed"},
                    ],
                },
            },
        },
    ],
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "assetgroup", "type": "esriFieldTypeInteger"},
        {"name": "status", "type": "esriFieldTypeInteger"},
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the layer metadata cache before and after each test."""
    _cached_layer_metadata.clear()
    yield
    _cached_layer_metadata.clear()


# ---------------------------------------------------------------------------
# Tests: _get_layer_metadata
# ---------------------------------------------------------------------------


class TestGetLayerMetadata:
    """Tests for _get_layer_metadata."""

    @respx.mock
    async def test_fetches_layer_metadata_successfully(self):
        """Successful fetch returns parsed JSON and caches result."""
        route = respx.get(SAMPLE_LAYER_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_LAYER_METADATA)
        )

        result = await _get_layer_metadata(SAMPLE_LAYER_URL, token="test-token-123")

        assert result == SAMPLE_LAYER_METADATA
        assert route.called
        # Verify token was passed as query param
        request = route.calls[0].request
        assert "token=test-token-123" in str(request.url)
        assert "f=json" in str(request.url)

    @respx.mock
    async def test_cache_hit_returns_without_network_request(self):
        """Second call returns cached result without making another request."""
        route = respx.get(SAMPLE_LAYER_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_LAYER_METADATA)
        )

        # First call — fetches from network
        result1 = await _get_layer_metadata(SAMPLE_LAYER_URL, token="tok")
        assert route.call_count == 1

        # Second call — should hit cache
        result2 = await _get_layer_metadata(SAMPLE_LAYER_URL, token="tok")
        assert route.call_count == 1  # No additional request
        assert result2 == result1

    @respx.mock
    async def test_returns_empty_dict_on_http_error(self):
        """HTTP error returns empty dict and logs warning."""
        respx.get(SAMPLE_LAYER_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        result = await _get_layer_metadata(SAMPLE_LAYER_URL, token="tok")

        assert result == {}

    @respx.mock
    async def test_returns_empty_dict_on_network_error(self):
        """Network connectivity error returns empty dict."""
        respx.get(SAMPLE_LAYER_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        result = await _get_layer_metadata(SAMPLE_LAYER_URL, token="tok")

        assert result == {}

    @respx.mock
    async def test_resolved_token_passed_as_query_param(self):
        """The resolved token is included in the request query parameters."""
        route = respx.get(SAMPLE_LAYER_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_LAYER_METADATA)
        )

        with patch(
            "psmcp_router_utilitynetwork.utility_network_service.resolve_token",
            return_value="resolved-token-abc",
        ):
            await _get_layer_metadata(SAMPLE_LAYER_URL, token="input-token")

        request = route.calls[0].request
        assert "token=resolved-token-abc" in str(request.url)

    @respx.mock
    async def test_no_token_param_when_resolve_returns_none(self):
        """When resolve_token returns None, no token param is sent."""
        route = respx.get(SAMPLE_LAYER_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_LAYER_METADATA)
        )

        with patch(
            "psmcp_router_utilitynetwork.utility_network_service.resolve_token",
            return_value=None,
        ):
            await _get_layer_metadata(SAMPLE_LAYER_URL, token=None)

        request = route.calls[0].request
        assert "token=" not in str(request.url)

    @respx.mock
    async def test_trailing_slash_stripped_from_url(self):
        """Trailing slash is removed before fetching and caching."""
        url_with_slash = SAMPLE_LAYER_URL + "/"
        route = respx.get(SAMPLE_LAYER_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_LAYER_METADATA)
        )

        result = await _get_layer_metadata(url_with_slash, token="tok")

        assert result == SAMPLE_LAYER_METADATA
        assert route.called
        # Cache key should be without trailing slash
        assert SAMPLE_LAYER_URL in _cached_layer_metadata
        assert url_with_slash not in _cached_layer_metadata

    @respx.mock
    async def test_failure_does_not_cache(self):
        """Failed fetches do not populate the cache."""
        respx.get(SAMPLE_LAYER_URL).mock(return_value=httpx.Response(404, text="Not Found"))

        result = await _get_layer_metadata(SAMPLE_LAYER_URL, token="tok")

        assert result == {}
        assert SAMPLE_LAYER_URL not in _cached_layer_metadata


# ---------------------------------------------------------------------------
# Tests: _invalidate_layer_metadata_cache
# ---------------------------------------------------------------------------


class TestInvalidateLayerMetadataCache:
    """Tests for _invalidate_layer_metadata_cache."""

    def test_clears_specific_entry(self):
        """Passing a URL clears only that entry."""
        _cached_layer_metadata["https://a/FeatureServer/0"] = {"id": 0}
        _cached_layer_metadata["https://b/FeatureServer/1"] = {"id": 1}

        _invalidate_layer_metadata_cache("https://a/FeatureServer/0")

        assert "https://a/FeatureServer/0" not in _cached_layer_metadata
        assert "https://b/FeatureServer/1" in _cached_layer_metadata

    def test_clears_all_entries_when_no_url(self):
        """Passing None clears the entire cache."""
        _cached_layer_metadata["https://a/FeatureServer/0"] = {"id": 0}
        _cached_layer_metadata["https://b/FeatureServer/1"] = {"id": 1}

        _invalidate_layer_metadata_cache(None)

        assert len(_cached_layer_metadata) == 0

    def test_no_error_when_clearing_nonexistent_url(self):
        """Clearing a URL not in cache does not raise."""
        _cached_layer_metadata["https://a/FeatureServer/0"] = {"id": 0}

        _invalidate_layer_metadata_cache("https://nonexistent/FeatureServer/99")

        # Original entry still present
        assert "https://a/FeatureServer/0" in _cached_layer_metadata

    def test_no_error_when_clearing_empty_cache(self):
        """Clearing an already-empty cache does not raise."""
        _invalidate_layer_metadata_cache(None)
        assert len(_cached_layer_metadata) == 0


# ---------------------------------------------------------------------------
# Test data for edge case tests
# ---------------------------------------------------------------------------

# Layer metadata with subtypes (standard case)
LAYER_WITH_SUBTYPES = {
    "subtypeField": "assetgroup",
    "types": [
        {
            "id": 1,
            "name": "Transformer",
            "domains": {
                "status": {
                    "type": "codedValue",
                    "codedValues": [
                        {"code": 0, "name": "Unknown"},
                        {"code": 1, "name": "Open"},
                        {"code": 2, "name": "Closed"},
                    ],
                },
                "phasecode": {
                    "type": "codedValue",
                    "codedValues": [
                        {"code": 4, "name": "A"},
                        {"code": 2, "name": "B"},
                        {"code": 7, "name": "ABC"},
                    ],
                },
            },
        },
        {
            "id": 2,
            "name": "Switch",
            "domains": {
                "status": {
                    "type": "codedValue",
                    "codedValues": [
                        {"code": 1, "name": "Open"},
                        {"code": 2, "name": "Closed"},
                    ],
                },
            },
        },
    ],
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "assetgroup", "type": "esriFieldTypeInteger"},
        {
            "name": "status",
            "type": "esriFieldTypeInteger",
            "domain": {
                "type": "codedValue",
                "codedValues": [
                    {"code": 0, "name": "Default Unknown"},
                    {"code": 1, "name": "Default Open"},
                    {"code": 2, "name": "Default Closed"},
                    {"code": 3, "name": "Default In Service"},
                ],
            },
        },
        {
            "name": "phasecode",
            "type": "esriFieldTypeInteger",
            "domain": {
                "type": "codedValue",
                "codedValues": [
                    {"code": 4, "name": "Phase A"},
                    {"code": 2, "name": "Phase B"},
                    {"code": 1, "name": "Phase C"},
                    {"code": 7, "name": "Phase ABC"},
                ],
            },
        },
    ],
}

# Layer metadata WITHOUT subtypeField (no subtypes at all)
LAYER_WITHOUT_SUBTYPES = {
    "subtypeField": "",
    "types": [],
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {
            "name": "status",
            "type": "esriFieldTypeInteger",
            "domain": {
                "type": "codedValue",
                "codedValues": [
                    {"code": 1, "name": "Active"},
                    {"code": 2, "name": "Inactive"},
                    {"code": 3, "name": "Retired"},
                ],
            },
        },
        {
            "name": "material",
            "type": "esriFieldTypeInteger",
            "domain": {
                "type": "codedValue",
                "codedValues": [
                    {"code": 10, "name": "Copper"},
                    {"code": 20, "name": "Aluminum"},
                ],
            },
        },
        {"name": "label", "type": "esriFieldTypeString"},
    ],
}


# ---------------------------------------------------------------------------
# Tests: Edge case — missing subtypeField (no subtypes)
# ---------------------------------------------------------------------------


class TestResolveNoSubtypeField:
    """Tests for resolve_subtype_domains when the layer has no subtypeField."""

    def test_uses_default_field_domains_when_no_subtype_field(self):
        """When subtypeField is empty, all features use default field-level domains."""
        features = [
            {"OBJECTID": 1, "status": 1, "material": 10, "label": "Wire A"},
            {"OBJECTID": 2, "status": 2, "material": 20, "label": "Wire B"},
        ]

        result = resolve_subtype_domains(features, LAYER_WITHOUT_SUBTYPES)

        assert result[0]["status"] == {"code": 1, "label": "Active"}
        assert result[0]["material"] == {"code": 10, "label": "Copper"}
        assert result[0]["label"] == "Wire A"  # Non-domain field unchanged

        assert result[1]["status"] == {"code": 2, "label": "Inactive"}
        assert result[1]["material"] == {"code": 20, "label": "Aluminum"}

    def test_uses_default_domains_when_subtype_field_is_none(self):
        """When subtypeField is None (not present in metadata), uses default domains."""
        metadata = {
            "types": [],
            "fields": [
                {
                    "name": "priority",
                    "type": "esriFieldTypeInteger",
                    "domain": {
                        "type": "codedValue",
                        "codedValues": [
                            {"code": 1, "name": "High"},
                            {"code": 2, "name": "Low"},
                        ],
                    },
                },
            ],
        }
        features = [{"OBJECTID": 1, "priority": 1}]

        result = resolve_subtype_domains(features, metadata)

        assert result[0]["priority"] == {"code": 1, "label": "High"}

    def test_unresolvable_codes_left_unchanged_with_no_subtypes(self):
        """Codes not in the default domain are left as raw values."""
        features = [{"OBJECTID": 1, "status": 99, "material": 10}]

        result = resolve_subtype_domains(features, LAYER_WITHOUT_SUBTYPES)

        assert result[0]["status"] == 99  # Code 99 not in domain
        assert result[0]["material"] == {"code": 10, "label": "Copper"}


# ---------------------------------------------------------------------------
# Tests: Edge case — null feature values
# ---------------------------------------------------------------------------


class TestResolveNullFeatureValues:
    """Tests for resolve_subtype_domains with null feature values."""

    def test_null_field_value_left_unchanged(self):
        """When a feature's field value is None, it is left as None (not resolved)."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": None, "phasecode": 7}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        assert result[0]["status"] is None  # Null left unchanged
        assert result[0]["phasecode"] == {"code": 7, "label": "ABC"}

    def test_null_subtype_field_value_falls_back_to_default_domains(self):
        """When a feature's subtype field value is None, fall back to default domains."""
        features = [{"OBJECTID": 1, "assetgroup": None, "status": 2, "phasecode": 4}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Should use default field-level domains
        assert result[0]["status"] == {"code": 2, "label": "Default Closed"}
        assert result[0]["phasecode"] == {"code": 4, "label": "Phase A"}

    def test_all_null_fields_returns_feature_unchanged(self):
        """Feature with all None values is returned unchanged (no crash)."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": None, "phasecode": None}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        assert result[0]["status"] is None
        assert result[0]["phasecode"] is None
        assert result[0]["OBJECTID"] == 1

    def test_empty_features_list_returns_empty(self):
        """Empty features list returns empty list without error."""
        result = resolve_subtype_domains([], LAYER_WITH_SUBTYPES)
        assert result == []

    def test_empty_metadata_returns_features_unchanged(self):
        """Empty metadata dict returns features unchanged."""
        features = [{"OBJECTID": 1, "status": 1}]
        result = resolve_subtype_domains(features, {})
        assert result == features


# ---------------------------------------------------------------------------
# Tests: Edge case — unknown subtype codes
# ---------------------------------------------------------------------------


class TestResolveUnknownSubtypeCodes:
    """Tests for resolve_subtype_domains with unknown subtype codes."""

    def test_unknown_subtype_code_falls_back_to_default_domains(self):
        """Feature with subtype code not in types[] uses default field-level domains."""
        # Subtype code 99 doesn't exist — only 1 (Transformer) and 2 (Switch) are defined
        features = [{"OBJECTID": 1, "assetgroup": 99, "status": 2, "phasecode": 4}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Should resolve using default field domains
        assert result[0]["status"] == {"code": 2, "label": "Default Closed"}
        assert result[0]["phasecode"] == {"code": 4, "label": "Phase A"}

    def test_known_and_unknown_subtypes_in_same_batch(self):
        """Mix of known and unknown subtypes: known uses subtype domain, unknown uses default."""
        features = [
            {"OBJECTID": 1, "assetgroup": 1, "status": 1},  # Known — Transformer
            {"OBJECTID": 2, "assetgroup": 99, "status": 1},  # Unknown subtype
        ]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Feature 1: uses subtype-specific domain (Transformer domain)
        assert result[0]["status"] == {"code": 1, "label": "Open"}
        # Feature 2: falls back to default domain
        assert result[1]["status"] == {"code": 1, "label": "Default Open"}

    def test_unknown_subtype_with_code_not_in_default_domain(self):
        """Unknown subtype + code not in default domain leaves value unchanged."""
        features = [{"OBJECTID": 1, "assetgroup": 99, "status": 999}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Code 999 not in default domain either — left unchanged
        assert result[0]["status"] == 999

    def test_does_not_mutate_original_features(self):
        """Resolution creates new dicts; original list is not modified."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 2}]
        original_feature = dict(features[0])

        resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        assert features[0] == original_feature  # Original unchanged


# ---------------------------------------------------------------------------
# Tests: Standard subtype domain resolution
# ---------------------------------------------------------------------------


class TestResolveSubtypeDomains:
    """Tests for resolve_subtype_domains with known subtype codes."""

    def test_known_subtype_resolves_fields_using_subtype_domains(self):
        """Feature with known subtype code uses subtype-specific domain for resolution."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 2, "phasecode": 7}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Subtype 1 (Transformer) has its own domains for status and phasecode
        assert result[0]["status"] == {"code": 2, "label": "Closed"}
        assert result[0]["phasecode"] == {"code": 7, "label": "ABC"}

    def test_fields_without_domain_for_subtype_left_unchanged(self):
        """Fields that have no domain mapping for the subtype are left as-is."""
        # Subtype 2 (Switch) only has domain for "status", NOT "phasecode"
        features = [{"OBJECTID": 1, "assetgroup": 2, "status": 1, "phasecode": 4}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # status resolved via Switch's domain
        assert result[0]["status"] == {"code": 1, "label": "Open"}
        # phasecode: Switch has no subtype-specific domain for it,
        # but the field-level default domain exists — so it uses the default
        assert result[0]["phasecode"] == {"code": 4, "label": "Phase A"}

    def test_subtype_field_itself_not_resolved(self):
        """The subtype field (assetgroup) stays as the raw integer, never resolved."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 2}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # assetgroup should remain the raw integer
        assert result[0]["assetgroup"] == 1
        assert not isinstance(result[0]["assetgroup"], dict)

    def test_multiple_features_different_subtypes_in_same_batch(self):
        """Multiple features with different subtypes resolve using their own domains."""
        features = [
            {"OBJECTID": 1, "assetgroup": 1, "status": 1},  # Transformer
            {"OBJECTID": 2, "assetgroup": 2, "status": 1},  # Switch
        ]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Transformer: status domain has code 1 → "Open"
        assert result[0]["status"] == {"code": 1, "label": "Open"}
        # Switch: status domain has code 1 → "Open" (same label, different domain source)
        assert result[1]["status"] == {"code": 1, "label": "Open"}

    def test_multiple_features_different_subtypes_different_labels(self):
        """Different subtypes can map the same code to different labels."""
        # Transformer has code 0 → "Unknown" in status domain
        # Switch does NOT have code 0 in its status domain — value left unchanged
        features = [
            {"OBJECTID": 1, "assetgroup": 1, "status": 0},  # Transformer
            {"OBJECTID": 2, "assetgroup": 2, "status": 0},  # Switch
        ]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # Transformer: has code 0 → "Unknown"
        assert result[0]["status"] == {"code": 0, "label": "Unknown"}
        # Switch: has a subtype domain for "status" but it doesn't include code 0,
        # so the value stays as the raw integer (no fallback to default domain)
        assert result[1]["status"] == 0


# ---------------------------------------------------------------------------
# Tests: Standalone tool network_resolve_coded_values
# ---------------------------------------------------------------------------


class TestNetworkResolveCodedValues:
    """Tests for the network_resolve_coded_values tool wrapper."""

    @patch("psmcp_router_utilitynetwork.utility_network_service._get_layer_metadata")
    async def test_returns_expected_dict_structure(self, mock_get_metadata):
        """Tool returns dict with features, featureCount, layerUrl, resolvedFields keys."""
        from psmcp_router_utilitynetwork.utility_network_service import network_resolve_coded_values

        mock_get_metadata.return_value = LAYER_WITH_SUBTYPES
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 2, "phasecode": 7}]

        result = await network_resolve_coded_values(
            features=features,
            layer_url="https://example.com/FeatureServer/0",
            token="test-token",
        )

        assert "features" in result
        assert "featureCount" in result
        assert "layerUrl" in result
        assert "resolvedFields" in result
        assert result["featureCount"] == 1
        assert result["layerUrl"] == "https://example.com/FeatureServer/0"
        assert isinstance(result["resolvedFields"], list)
        assert "status" in result["resolvedFields"]
        assert "phasecode" in result["resolvedFields"]

    @patch("psmcp_router_utilitynetwork.utility_network_service._get_layer_metadata")
    async def test_resolves_features_correctly(self, mock_get_metadata):
        """Tool resolves coded values using layer metadata."""
        from psmcp_router_utilitynetwork.utility_network_service import network_resolve_coded_values

        mock_get_metadata.return_value = LAYER_WITH_SUBTYPES
        features = [
            {"OBJECTID": 1, "assetgroup": 1, "status": 1, "phasecode": 4},
            {"OBJECTID": 2, "assetgroup": 2, "status": 2},
        ]

        result = await network_resolve_coded_values(
            features=features,
            layer_url="https://example.com/FeatureServer/0",
            token="tok",
        )

        assert result["features"][0]["status"] == {"code": 1, "label": "Open"}
        assert result["features"][0]["phasecode"] == {"code": 4, "label": "A"}
        assert result["features"][1]["status"] == {"code": 2, "label": "Closed"}
        assert result["featureCount"] == 2

    @patch("psmcp_router_utilitynetwork.utility_network_service._get_layer_metadata")
    async def test_returns_unchanged_features_with_warning_on_metadata_failure(
        self, mock_get_metadata
    ):
        """When _get_layer_metadata returns empty dict, features returned unchanged."""
        from psmcp_router_utilitynetwork.utility_network_service import network_resolve_coded_values

        mock_get_metadata.return_value = {}
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 2}]

        result = await network_resolve_coded_values(
            features=features,
            layer_url="https://example.com/FeatureServer/0",
            token="tok",
        )

        assert result["features"] == features
        assert result["featureCount"] == 1
        assert result["resolvedFields"] == []
        assert "warning" in result
        assert "Could not fetch layer metadata" in result["warning"]


# ---------------------------------------------------------------------------
# Tests: Output structure verification ({code, label} format)
# ---------------------------------------------------------------------------


class TestOutputStructureVerification:
    """Tests verifying resolved values have exactly {code: int, label: str} structure."""

    def test_resolved_value_has_code_and_label_keys(self):
        """Resolved coded value contains exactly 'code' and 'label' keys."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 2}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        resolved_status = result[0]["status"]
        assert isinstance(resolved_status, dict)
        assert set(resolved_status.keys()) == {"code", "label"}

    def test_resolved_code_is_int_and_label_is_str(self):
        """The 'code' value is int and 'label' value is str."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 1, "phasecode": 7}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        status = result[0]["status"]
        assert isinstance(status["code"], int)
        assert isinstance(status["label"], str)

        phasecode = result[0]["phasecode"]
        assert isinstance(phasecode["code"], int)
        assert isinstance(phasecode["label"], str)

    def test_unresolved_values_not_wrapped_in_dict(self):
        """Values that cannot be resolved remain as raw values, NOT wrapped in {code, label}."""
        # Code 999 doesn't exist in any domain
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 999}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        # status with unknown code stays as raw int
        assert result[0]["status"] == 999
        assert not isinstance(result[0]["status"], dict)

    def test_non_domain_fields_not_wrapped(self):
        """Fields without any domain (e.g., OBJECTID, string fields) are never wrapped."""
        features = [{"OBJECTID": 42, "assetgroup": 1, "status": 1, "label": "My Device"}]

        # Add a string field "label" that has no domain
        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        assert result[0]["OBJECTID"] == 42
        assert not isinstance(result[0]["OBJECTID"], dict)
        assert result[0]["label"] == "My Device"
        assert not isinstance(result[0]["label"], dict)

    def test_multiple_resolved_fields_all_have_correct_structure(self):
        """When multiple fields are resolved, each has the {code, label} structure."""
        features = [{"OBJECTID": 1, "assetgroup": 1, "status": 0, "phasecode": 2}]

        result = resolve_subtype_domains(features, LAYER_WITH_SUBTYPES)

        for field_name in ("status", "phasecode"):
            value = result[0][field_name]
            assert isinstance(value, dict), f"{field_name} should be a dict"
            assert "code" in value, f"{field_name} missing 'code' key"
            assert "label" in value, f"{field_name} missing 'label' key"
            assert isinstance(value["code"], int), f"{field_name}.code should be int"
            assert isinstance(value["label"], str), f"{field_name}.label should be str"
