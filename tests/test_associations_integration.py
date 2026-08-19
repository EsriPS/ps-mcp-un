"""Integration tests for network_query_associations against a live service."""

import os

import pytest
from psmcp_router_utilitynetwork.utility_network_service import network_query_associations


@pytest.mark.integration
class TestAssociationsIntegration:
    """Tests requiring a configured UTILITY_NETWORK_URL service."""

    @pytest.fixture(autouse=True)
    def require_service_url(self):
        if not os.getenv("UTILITY_NETWORK_URL"):
            pytest.skip("UTILITY_NETWORK_URL not set")

    async def test_query_returns_valid_structure(self):
        global_id = os.getenv("TEST_ASSOCIATION_GLOBAL_ID")
        if not global_id:
            pytest.skip("TEST_ASSOCIATION_GLOBAL_ID not set")

        result = await network_query_associations(global_id=global_id)

        assert "globalId" in result
        assert "associations" in result
        assert "associationCount" in result
        assert "serviceUrl" in result
        assert isinstance(result["associations"], list)
        assert result["associationCount"] == len(result["associations"])

    async def test_associations_have_resolved_names(self):
        global_id = os.getenv("TEST_ASSOCIATION_GLOBAL_ID")
        if not global_id:
            pytest.skip("TEST_ASSOCIATION_GLOBAL_ID not set")

        result = await network_query_associations(global_id=global_id)

        for assoc in result["associations"]:
            # associationType must be a string name
            assert isinstance(assoc["associationType"], str)
            assert assoc["associationType"] in (
                "connectivity",
                "containment",
                "structuralAttachment",
            )

            # Both sides must have resolved identity fields
            for side in ("fromFeature", "toFeature"):
                feature = assoc[side]
                assert "globalId" in feature
                assert "sourceName" in feature
                assert isinstance(feature["sourceName"], str)
                assert len(feature["sourceName"]) > 0

                assert "assetGroupName" in feature
                assert isinstance(feature["assetGroupName"], str)
                assert len(feature["assetGroupName"]) > 0

                assert "assetTypeName" in feature
                assert isinstance(feature["assetTypeName"], str)
                assert len(feature["assetTypeName"]) > 0
