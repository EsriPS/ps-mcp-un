"""Unit tests for viewer HTML structure.

**Validates: Requirements 3.1, 3.2, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 14.1, 14.2**

Tests verify the static HTML returned by get_viewer_html() contains all required
elements: SDK imports, event handlers, app-side tool registrations, model context
updates, error handling, token registration, customization script execution, and
type dispatch for all three map types.
"""

from __future__ import annotations

from psmcp_router_dynamic_app.viewer import get_viewer_html


def test_mcp_apps_sdk_import_present() -> None:
    """Verify MCP Apps SDK is imported from CDN."""
    html = get_viewer_html()
    assert "@modelcontextprotocol/ext-apps" in html


def test_arcgis_maps_sdk_import_present() -> None:
    """Verify ArcGIS Maps SDK for JavaScript v4.34 is imported."""
    html = get_viewer_html()
    assert "js.arcgis.com/4.34" in html


def test_ontoolinput_handler_present() -> None:
    """Verify ontoolinput handler is defined for streaming tool arguments."""
    html = get_viewer_html()
    assert "ontoolinput" in html


def test_ontoolresult_handler_present() -> None:
    """Verify ontoolresult handler is defined for final tool result data."""
    html = get_viewer_html()
    assert "ontoolresult" in html


def test_add_layer_tool_registered() -> None:
    """Verify add_layer app-side tool is registered."""
    html = get_viewer_html()
    assert '"add_layer"' in html


def test_remove_layer_tool_registered() -> None:
    """Verify remove_layer app-side tool is registered."""
    html = get_viewer_html()
    assert '"remove_layer"' in html


def test_change_basemap_tool_registered() -> None:
    """Verify change_basemap app-side tool is registered."""
    html = get_viewer_html()
    assert '"change_basemap"' in html


def test_update_symbology_tool_registered() -> None:
    """Verify update_symbology app-side tool is registered."""
    html = get_viewer_html()
    assert '"update_symbology"' in html


def test_get_current_view_tool_registered() -> None:
    """Verify get_current_view app-side tool is registered."""
    html = get_viewer_html()
    assert '"get_current_view"' in html


def test_update_model_context_calls_present() -> None:
    """Verify updateModelContext is called to push state back to the model."""
    html = get_viewer_html()
    assert "updateModelContext" in html


def test_error_handling_for_unrecognized_type() -> None:
    """Verify error handling for unrecognized map type values."""
    html = get_viewer_html()
    assert "Unrecognized map type" in html


def test_token_registration_with_identity_manager() -> None:
    """Verify token registration uses IdentityManager."""
    html = get_viewer_html()
    assert "IdentityManager" in html
    assert "registerToken" in html


def test_customization_script_execution() -> None:
    """Verify customization_script field is executed after map init."""
    html = get_viewer_html()
    assert "customization_script" in html


def test_type_dispatch_sample_map() -> None:
    """Verify type dispatch handles sample_map type."""
    html = get_viewer_html()
    assert '"sample_map"' in html


def test_type_dispatch_webmap() -> None:
    """Verify type dispatch handles webmap type."""
    html = get_viewer_html()
    assert '"webmap"' in html


def test_type_dispatch_layers_map() -> None:
    """Verify type dispatch handles layers_map type."""
    html = get_viewer_html()
    assert '"layers_map"' in html
