# Feature: dynamic-application-router, Property 9: Resource Content Idempotence
"""Property-based test verifying resource content idempotence.

**Validates: Requirements 3.5**

For any number of sequential calls to `get_viewer_html()`, the returned HTML string
SHALL be identical across all calls.
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from psmcp_router_dynamic_app.viewer import get_viewer_html


@settings(max_examples=100)
@given(call_count=st.integers(min_value=2, max_value=50))
def test_resource_content_idempotence(call_count: int) -> None:
    """Calling get_viewer_html() multiple times always returns the same string.

    **Validates: Requirements 3.5**
    """
    first_result = get_viewer_html()

    for _ in range(call_count - 1):
        assert get_viewer_html() == first_result
