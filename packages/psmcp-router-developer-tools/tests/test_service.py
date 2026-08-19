"""Tests for the developer-tools router MCP tool functions."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from psmcp_router_developer_tools.models import (
    SampleResult,
    SampleSetSummary,
    Skill,
    SkillMetadata,
    SkillSummary,
)
from psmcp_router_developer_tools.service import (
    get_sample,
    get_skill,
    list_sample_sets,
    list_skills,
)


@pytest.fixture(autouse=True)
def _reset_registries():
    """Reset the module-level registries before each test."""
    import psmcp_router_developer_tools.service as svc

    svc._skill_registry = None
    svc._sample_registry = None
    yield
    svc._skill_registry = None
    svc._sample_registry = None


def _make_skill(
    name: str,
    description: str = "A skill",
    tags: list[str] | None = None,
    content: str = "# Body\n\nContent.",
    file_path: str = "skill.md",
    source_id: str = "test:source",
) -> Skill:
    return Skill(
        metadata=SkillMetadata(
            name=name,
            description=description,
            tags=tags or [],
            source_id=source_id,
        ),
        content=content,
        file_path=file_path,
    )


class TestListSkills:
    """Tests for the list_skills tool function."""

    async def test_returns_all_skills(self):
        """list_skills returns all skills when no tag filter is provided."""
        mock_registry = AsyncMock()
        mock_registry.list_skills.return_value = [
            SkillSummary(name="Skill A", description="First", tags=["python"], source="src1"),
            SkillSummary(name="Skill B", description="Second", tags=["js"], source="src2"),
        ]

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await list_skills()

        assert result["total"] == 2
        assert len(result["skills"]) == 2
        assert result["skills"][0]["name"] == "Skill A"
        assert result["skills"][1]["name"] == "Skill B"
        mock_registry.list_skills.assert_called_once_with(tags=None)

    async def test_passes_tag_filter(self):
        """list_skills passes tags to the registry."""
        mock_registry = AsyncMock()
        mock_registry.list_skills.return_value = [
            SkillSummary(name="Skill A", description="First", tags=["python"], source="src1"),
        ]

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await list_skills(tags=["python"])

        assert result["total"] == 1
        mock_registry.list_skills.assert_called_once_with(tags=["python"])

    async def test_returns_empty_list(self):
        """list_skills returns empty results gracefully."""
        mock_registry = AsyncMock()
        mock_registry.list_skills.return_value = []

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await list_skills()

        assert result["total"] == 0
        assert result["skills"] == []

    async def test_response_shape(self):
        """list_skills response includes expected fields."""
        mock_registry = AsyncMock()
        mock_registry.list_skills.return_value = [
            SkillSummary(
                name="Test", description="Desc", tags=["tag1", "tag2"], source="local:path"
            ),
        ]

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await list_skills()

        skill = result["skills"][0]
        assert skill == {
            "name": "Test",
            "description": "Desc",
            "tags": ["tag1", "tag2"],
            "source": "local:path",
        }


class TestGetSkill:
    """Tests for the get_skill tool function."""

    async def test_returns_skill_content(self):
        """get_skill returns full skill data when found."""
        skill = _make_skill(
            name="Python Guide",
            description="Python best practices",
            tags=["python"],
            content="# Python Guide\n\nUse type hints.",
            file_path="guides/python.md",
            source_id="local:skills",
        )
        mock_source = AsyncMock()
        mock_source.read_file.return_value = None

        mock_registry = AsyncMock()
        mock_registry.get_skill.return_value = (skill, mock_source)

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await get_skill(name="Python Guide")

        assert result["name"] == "Python Guide"
        assert result["description"] == "Python best practices"
        assert result["tags"] == ["python"]
        assert result["source"] == "local:skills"
        assert result["content"] == "# Python Guide\n\nUse type hints."
        assert result["references"] == []

    async def test_returns_error_when_not_found(self):
        """get_skill returns error dict with available names when skill not found."""
        mock_registry = AsyncMock()
        mock_registry.get_skill.return_value = None
        mock_registry.get_available_names.return_value = ["Skill A", "Skill B"]

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await get_skill(name="Nonexistent")

        assert "error" in result
        assert "Nonexistent" in result["error"]
        assert result["available_skills"] == ["Skill A", "Skill B"]

    async def test_resolves_references(self):
        """get_skill resolves relative .md references in content."""
        skill = _make_skill(
            name="Main Skill",
            content="See [reference](./ref.md) for details.",
            file_path="skills/main.md",
        )
        mock_source = AsyncMock()
        mock_source.read_file.return_value = "# Reference\n\nReference content."

        mock_registry = AsyncMock()
        mock_registry.get_skill.return_value = (skill, mock_source)

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await get_skill(name="Main Skill")

        assert len(result["references"]) == 1
        ref = result["references"][0]
        assert ref["label"] == "reference"
        assert ref["path"] == "./ref.md"
        assert ref["content"] == "# Reference\n\nReference content."
        mock_source.read_file.assert_called_once_with("skills/ref.md")

    async def test_handles_unresolvable_reference(self):
        """get_skill includes error for references that can't be resolved."""
        skill = _make_skill(
            name="Broken Refs",
            content="See [missing](./gone.md) for info.",
            file_path="skills/broken.md",
        )
        mock_source = AsyncMock()
        mock_source.read_file.return_value = None

        mock_registry = AsyncMock()
        mock_registry.get_skill.return_value = (skill, mock_source)

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await get_skill(name="Broken Refs")

        assert len(result["references"]) == 1
        ref = result["references"][0]
        assert ref["label"] == "missing"
        assert "error" in ref

    async def test_no_references_in_content(self):
        """get_skill returns empty references when content has no .md links."""
        skill = _make_skill(
            name="Simple",
            content="# Simple\n\nNo links here.",
            file_path="simple.md",
        )
        mock_source = AsyncMock()

        mock_registry = AsyncMock()
        mock_registry.get_skill.return_value = (skill, mock_source)

        with patch(
            "psmcp_router_developer_tools.service._get_skill_registry",
            return_value=mock_registry,
        ):
            result = await get_skill(name="Simple")

        assert result["references"] == []
        mock_source.read_file.assert_not_called()


class TestListSampleSets:
    """Tests for the list_sample_sets tool function."""

    async def test_returns_configured_sets(self):
        """list_sample_sets returns all configured sample sets."""
        mock_registry = Mock()
        mock_registry.list_sample_sets.return_value = [
            SampleSetSummary(
                name="python-samples",
                source_type="local",
                languages=["python"],
                apis=["arcgis"],
            ),
            SampleSetSummary(
                name="js-samples",
                source_type="github",
                languages=["javascript"],
                apis=[],
            ),
        ]

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await list_sample_sets()

        assert result["total"] == 2
        assert len(result["sample_sets"]) == 2
        assert result["sample_sets"][0]["name"] == "python-samples"
        assert result["sample_sets"][0]["languages"] == ["python"]

    async def test_returns_message_when_empty(self):
        """list_sample_sets returns a message when no sets are configured."""
        mock_registry = Mock()
        mock_registry.list_sample_sets.return_value = []

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await list_sample_sets()

        assert result["sample_sets"] == []
        assert "message" in result

    async def test_response_shape(self):
        """list_sample_sets response includes expected fields."""
        mock_registry = Mock()
        mock_registry.list_sample_sets.return_value = [
            SampleSetSummary(
                name="test",
                source_type="github",
                languages=["python", "js"],
                apis=["rest"],
            ),
        ]

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await list_sample_sets()

        sample_set = result["sample_sets"][0]
        assert sample_set == {
            "name": "test",
            "source_type": "github",
            "languages": ["python", "js"],
            "apis": ["rest"],
        }


class TestGetSample:
    """Tests for the get_sample tool function."""

    async def test_returns_search_results(self):
        """get_sample returns matching results from the registry."""
        mock_registry = Mock()
        mock_registry.search = AsyncMock(
            return_value=[
                SampleResult(file_path="auth.py", content="def auth(): pass", relevance_score=5.0),
                SampleResult(
                    file_path="utils.py", content="def helper(): pass", relevance_score=2.0
                ),
            ]
        )

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await get_sample(sample_set="my-samples", query="auth")

        assert result["total"] == 2
        assert result["query"] == "auth"
        assert result["sample_set"] == "my-samples"
        assert result["results"][0]["file_path"] == "auth.py"
        assert result["results"][0]["relevance_score"] == 5.0
        mock_registry.search.assert_called_once_with("my-samples", "auth")

    async def test_returns_error_for_unknown_set(self):
        """get_sample returns error when sample set is not found."""
        mock_registry = Mock()
        mock_registry.search = AsyncMock(return_value=None)
        mock_registry.get_available_names.return_value = ["set-a", "set-b"]

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await get_sample(sample_set="nonexistent", query="test")

        assert "error" in result
        assert "nonexistent" in result["error"]
        assert result["available_sample_sets"] == ["set-a", "set-b"]

    async def test_returns_empty_results(self):
        """get_sample returns empty results when no matches found."""
        mock_registry = Mock()
        mock_registry.search = AsyncMock(return_value=[])

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await get_sample(sample_set="my-samples", query="xyz")

        assert result["results"] == []
        assert result["query"] == "xyz"
        assert result["sample_set"] == "my-samples"

    async def test_response_shape(self):
        """get_sample response includes expected fields for each result."""
        mock_registry = Mock()
        mock_registry.search = AsyncMock(
            return_value=[
                SampleResult(file_path="file.py", content="code here", relevance_score=3.5),
            ]
        )

        with patch(
            "psmcp_router_developer_tools.service._get_sample_registry",
            return_value=mock_registry,
        ):
            result = await get_sample(sample_set="samples", query="code")

        item = result["results"][0]
        assert item == {
            "file_path": "file.py",
            "content": "code here",
            "relevance_score": 3.5,
        }
