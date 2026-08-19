"""Unit tests for YAML front matter parsing and reference resolution."""

from psmcp_router_developer_tools.parsing import (
    _merge_tags,
    find_relative_references,
    parse_front_matter,
    parse_skill_file,
    resolve_reference_path,
)


class TestParseFrontMatter:
    """Tests for parse_front_matter()."""

    def test_valid_front_matter(self):
        text = "---\nname: Test Skill\ndescription: A test\n---\n\nBody content here."
        fm, body = parse_front_matter(text)
        assert fm == {"name": "Test Skill", "description": "A test"}
        assert body == "Body content here."

    def test_no_front_matter_returns_empty_dict(self):
        text = "Just some markdown content without front matter."
        fm, body = parse_front_matter(text)
        assert fm == {}
        assert body == text

    def test_invalid_yaml_returns_empty_dict(self):
        text = "---\n: invalid: yaml: [unclosed\n---\n\nBody."
        fm, body = parse_front_matter(text)
        assert fm == {}
        assert body == text

    def test_non_dict_yaml_returns_empty_dict(self):
        text = "---\n- item1\n- item2\n---\n\nBody."
        fm, body = parse_front_matter(text)
        assert fm == {}
        assert body == text

    def test_front_matter_with_tags_list(self):
        text = "---\nname: Skill\ntags:\n  - python\n  - testing\n---\n\nContent."
        fm, body = parse_front_matter(text)
        assert fm["tags"] == ["python", "testing"]
        assert body == "Content."

    def test_empty_front_matter_returns_empty_dict(self):
        text = "---\n\n---\n\nBody."
        fm, body = parse_front_matter(text)
        # yaml.safe_load of empty string returns None, not a dict
        assert fm == {}
        assert body == text

    def test_front_matter_not_at_start(self):
        text = "Some text\n---\nname: Skill\n---\n\nBody."
        fm, body = parse_front_matter(text)
        assert fm == {}
        assert body == text


class TestParseSkillFile:
    """Tests for parse_skill_file()."""

    def test_valid_skill_file(self):
        content = (
            "---\nname: My Skill\ndescription: Does things\ntags:\n  - python\n---\n\nSkill body."
        )
        skill = parse_skill_file(content, "skills/my-skill.md", "local:test")
        assert skill is not None
        assert skill.metadata.name == "My Skill"
        assert skill.metadata.description == "Does things"
        assert skill.metadata.tags == ["python"]
        assert skill.metadata.source_id == "local:test"
        assert skill.content == "Skill body."
        assert skill.file_path == "skills/my-skill.md"

    def test_missing_front_matter_returns_none(self):
        content = "Just markdown without front matter."
        skill = parse_skill_file(content, "test.md", "local:test")
        assert skill is None

    def test_empty_name_returns_none(self):
        content = "---\nname: \ndescription: Something\n---\n\nBody."
        skill = parse_skill_file(content, "test.md", "local:test")
        assert skill is None

    def test_missing_name_field_returns_none(self):
        content = "---\ndescription: No name here\n---\n\nBody."
        skill = parse_skill_file(content, "test.md", "local:test")
        assert skill is None

    def test_whitespace_only_name_returns_none(self):
        content = "---\nname: '   '\n---\n\nBody."
        skill = parse_skill_file(content, "test.md", "local:test")
        assert skill is None

    def test_missing_description_defaults_to_empty(self):
        content = "---\nname: Skill\n---\n\nBody."
        skill = parse_skill_file(content, "test.md", "local:test")
        assert skill is not None
        assert skill.metadata.description == ""


class TestMergeTags:
    """Tests for _merge_tags()."""

    def test_top_level_list_tags(self):
        fm = {"tags": ["Python", "Testing"]}
        assert _merge_tags(fm) == ["python", "testing"]

    def test_top_level_string_tag(self):
        fm = {"tags": "Python"}
        assert _merge_tags(fm) == ["python"]

    def test_metadata_tags(self):
        fm = {"metadata": {"tags": ["deployment", "docker"]}}
        assert _merge_tags(fm) == ["deployment", "docker"]

    def test_merge_top_and_metadata_tags(self):
        fm = {"tags": ["python"], "metadata": {"tags": ["testing"]}}
        assert _merge_tags(fm) == ["python", "testing"]

    def test_deduplication_case_insensitive(self):
        fm = {"tags": ["Python", "PYTHON", "python"]}
        assert _merge_tags(fm) == ["python"]

    def test_deduplication_across_sources(self):
        fm = {"tags": ["python"], "metadata": {"tags": ["Python"]}}
        assert _merge_tags(fm) == ["python"]

    def test_empty_tags(self):
        fm = {}
        assert _merge_tags(fm) == []

    def test_whitespace_stripped(self):
        fm = {"tags": ["  python  ", " testing "]}
        assert _merge_tags(fm) == ["python", "testing"]

    def test_empty_string_tags_excluded(self):
        fm = {"tags": ["python", "", "  "]}
        assert _merge_tags(fm) == ["python"]

    def test_non_string_tags_converted(self):
        fm = {"tags": [123, True]}
        assert _merge_tags(fm) == ["123", "true"]

    def test_metadata_string_tag(self):
        fm = {"metadata": {"tags": "single-tag"}}
        assert _merge_tags(fm) == ["single-tag"]

    def test_metadata_not_dict_ignored(self):
        fm = {"metadata": "not a dict"}
        assert _merge_tags(fm) == []


class TestFindRelativeReferences:
    """Tests for find_relative_references()."""

    def test_finds_relative_md_links(self):
        content = "See [guide](./guide.md) and [reference](../ref.md) for details."
        refs = find_relative_references(content)
        assert refs == [("guide", "./guide.md"), ("reference", "../ref.md")]

    def test_ignores_absolute_paths(self):
        content = "See [docs](/absolute/path.md) for info."
        refs = find_relative_references(content)
        assert refs == []

    def test_ignores_http_links(self):
        content = "See [docs](http://example.com/file.md) and [more](https://example.com/other.md)."
        refs = find_relative_references(content)
        assert refs == []

    def test_ignores_non_md_links(self):
        content = "See [image](photo.png) and [script](run.py)."
        refs = find_relative_references(content)
        assert refs == []

    def test_empty_content(self):
        refs = find_relative_references("")
        assert refs == []

    def test_multiple_references(self):
        content = "[a](one.md) text [b](two.md) more [c](three.md)"
        refs = find_relative_references(content)
        assert refs == [("a", "one.md"), ("b", "two.md"), ("c", "three.md")]

    def test_empty_label(self):
        content = "[](empty-label.md)"
        refs = find_relative_references(content)
        assert refs == [("", "empty-label.md")]

    def test_nested_directory_reference(self):
        content = "[deep](sub/dir/file.md)"
        refs = find_relative_references(content)
        assert refs == [("deep", "sub/dir/file.md")]


class TestResolveReferencePath:
    """Tests for resolve_reference_path()."""

    def test_same_directory(self):
        result = resolve_reference_path("skills/my-skill.md", "other.md")
        assert result == "skills/other.md"

    def test_parent_directory(self):
        result = resolve_reference_path("skills/sub/my-skill.md", "../other.md")
        assert result == "skills/other.md"

    def test_subdirectory(self):
        result = resolve_reference_path("skills/my-skill.md", "sub/other.md")
        assert result == "skills/sub/other.md"

    def test_root_level_file(self):
        result = resolve_reference_path("skill.md", "other.md")
        assert result == "other.md"

    def test_deeply_nested(self):
        result = resolve_reference_path("a/b/c/skill.md", "../../ref.md")
        assert result == "a/ref.md"
