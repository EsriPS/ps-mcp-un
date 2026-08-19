"""Tests for skill and sample registries."""

import pytest
from psmcp_router_developer_tools.models import (
    SampleResult,
    SampleSetConfig,
    SampleSetSummary,
    Skill,
    SkillMetadata,
    SkillSummary,
)
from psmcp_router_developer_tools.registry import SampleRegistry, SkillRegistry


class FakeSkillSource:
    """Fake skill source for testing."""

    def __init__(self, source_id: str, skills: list[Skill]):
        self._source_id = source_id
        self._skills = skills

    @property
    def source_id(self) -> str:
        return self._source_id

    async def load_skills(self) -> list[Skill]:
        return self._skills

    async def read_file(self, relative_path: str) -> str | None:
        return None


class FailingSkillSource:
    """Skill source that raises on load."""

    @property
    def source_id(self) -> str:
        return "failing:source"

    async def load_skills(self) -> list[Skill]:
        raise RuntimeError("Connection failed")

    async def read_file(self, relative_path: str) -> str | None:
        return None


class FakeSampleSource:
    """Fake sample source for testing."""

    def __init__(self, source_id: str, results: list[tuple[str, str, float]]):
        self._source_id = source_id
        self._results = results

    @property
    def source_id(self) -> str:
        return self._source_id

    async def search(self, query: str) -> list[tuple[str, str, float]]:
        return self._results


def _make_skill(name: str, tags: list[str], source_id: str = "test:source") -> Skill:
    """Helper to create a Skill with minimal boilerplate."""
    return Skill(
        metadata=SkillMetadata(
            name=name,
            description=f"Description for {name}",
            tags=tags,
            source_id=source_id,
        ),
        content=f"# {name}\n\nContent body.",
        file_path=f"{name.lower().replace(' ', '-')}.md",
    )


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    @pytest.fixture
    def skills(self):
        return [
            _make_skill("Python Guide", ["python", "backend"]),
            _make_skill("React Patterns", ["react", "frontend"]),
            _make_skill("Testing Best Practices", ["testing", "python"]),
        ]

    @pytest.fixture
    def registry(self, skills):
        source = FakeSkillSource("test:source", skills)
        return SkillRegistry([source])

    async def test_list_skills_returns_all_without_filter(self, registry):
        results = await registry.list_skills()
        assert len(results) == 3
        names = [r.name for r in results]
        assert "Python Guide" in names
        assert "React Patterns" in names
        assert "Testing Best Practices" in names

    async def test_list_skills_returns_skill_summaries(self, registry):
        results = await registry.list_skills()
        first = results[0]
        assert isinstance(first, SkillSummary)
        assert first.source == "test:source"
        assert first.description != ""

    async def test_list_skills_filters_by_tag(self, registry):
        results = await registry.list_skills(tags=["python"])
        assert len(results) == 2
        names = [r.name for r in results]
        assert "Python Guide" in names
        assert "Testing Best Practices" in names

    async def test_list_skills_tag_filter_case_insensitive(self, registry):
        results = await registry.list_skills(tags=["PYTHON"])
        assert len(results) == 2

    async def test_list_skills_tag_filter_matches_any(self, registry):
        results = await registry.list_skills(tags=["frontend", "testing"])
        assert len(results) == 2
        names = [r.name for r in results]
        assert "React Patterns" in names
        assert "Testing Best Practices" in names

    async def test_list_skills_tag_filter_no_match(self, registry):
        results = await registry.list_skills(tags=["nonexistent"])
        assert results == []

    async def test_get_skill_by_name(self, registry):
        result = await registry.get_skill("Python Guide")
        assert result is not None
        skill, source = result
        assert skill.metadata.name == "Python Guide"
        assert source.source_id == "test:source"

    async def test_get_skill_case_insensitive(self, registry):
        result = await registry.get_skill("python guide")
        assert result is not None
        assert result[0].metadata.name == "Python Guide"

    async def test_get_skill_case_insensitive_upper(self, registry):
        result = await registry.get_skill("PYTHON GUIDE")
        assert result is not None
        assert result[0].metadata.name == "Python Guide"

    async def test_get_skill_not_found(self, registry):
        result = await registry.get_skill("Nonexistent Skill")
        assert result is None

    async def test_get_available_names(self, registry):
        names = await registry.get_available_names()
        assert len(names) == 3
        assert "Python Guide" in names
        assert "React Patterns" in names
        assert "Testing Best Practices" in names

    async def test_lazy_loading_only_loads_once(self, skills):
        """Verify _ensure_loaded only calls load_skills once."""
        source = FakeSkillSource("test:source", skills)
        registry = SkillRegistry([source])

        await registry.list_skills()
        await registry.list_skills()
        await registry.get_skill("Python Guide")
        # If it loaded multiple times, we'd see duplicates
        names = await registry.get_available_names()
        assert len(names) == 3

    async def test_multiple_sources(self):
        source1 = FakeSkillSource("source:one", [_make_skill("Skill A", ["tag1"], "source:one")])
        source2 = FakeSkillSource("source:two", [_make_skill("Skill B", ["tag2"], "source:two")])
        registry = SkillRegistry([source1, source2])
        results = await registry.list_skills()
        assert len(results) == 2
        names = [r.name for r in results]
        assert "Skill A" in names
        assert "Skill B" in names

    async def test_failing_source_does_not_crash(self):
        good_source = FakeSkillSource("good:source", [_make_skill("Good Skill", ["tag"])])
        bad_source = FailingSkillSource()
        registry = SkillRegistry([good_source, bad_source])
        results = await registry.list_skills()
        assert len(results) == 1
        assert results[0].name == "Good Skill"

    async def test_empty_sources(self):
        registry = SkillRegistry([])
        results = await registry.list_skills()
        assert results == []
        names = await registry.get_available_names()
        assert names == []


class TestSampleRegistry:
    """Tests for SampleRegistry."""

    @pytest.fixture
    def configs(self):
        return [
            SampleSetConfig(
                name="python-samples",
                source_type="local",
                path="/samples/python",
                languages=["python"],
                apis=["arcgis"],
            ),
            SampleSetConfig(
                name="js-samples",
                source_type="github",
                url="https://github.com/org/js-samples",
                languages=["javascript", "typescript"],
                apis=[],
            ),
        ]

    @pytest.fixture
    def sources(self):
        return {
            "python-samples": FakeSampleSource(
                "local:python-samples",
                [
                    ("example.py", "print('hello')", 5.0),
                    ("utils.py", "def helper(): pass", 2.0),
                ],
            ),
            "js-samples": FakeSampleSource(
                "github:org/js-samples",
                [("app.ts", "console.log('hi')", 3.0)],
            ),
        }

    @pytest.fixture
    def registry(self, configs, sources):
        return SampleRegistry(configs, sources)

    def test_list_sample_sets(self, registry):
        results = registry.list_sample_sets()
        assert len(results) == 2
        assert all(isinstance(r, SampleSetSummary) for r in results)
        names = [r.name for r in results]
        assert "python-samples" in names
        assert "js-samples" in names

    def test_list_sample_sets_includes_metadata(self, registry):
        results = registry.list_sample_sets()
        py_set = next(r for r in results if r.name == "python-samples")
        assert py_set.source_type == "local"
        assert py_set.languages == ["python"]
        assert py_set.apis == ["arcgis"]

    async def test_search_delegates_to_source(self, registry):
        results = await registry.search("python-samples", "hello")
        assert results is not None
        assert len(results) == 2
        assert all(isinstance(r, SampleResult) for r in results)
        assert results[0].file_path == "example.py"
        assert results[0].content == "print('hello')"
        assert results[0].relevance_score == 5.0

    async def test_search_returns_none_for_unknown_set(self, registry):
        results = await registry.search("nonexistent-set", "query")
        assert results is None

    def test_get_available_names(self, registry):
        names = registry.get_available_names()
        assert len(names) == 2
        assert "python-samples" in names
        assert "js-samples" in names

    def test_empty_configs(self):
        registry = SampleRegistry([], {})
        assert registry.list_sample_sets() == []
        assert registry.get_available_names() == []

    async def test_search_empty_sources(self):
        configs = [SampleSetConfig(name="orphan", source_type="local", path="/nowhere")]
        registry = SampleRegistry(configs, {})
        results = await registry.search("orphan", "query")
        assert results is None
