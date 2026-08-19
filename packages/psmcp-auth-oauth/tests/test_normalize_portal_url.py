"""Unit tests for portal URL normalization."""

from __future__ import annotations

import pytest
from psmcp_auth_oauth import normalize_portal_url


class TestNormalizePortalUrl:
    """Tests for normalize_portal_url covering Online and Enterprise patterns."""

    @pytest.mark.parametrize(
        ("raw_url", "expected"),
        [
            # ArcGIS Online — bare domain
            ("https://www.arcgis.com", "https://www.arcgis.com"),
            ("https://www.arcgis.com/", "https://www.arcgis.com"),
            ("https://www.arcgis.com///", "https://www.arcgis.com"),
            # ArcGIS Online — with sharing/rest suffix
            (
                "https://www.arcgis.com/sharing/rest",
                "https://www.arcgis.com",
            ),
            (
                "https://www.arcgis.com/sharing/rest/",
                "https://www.arcgis.com",
            ),
            (
                "https://www.arcgis.com/sharing/rest/oauth2/authorize",
                "https://www.arcgis.com",
            ),
            # ArcGIS Online — org subdomain
            (
                "https://myorg.maps.arcgis.com",
                "https://myorg.maps.arcgis.com",
            ),
            (
                "https://myorg.maps.arcgis.com/sharing/rest",
                "https://myorg.maps.arcgis.com",
            ),
            # ArcGIS Enterprise — web adaptor
            (
                "https://gis.example.com/portal",
                "https://gis.example.com/portal",
            ),
            (
                "https://gis.example.com/portal/",
                "https://gis.example.com/portal",
            ),
            (
                "https://gis.example.com/portal/sharing/rest",
                "https://gis.example.com/portal",
            ),
            (
                "https://gis.example.com/portal/sharing/rest/",
                "https://gis.example.com/portal",
            ),
            (
                "https://gis.example.com/portal/sharing/rest/oauth2/token",
                "https://gis.example.com/portal",
            ),
            # ArcGIS Enterprise — direct port
            (
                "https://portal.example.com:7443/arcgis",
                "https://portal.example.com:7443/arcgis",
            ),
            (
                "https://portal.example.com:7443/arcgis/sharing/rest",
                "https://portal.example.com:7443/arcgis",
            ),
            # Whitespace handling
            (
                "  https://www.arcgis.com  ",
                "https://www.arcgis.com",
            ),
            (
                "  https://gis.example.com/portal/sharing/rest/  ",
                "https://gis.example.com/portal",
            ),
        ],
        ids=[
            "online-bare",
            "online-trailing-slash",
            "online-multiple-trailing-slashes",
            "online-sharing-rest",
            "online-sharing-rest-slash",
            "online-full-oauth-path",
            "online-org-subdomain",
            "online-org-sharing-rest",
            "enterprise-web-adaptor",
            "enterprise-trailing-slash",
            "enterprise-sharing-rest",
            "enterprise-sharing-rest-slash",
            "enterprise-full-oauth-path",
            "enterprise-direct-port",
            "enterprise-direct-sharing-rest",
            "whitespace-bare",
            "whitespace-with-suffix",
        ],
    )
    def test_normalization(self, raw_url: str, expected: str) -> None:
        """URL is normalized to portal root regardless of input format."""
        assert normalize_portal_url(raw_url) == expected

    def test_case_insensitive_suffix_stripping(self) -> None:
        """The /sharing/rest suffix is matched case-insensitively."""
        assert (
            normalize_portal_url("https://gis.example.com/portal/Sharing/Rest")
            == "https://gis.example.com/portal"
        )
        assert (
            normalize_portal_url("https://gis.example.com/portal/SHARING/REST/oauth2")
            == "https://gis.example.com/portal"
        )
