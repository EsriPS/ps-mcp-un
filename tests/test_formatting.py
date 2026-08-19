"""Unit tests for the formatting helpers in psmcp_router_utilitynetwork.formatting."""

from psmcp_router_utilitynetwork.utility_network_service import (
    format_customer_impact,
    resolve_phase_domain,
    summarize_trace_results,
    truncate_results,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_TRACE_ELEMENTS = [
    {
        "networkSourceId": 9,
        "globalId": "{E1}",
        "objectId": 1,
        "assetGroupCode": 4,
        "assetTypeCode": 12,
        "sourceName": "ElectricDevice",
        "assetGroupName": "Medium Voltage Transformer",
        "assetTypeName": "Three Phase Padmount",
    },
    {
        "networkSourceId": 9,
        "globalId": "{E2}",
        "objectId": 2,
        "assetGroupCode": 4,
        "assetTypeCode": 12,
        "sourceName": "ElectricDevice",
        "assetGroupName": "Medium Voltage Transformer",
        "assetTypeName": "Three Phase Padmount",
    },
    {
        "networkSourceId": 9,
        "globalId": "{E3}",
        "objectId": 3,
        "assetGroupCode": 5,
        "assetTypeCode": 1,
        "sourceName": "ElectricDevice",
        "assetGroupName": "Subnetwork Controller",
        "assetTypeName": "Circuit Breaker",
    },
    {
        "networkSourceId": 11,
        "globalId": "{E4}",
        "objectId": 4,
        "assetGroupCode": 2,
        "assetTypeCode": 1,
        "sourceName": "ElectricLine",
        "assetGroupName": "Medium Voltage",
        "assetTypeName": "Underground Single Phase",
    },
    {
        "networkSourceId": 11,
        "globalId": "{E5}",
        "objectId": 5,
        "assetGroupCode": 2,
        "assetTypeCode": 1,
        "sourceName": "ElectricLine",
        "assetGroupName": "Medium Voltage",
        "assetTypeName": "Underground Single Phase",
    },
    {
        "networkSourceId": 11,
        "globalId": "{E6}",
        "objectId": 6,
        "assetGroupCode": 2,
        "assetTypeCode": 2,
        "sourceName": "ElectricLine",
        "assetGroupName": "Medium Voltage",
        "assetTypeName": "Overhead Three Phase",
    },
]

SAMPLE_CUSTOMERS = [
    {
        "meter_id": "M001",
        "account_number": "A001",
        "service_address": "123 Main St",
        "connected_load": 5.5,
        "phase": 7,
    },
    {
        "meter_id": "M002",
        "account_number": "A002",
        "service_address": "456 Oak Ave",
        "connected_load": 3.2,
        "phase": 4,
    },
    {
        "meter_id": "M003",
        "account_number": "A003",
        "service_address": "789 Pine Rd",
        "connected_load": 4.0,
        "phase": 2,
    },
    {
        "meter_id": "M004",
        "account_number": "A004",
        "service_address": "101 Elm Dr",
        "connected_load": 6.1,
        "phase": 7,
    },
]


# ---------------------------------------------------------------------------
# TestSummarizeTraceResults
# ---------------------------------------------------------------------------


class TestSummarizeTraceResults:
    """Tests for summarize_trace_results."""

    def test_groups_elements_by_source_and_asset_group(self):
        """Verify correct grouping and counts by sourceName + assetGroupName."""
        raw = {"traceResults": {"elements": SAMPLE_TRACE_ELEMENTS}}
        result = summarize_trace_results(raw)

        assert result["totalElements"] == 6

        # Should have 3 groups: ElectricLine/Medium Voltage (3),
        # ElectricDevice/Medium Voltage Transformer (2),
        # ElectricDevice/Subnetwork Controller (1)
        groups = result["groups"]
        assert len(groups) == 3

        # Find each group by name
        group_map = {(g["sourceName"], g["assetGroupName"]): g for g in groups}
        assert group_map[("ElectricLine", "Medium Voltage")]["count"] == 3
        assert group_map[("ElectricDevice", "Medium Voltage Transformer")]["count"] == 2
        assert group_map[("ElectricDevice", "Subnetwork Controller")]["count"] == 1

    def test_groups_sorted_by_count_descending(self):
        """Highest count group should be first."""
        raw = {"traceResults": {"elements": SAMPLE_TRACE_ELEMENTS}}
        result = summarize_trace_results(raw)

        groups = result["groups"]
        counts = [g["count"] for g in groups]
        assert counts == sorted(counts, reverse=True)

    def test_asset_types_counted_within_groups(self):
        """Sub-counts per assetTypeName within each group."""
        raw = {"traceResults": {"elements": SAMPLE_TRACE_ELEMENTS}}
        result = summarize_trace_results(raw)

        groups = result["groups"]
        # ElectricLine/Medium Voltage has 2 Underground Single Phase + 1 Overhead Three Phase
        line_group = next(
            g for g in groups if g["assetGroupName"] == "Medium Voltage"
        )
        type_map = {at["name"]: at["count"] for at in line_group["assetTypes"]}
        assert type_map["Underground Single Phase"] == 2
        assert type_map["Overhead Three Phase"] == 1

    def test_identifies_controllers(self):
        """Elements with 'Controller' in group/type name are identified."""
        raw = {"traceResults": {"elements": SAMPLE_TRACE_ELEMENTS}}
        result = summarize_trace_results(raw)

        controllers = result["controllers"]
        assert len(controllers) == 1
        assert controllers[0]["globalId"] == "{E3}"
        assert controllers[0]["assetGroupName"] == "Subnetwork Controller"

    def test_handles_empty_elements(self):
        """Empty list returns zero counts and empty structures."""
        raw = {"traceResults": {"elements": []}}
        result = summarize_trace_results(raw)

        assert result["totalElements"] == 0
        assert result["groups"] == []
        assert result["controllers"] == []
        assert result["elements"] == []
        assert result["truncated"] is False

    def test_truncates_when_exceeds_limit(self):
        """With limit=3, only 3 elements returned and truncated is True."""
        raw = {"traceResults": {"elements": SAMPLE_TRACE_ELEMENTS}}
        result = summarize_trace_results(raw, limit=3)

        assert result["totalElements"] == 6
        assert len(result["elements"]) == 3
        assert result["truncated"] is True
        assert "note" in result
        assert "3 of 6" in result["note"]

    def test_uses_source_mapping_fallback(self):
        """When sourceName is empty, uses source_mapping for lookup."""
        elements = [
            {
                "networkSourceId": 9,
                "globalId": "{X1}",
                "objectId": 100,
                "assetGroupCode": 1,
                "assetTypeCode": 1,
                "sourceName": "",
                "assetGroupName": "Switch",
                "assetTypeName": "Disconnect",
            },
        ]
        raw = {"traceResults": {"elements": elements}}
        source_mapping = {"9": "ElectricDevice"}

        result = summarize_trace_results(raw, source_mapping=source_mapping)

        groups = result["groups"]
        assert len(groups) == 1
        assert groups[0]["sourceName"] == "ElectricDevice"

    def test_no_raw_numeric_codes_in_output(self):
        """Verify all group names are strings and not raw numeric codes."""
        raw = {"traceResults": {"elements": SAMPLE_TRACE_ELEMENTS}}
        result = summarize_trace_results(raw)

        for group in result["groups"]:
            assert isinstance(group["sourceName"], str)
            assert isinstance(group["assetGroupName"], str)
            # Should not be purely numeric
            assert not group["sourceName"].isdigit()
            assert not group["assetGroupName"].isdigit()
            for at in group["assetTypes"]:
                assert isinstance(at["name"], str)
                assert not at["name"].isdigit()


# ---------------------------------------------------------------------------
# TestFormatCustomerImpact
# ---------------------------------------------------------------------------


class TestFormatCustomerImpact:
    """Tests for format_customer_impact."""

    def test_counts_customers(self):
        """customerCount matches input length."""
        result = format_customer_impact(SAMPLE_CUSTOMERS)
        assert result["customerCount"] == 4

    def test_sums_load(self):
        """totalLoad is sum of load_field values when field specified."""
        result = format_customer_impact(SAMPLE_CUSTOMERS, load_field="connected_load")
        expected = 5.5 + 3.2 + 4.0 + 6.1
        assert abs(result["totalLoad"] - expected) < 0.001

    def test_phase_breakdown_from_bitfield(self):
        """Correct label mapping when phase_domain provided."""
        phase_domain = {7: "ABC", 4: "A", 2: "B", 1: "C"}
        result = format_customer_impact(SAMPLE_CUSTOMERS, phase_domain=phase_domain)
        breakdown = result["phaseBreakdown"]
        assert breakdown["ABC"] == 2  # M001, M004
        assert breakdown["A"] == 1  # M002
        assert breakdown["B"] == 1  # M003

    def test_uses_provided_phases_dict(self):
        """When phases param given, uses it directly."""
        custom_phases = {"A": 10, "B": 5, "C": 3}
        result = format_customer_impact(SAMPLE_CUSTOMERS, phases=custom_phases)
        assert result["phaseBreakdown"] == custom_phases

    def test_handles_empty_customers(self):
        """Zero count, zero load for empty input."""
        result = format_customer_impact([])
        assert result["customerCount"] == 0
        assert result["totalLoad"] == 0.0
        assert result["phaseBreakdown"] == {}

    def test_no_load_when_field_not_specified(self):
        """totalLoad is 0.0 when load_field is not provided."""
        customers = [
            {"meter_id": "M100", "phase": 4},
            {"meter_id": "M101", "phase": 2},
        ]
        result = format_customer_impact(customers)
        assert result["totalLoad"] == 0.0

    def test_uses_explicit_load_field(self):
        """Sums values from the specified load_field."""
        customers = [
            {"meter_id": "M1", "demand_kw": 10.0, "phase": 4},
            {"meter_id": "M2", "demand_kw": 5.0, "phase": 2},
        ]
        result = format_customer_impact(customers, load_field="demand_kw")
        assert abs(result["totalLoad"] - 15.0) < 0.001

    def test_custom_phase_field(self):
        """Uses specified phase_field instead of default 'phase'."""
        customers = [
            {"meter_id": "M1", "phases_current": 7},
            {"meter_id": "M2", "phases_current": 4},
        ]
        phase_domain = {7: "ABC", 4: "A"}
        result = format_customer_impact(
            customers, phase_domain=phase_domain, phase_field="phases_current"
        )
        assert result["phaseBreakdown"]["ABC"] == 1
        assert result["phaseBreakdown"]["A"] == 1

    def test_fallback_uses_default_labels_without_phase_domain(self):
        """When no phase_domain provided, uses default labels."""
        result = format_customer_impact(SAMPLE_CUSTOMERS)
        breakdown = result["phaseBreakdown"]
        assert breakdown["ABC"] == 2
        assert breakdown["A"] == 1
        assert breakdown["B"] == 1


# ---------------------------------------------------------------------------
# TestTruncateResults
# ---------------------------------------------------------------------------


class TestTruncateResults:
    """Tests for truncate_results."""

    def test_no_truncation_when_within_limit(self):
        """Returns all items, truncated=False, no note."""
        items = [1, 2, 3, 4, 5]
        result = truncate_results(items, limit=10)

        assert result["items"] == items
        assert result["total"] == 5
        assert result["truncated"] is False
        assert "note" not in result

    def test_truncates_when_exceeds_limit(self):
        """Returns first N items, truncated=True, note present."""
        items = list(range(20))
        result = truncate_results(items, limit=5)

        assert result["items"] == [0, 1, 2, 3, 4]
        assert result["total"] == 20
        assert result["truncated"] is True
        assert "note" in result

    def test_note_format(self):
        """Note says 'showing N of M {label}'."""
        items = list(range(100))
        result = truncate_results(items, limit=10, label="features")

        assert result["note"] == "showing 10 of 100 features"

    def test_custom_label(self):
        """Label appears in note."""
        items = list(range(50))
        result = truncate_results(items, limit=5, label="customers")

        assert "customers" in result["note"]

    def test_exact_limit_not_truncated(self):
        """len(items) == limit → no truncation."""
        items = list(range(10))
        result = truncate_results(items, limit=10)

        assert result["items"] == items
        assert result["total"] == 10
        assert result["truncated"] is False
        assert "note" not in result


# ---------------------------------------------------------------------------
# TestResolvePhaseDomain
# ---------------------------------------------------------------------------


class TestResolvePhaseDomain:
    """Tests for resolve_phase_domain."""

    def test_resolves_from_network_attributes(self):
        """Extracts phase domain from a phases network attribute."""
        data_element = {
            "networkAttributes": [
                {
                    "name": "Shape length",
                    "domain": None,
                },
                {
                    "name": "Phases Current",
                    "domain": {
                        "domainName": "Phases",
                        "codedValues": [
                            {"code": 7, "name": "ABC"},
                            {"code": 4, "name": "A"},
                            {"code": 2, "name": "B"},
                            {"code": 1, "name": "C"},
                            {"code": 5, "name": "AC"},
                        ],
                    },
                },
            ],
        }
        result = resolve_phase_domain(data_element)
        assert result == {7: "ABC", 4: "A", 2: "B", 1: "C", 5: "AC"}

    def test_returns_none_when_no_phase_attribute(self):
        """Returns None when no phase-related attribute has a domain."""
        data_element = {
            "networkAttributes": [
                {"name": "Shape length", "domain": None},
                {"name": "Load", "domain": {"domainName": "LoadValues", "codedValues": []}},
            ],
        }
        result = resolve_phase_domain(data_element)
        assert result is None

    def test_returns_none_for_empty_attributes(self):
        """Returns None for empty network attributes list."""
        result = resolve_phase_domain({"networkAttributes": []})
        assert result is None
