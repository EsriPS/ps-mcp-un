"""Property-based tests for LLM response cleaning logic.

Feature: dynamic-application-router
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from psmcp_router_dynamic_app.llm import _clean_llm_response

# Strategy: generate arbitrary text content (no null bytes, no backtick sequences
# that would be confused with markdown delimiters during stripping)
_content_text = st.text(
    alphabet=st.characters(exclude_characters="\x00"),
    min_size=0,
    max_size=200,
).filter(lambda s: "```" not in s)

# Strategy: markdown language prefixes that _clean_llm_response handles
_markdown_prefixes = st.sampled_from(["```html", "```javascript", "```js", "```"])


# Feature: dynamic-application-router, Property 7: Markdown Code Block Stripping
class TestMarkdownCodeBlockStripping:
    """Property 7: Markdown Code Block Stripping.

    For any string s, if s is wrapped with ```html prefix and ``` suffix,
    or just ``` prefix and ``` suffix, then _clean_llm_response(s) SHALL return
    the inner content with delimiters removed and whitespace trimmed. If s has no
    markdown delimiters, the result SHALL equal s.strip().

    **Validates: Requirements 7.7**
    """

    @settings(max_examples=100)
    @given(content=_content_text, prefix=_markdown_prefixes)
    def test_wrapped_strings_have_delimiters_removed(self, content: str, prefix: str) -> None:
        """Strings wrapped with markdown code block delimiters have them removed.

        **Validates: Requirements 7.7**
        """
        wrapped = f"{prefix}\n{content}\n```"
        result = _clean_llm_response(wrapped)
        # The result should not contain the prefix or trailing ```
        assert not result.startswith(prefix)
        assert not result.endswith("```")
        # The result should equal the inner content stripped
        assert result == content.strip()

    @settings(max_examples=100)
    @given(content=_content_text, prefix=_markdown_prefixes)
    def test_wrapped_strings_without_newline_have_delimiters_removed(
        self, content: str, prefix: str
    ) -> None:
        """Strings wrapped with markdown delimiters (no newline after prefix) are cleaned.

        **Validates: Requirements 7.7**
        """
        wrapped = f"{prefix}{content}```"
        result = _clean_llm_response(wrapped)
        assert not result.startswith(prefix)
        assert not result.endswith("```")
        assert result == content.strip()

    @settings(max_examples=100)
    @given(
        content=st.text(
            alphabet=st.characters(
                exclude_characters="\x00`",
            ),
            min_size=0,
            max_size=200,
        ).filter(lambda s: not s.startswith("```") and not s.endswith("```"))
    )
    def test_unwrapped_strings_equal_stripped(self, content: str) -> None:
        """Strings without markdown delimiters return s.strip().

        **Validates: Requirements 7.7**
        """
        result = _clean_llm_response(content)
        assert result == content.strip()

    @settings(max_examples=100)
    @given(content=_content_text, prefix=_markdown_prefixes)
    def test_result_is_trimmed(self, content: str, prefix: str) -> None:
        """The result of cleaning a wrapped string has no leading/trailing whitespace.

        **Validates: Requirements 7.7**
        """
        # Add extra whitespace around the content inside the block
        wrapped = f"{prefix}  \n  {content}  \n  ```"
        result = _clean_llm_response(wrapped)
        assert result == result.strip()
