"""Tests for local filesystem source implementation."""

import pytest
from psmcp_router_developer_tools.scoring import compute_relevance
from psmcp_router_developer_tools.sources.local import (
    LocalSampleSource,
    LocalSkillSource,
)


class TestLocalSkillSource:
    """Tests for LocalSkillSource."""

    @pytest.fixture
    def skill_dir(self, tmp_path):
        """Create a temporary directory with skill files."""
        skill = tmp_path / "test-skill.md"
        skill.write_text(
            "---\nname: Test Skill\ndescription: A test\ntags:\n  - python\n---\n"
            "# Test Skill\n\nSome content here.\n",
            encoding="utf-8",
        )
        return tmp_path

    async def test_load_skills_reads_md_files(self, skill_dir):
        source = LocalSkillSource(str(skill_dir))
        skills = await source.load_skills()
        assert len(skills) == 1
        assert skills[0].metadata.name == "Test Skill"
        assert skills[0].metadata.description == "A test"
        assert "python" in skills[0].metadata.tags

    async def test_load_skills_skips_dot_directories(self, skill_dir):
        dot_dir = skill_dir / ".hidden"
        dot_dir.mkdir()
        hidden_skill = dot_dir / "secret.md"
        hidden_skill.write_text(
            "---\nname: Hidden\ndescription: hidden\n---\nHidden content\n",
            encoding="utf-8",
        )
        source = LocalSkillSource(str(skill_dir))
        skills = await source.load_skills()
        assert len(skills) == 1
        assert skills[0].metadata.name == "Test Skill"

    async def test_load_skills_reads_nested_directories(self, skill_dir):
        nested = skill_dir / "subdir"
        nested.mkdir()
        nested_skill = nested / "nested-skill.md"
        nested_skill.write_text(
            "---\nname: Nested Skill\ndescription: nested\n---\nNested content\n",
            encoding="utf-8",
        )
        source = LocalSkillSource(str(skill_dir))
        skills = await source.load_skills()
        assert len(skills) == 2
        names = {s.metadata.name for s in skills}
        assert "Nested Skill" in names

    async def test_load_skills_returns_empty_for_nonexistent_path(self):
        source = LocalSkillSource("/nonexistent/path")
        skills = await source.load_skills()
        assert skills == []

    async def test_load_skills_skips_invalid_files(self, tmp_path):
        # File without front matter
        bad = tmp_path / "no-frontmatter.md"
        bad.write_text("# Just a heading\n\nNo front matter here.\n", encoding="utf-8")
        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()
        assert skills == []

    async def test_source_id_defaults_to_local_prefix(self):
        source = LocalSkillSource("/some/path")
        assert source.source_id == "local:/some/path"

    async def test_source_id_custom(self):
        source = LocalSkillSource("/some/path", source_id="custom:id")
        assert source.source_id == "custom:id"

    async def test_read_file_returns_content(self, skill_dir):
        source = LocalSkillSource(str(skill_dir))
        content = await source.read_file("test-skill.md")
        assert content is not None
        assert "Test Skill" in content

    async def test_read_file_returns_none_for_missing(self, skill_dir):
        source = LocalSkillSource(str(skill_dir))
        content = await source.read_file("nonexistent.md")
        assert content is None


class TestLocalSampleSource:
    """Tests for LocalSampleSource."""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Create a temporary directory with sample files."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def hello():\n    print('hello world')\n", encoding="utf-8")
        js_file = tmp_path / "app.js"
        js_file.write_text("console.log('hello');\n", encoding="utf-8")
        return tmp_path

    async def test_search_finds_matching_files(self, sample_dir):
        source = LocalSampleSource(str(sample_dir), "test-samples")
        results = await source.search("hello")
        assert len(results) == 2
        paths = [r[0] for r in results]
        assert "example.py" in paths
        assert "app.js" in paths

    async def test_search_case_insensitive(self, sample_dir):
        source = LocalSampleSource(str(sample_dir), "test-samples")
        results = await source.search("HELLO")
        assert len(results) == 2

    async def test_search_returns_empty_for_no_match(self, sample_dir):
        source = LocalSampleSource(str(sample_dir), "test-samples")
        results = await source.search("nonexistent_term_xyz")
        assert results == []

    async def test_search_skips_dot_directories(self, sample_dir):
        dot_dir = sample_dir / ".git"
        dot_dir.mkdir()
        hidden = dot_dir / "config"
        hidden.write_text("hello from git config\n", encoding="utf-8")
        source = LocalSampleSource(str(sample_dir), "test-samples")
        results = await source.search("hello")
        paths = [r[0] for r in results]
        assert not any(".git" in p for p in paths)

    async def test_search_skips_binary_extensions(self, sample_dir):
        img = sample_dir / "logo.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        source = LocalSampleSource(str(sample_dir), "test-samples")
        results = await source.search("PNG")
        paths = [r[0] for r in results]
        assert "logo.png" not in paths

    async def test_search_returns_empty_for_nonexistent_path(self):
        source = LocalSampleSource("/nonexistent/path", "missing")
        results = await source.search("hello")
        assert results == []

    async def test_search_results_sorted_by_relevance(self, tmp_path):
        # File with many matches should rank higher
        many = tmp_path / "many.txt"
        many.write_text("hello " * 8, encoding="utf-8")
        few = tmp_path / "few.txt"
        few.write_text("hello once\n", encoding="utf-8")
        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("hello")
        assert results[0][0] == "many.txt"
        assert results[0][2] > results[1][2]

    async def test_source_id(self):
        source = LocalSampleSource("/path", "my-samples")
        assert source.source_id == "local:my-samples"


class TestComputeRelevance:
    """Tests for compute_relevance scoring function."""

    def test_path_match_weighted_3(self):
        score = compute_relevance("no match here", "hello.py", ["hello"])
        assert score == 3.0

    def test_content_match_counts(self):
        score = compute_relevance("hello hello hello", "other.py", ["hello"])
        assert score == 3.0  # min(3, 10)

    def test_content_match_capped_at_10(self):
        content = "hello " * 20
        score = compute_relevance(content, "other.py", ["hello"])
        assert score == 10.0  # capped at 10

    def test_path_and_content_combined(self):
        score = compute_relevance("hello world", "hello.py", ["hello"])
        # path match (3.0) + content match (1 occurrence = 1.0)
        assert score == 4.0

    def test_multiple_terms(self):
        score = compute_relevance("hello world", "test.py", ["hello", "world"])
        # hello: 1 content match, world: 1 content match
        assert score == 2.0

    def test_no_match_returns_zero(self):
        score = compute_relevance("nothing here", "file.txt", ["missing"])
        assert score == 0.0

    def test_case_insensitive(self):
        score = compute_relevance("Hello World", "Test.py", ["hello"])
        assert score > 0
