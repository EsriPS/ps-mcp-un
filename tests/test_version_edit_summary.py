"""Tests for the version_edit_summary tool and its diff-summing helpers."""

from unittest.mock import MagicMock, patch

import pytest
from psmcp_router_version_editing.version_editing_service import (
    _sum_difference_object_ids,
    version_edit_summary,
)


class TestSumDifferenceObjectIds:
    """The diff summer counts inserts/updates/deletes across shape variants."""

    def test_top_level_list_of_layers(self):
        diffs = [
            {"inserts": [1, 2], "updates": [3], "deletes": []},
            {"inserts": [], "updates": [4, 5], "deletes": [6]},
        ]
        assert _sum_difference_object_ids(diffs) == 6

    def test_dict_wrapping_differences_key(self):
        diffs = {"differences": [{"inserts": [1], "updates": [2, 3], "deletes": [4]}]}
        assert _sum_difference_object_ids(diffs) == 4

    def test_object_id_suffix_variants(self):
        diffs = [
            {"insertObjectIds": [1, 2], "updateObjectIds": [3], "deleteObjectIds": [4, 5]},
        ]
        assert _sum_difference_object_ids(diffs) == 5

    def test_empty_and_unknown_shapes(self):
        assert _sum_difference_object_ids([]) == 0
        assert _sum_difference_object_ids({}) == 0
        assert _sum_difference_object_ids(None) == 0
        assert _sum_difference_object_ids("nope") == 0

    def test_ignores_non_list_entries(self):
        diffs = [{"inserts": None, "updates": [1]}, "junk", 42]
        assert _sum_difference_object_ids(diffs) == 1


class TestVersionEditSummary:
    """The tool merges differences + dirty-area counts, and handles errors."""

    @pytest.fixture(autouse=True)
    def _service_url(self, monkeypatch):
        monkeypatch.setenv("UTILITY_NETWORK_URL", "https://example.com/server/rest/services/UN/FeatureServer")
        monkeypatch.setenv("ARCGIS_TOKEN", "test-token")

    @patch("psmcp_router_version_editing.version_editing_service._count_topology_errors")
    @patch("psmcp_router_version_editing.version_editing_service._count_dirty_areas")
    @patch("psmcp_router_version_editing.version_editing_service._find_version")
    @patch("psmcp_router_version_editing.version_editing_service._get_version_manager")
    @patch("psmcp_router_version_editing.version_editing_service._connect_gis")
    async def test_reports_edits_dirty_areas_and_errors(
        self, _gis, _vm, find_version, count_dirty, count_errors
    ):
        version = MagicMock()
        version.differences.return_value = [
            {"inserts": [1, 2], "updates": [3], "deletes": []},
        ]
        find_version.return_value = version
        count_dirty.return_value = 2
        count_errors.return_value = 4

        result = await version_edit_summary(version_name="OWNER.Edit1")

        assert result["version_name"] == "OWNER.Edit1"
        assert result["features_edited"] == 3
        assert result["dirty_areas"] == 2
        assert result["has_dirty_areas"] is True
        assert result["error_count"] == 4
        assert result["has_errors"] is True
        version.start_reading.assert_called_once()
        version.stop_reading.assert_called_once()

    @patch("psmcp_router_version_editing.version_editing_service._count_topology_errors")
    @patch("psmcp_router_version_editing.version_editing_service._count_dirty_areas")
    @patch("psmcp_router_version_editing.version_editing_service._find_version")
    @patch("psmcp_router_version_editing.version_editing_service._get_version_manager")
    @patch("psmcp_router_version_editing.version_editing_service._connect_gis")
    async def test_clean_version_has_no_errors(
        self, _gis, _vm, find_version, count_dirty, count_errors
    ):
        version = MagicMock()
        version.differences.return_value = []
        find_version.return_value = version
        count_dirty.return_value = 0
        count_errors.return_value = 0

        result = await version_edit_summary(version_name="OWNER.Clean")

        assert result["error_count"] == 0
        assert result["has_errors"] is False
        assert result["has_dirty_areas"] is False

    @patch("psmcp_router_version_editing.version_editing_service._find_version")
    @patch("psmcp_router_version_editing.version_editing_service._get_version_manager")
    @patch("psmcp_router_version_editing.version_editing_service._connect_gis")
    async def test_version_not_found(self, _gis, _vm, find_version):
        find_version.return_value = None
        result = await version_edit_summary(version_name="OWNER.Missing")
        assert "error" in result
        assert "was not found" in result["error"]

    @patch("psmcp_router_version_editing.version_editing_service._count_topology_errors")
    @patch("psmcp_router_version_editing.version_editing_service._count_dirty_areas")
    @patch("psmcp_router_version_editing.version_editing_service._find_version")
    @patch("psmcp_router_version_editing.version_editing_service._get_version_manager")
    @patch("psmcp_router_version_editing.version_editing_service._connect_gis")
    async def test_counts_none_yield_null_flags(
        self, _gis, _vm, find_version, count_dirty, count_errors
    ):
        version = MagicMock()
        version.differences.return_value = []
        find_version.return_value = version
        count_dirty.return_value = None  # dirty-areas layer unavailable
        count_errors.return_value = None  # validate unavailable

        result = await version_edit_summary(version_name="OWNER.Edit1")

        assert result["features_edited"] == 0
        assert result["dirty_areas"] is None
        assert result["has_dirty_areas"] is None
        assert result["error_count"] is None
        assert result["has_errors"] is None

