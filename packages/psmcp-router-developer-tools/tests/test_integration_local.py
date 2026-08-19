"""Integration tests for local source end-to-end flows.

These tests exercise the full flow from filesystem to parsed results,
using real temporary directories with actual files.

Validates: Requirements 1.4, 1.5, 4.3
"""

import pytest
from psmcp_router_developer_tools.sources.local import LocalSampleSource, LocalSkillSource


class TestLocalSkillSourceIntegration:
    """End-to-end tests for skill loading from real filesystem directories."""

    @pytest.fixture
    def skills_dir(self, tmp_path):
        """Create a realistic skill directory with valid and invalid files."""
        # Valid skill: python best practices
        (tmp_path / "python-best-practices.md").write_text(
            "---\n"
            "name: Python Best Practices\n"
            "description: Guidelines for writing clean Python code\n"
            "tags:\n"
            "  - python\n"
            "  - best-practices\n"
            "---\n"
            "# Python Best Practices\n\n"
            "Use type hints on all function signatures.\n"
            "Prefer pathlib over os.path.\n",
            encoding="utf-8",
        )

        # Valid skill: deployment guide
        (tmp_path / "deployment-guide.md").write_text(
            "---\n"
            "name: Deployment Guide\n"
            "description: How to deploy services\n"
            "tags:\n"
            "  - deployment\n"
            "  - docker\n"
            "metadata:\n"
            "  tags:\n"
            "    - ci-cd\n"
            "---\n"
            "# Deployment Guide\n\n"
            "Use Docker Compose for local development.\n",
            encoding="utf-8",
        )

        # Invalid: no front matter
        (tmp_path / "readme.md").write_text(
            "# Just a README\n\nNo front matter here.\n",
            encoding="utf-8",
        )

        # Invalid: empty name field
        (tmp_path / "empty-name.md").write_text(
            "---\nname: \ndescription: Has empty name\n---\nContent with empty name.\n",
            encoding="utf-8",
        )

        # Invalid: malformed YAML
        (tmp_path / "bad-yaml.md").write_text(
            "---\nname: [unclosed bracket\n---\nContent after bad yaml.\n",
            encoding="utf-8",
        )

        return tmp_path

    async def test_loads_valid_skills_and_skips_invalid(self, skills_dir):
        """Full loading: valid skills are returned, invalid ones are skipped gracefully."""
        source = LocalSkillSource(str(skills_dir))
        skills = await source.load_skills()

        names = {s.metadata.name for s in skills}
        assert names == {"Python Best Practices", "Deployment Guide"}

    async def test_skill_metadata_is_complete(self, skills_dir):
        """Loaded skills have correct metadata including merged tags."""
        source = LocalSkillSource(str(skills_dir))
        skills = await source.load_skills()

        by_name = {s.metadata.name: s for s in skills}

        python_skill = by_name["Python Best Practices"]
        assert python_skill.metadata.description == "Guidelines for writing clean Python code"
        assert set(python_skill.metadata.tags) == {"python", "best-practices"}
        assert python_skill.metadata.source_id == f"local:{skills_dir}"

        deploy_skill = by_name["Deployment Guide"]
        assert deploy_skill.metadata.description == "How to deploy services"
        # Tags merged from top-level and metadata.tags
        assert set(deploy_skill.metadata.tags) == {"deployment", "docker", "ci-cd"}

    async def test_skill_content_is_body_without_front_matter(self, skills_dir):
        """Skill content is the markdown body after the front matter block."""
        source = LocalSkillSource(str(skills_dir))
        skills = await source.load_skills()

        by_name = {s.metadata.name: s for s in skills}
        python_skill = by_name["Python Best Practices"]
        assert "# Python Best Practices" in python_skill.content
        assert "Use type hints" in python_skill.content
        # Front matter delimiters should not be in content
        assert "---" not in python_skill.content

    async def test_nested_directory_skills_are_loaded(self, tmp_path):
        """Skills in nested subdirectories are discovered and loaded."""
        nested = tmp_path / "category" / "subcategory"
        nested.mkdir(parents=True)

        (nested / "deep-skill.md").write_text(
            "---\n"
            "name: Deep Skill\n"
            "description: A deeply nested skill\n"
            "tags:\n"
            "  - nested\n"
            "---\n"
            "# Deep Skill\n\nContent from deep nesting.\n",
            encoding="utf-8",
        )

        (tmp_path / "top-skill.md").write_text(
            "---\n"
            "name: Top Skill\n"
            "description: A top-level skill\n"
            "---\n"
            "# Top Skill\n\nTop level content.\n",
            encoding="utf-8",
        )

        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()

        names = {s.metadata.name for s in skills}
        assert names == {"Deep Skill", "Top Skill"}

        # Verify file_path includes relative directory structure
        by_name = {s.metadata.name: s for s in skills}
        deep = by_name["Deep Skill"]
        assert "category" in deep.file_path
        assert "subcategory" in deep.file_path

    async def test_invalid_front_matter_files_skipped_gracefully(self, tmp_path):
        """Files with invalid YAML front matter are skipped without raising."""
        (tmp_path / "bad.md").write_text(
            "---\nname: [invalid: yaml: here\n---\nBody content.\n",
            encoding="utf-8",
        )

        (tmp_path / "good.md").write_text(
            "---\nname: Good Skill\ndescription: Valid\n---\nGood content.\n",
            encoding="utf-8",
        )

        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()

        assert len(skills) == 1
        assert skills[0].metadata.name == "Good Skill"


class TestLocalSkillSourceDotDirectoryExclusion:
    """Integration tests for dot-directory exclusion in skill loading."""

    async def test_git_directory_excluded(self, tmp_path):
        """Files inside .git/ are not loaded as skills."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD.md").write_text(
            "---\nname: Git Internal\n---\nShould not load.\n",
            encoding="utf-8",
        )

        (tmp_path / "real-skill.md").write_text(
            "---\nname: Real Skill\ndescription: Valid\n---\nContent.\n",
            encoding="utf-8",
        )

        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()

        assert len(skills) == 1
        assert skills[0].metadata.name == "Real Skill"

    async def test_github_directory_excluded(self, tmp_path):
        """Files inside .github/ are not loaded as skills."""
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        (github_dir / "workflow.md").write_text(
            "---\nname: Workflow\n---\nGitHub workflow.\n",
            encoding="utf-8",
        )

        (tmp_path / "valid.md").write_text(
            "---\nname: Valid Skill\ndescription: OK\n---\nBody.\n",
            encoding="utf-8",
        )

        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()

        assert len(skills) == 1
        assert skills[0].metadata.name == "Valid Skill"

    async def test_nested_dot_directory_excluded(self, tmp_path):
        """Files in nested dot-directories (e.g., subdir/.hidden/) are excluded."""
        nested_hidden = tmp_path / "docs" / ".drafts"
        nested_hidden.mkdir(parents=True)
        (nested_hidden / "draft.md").write_text(
            "---\nname: Draft\n---\nDraft content.\n",
            encoding="utf-8",
        )

        (tmp_path / "docs" / "published.md").write_text(
            "---\nname: Published\ndescription: A published doc\n---\nPublished.\n",
            encoding="utf-8",
        )

        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()

        assert len(skills) == 1
        assert skills[0].metadata.name == "Published"

    async def test_multiple_dot_directories_all_excluded(self, tmp_path):
        """Multiple dot-directories at various levels are all excluded."""
        for dot_name in [".git", ".github", ".vscode", ".idea"]:
            dot_dir = tmp_path / dot_name
            dot_dir.mkdir()
            (dot_dir / "file.md").write_text(
                f"---\nname: {dot_name} file\n---\nContent.\n",
                encoding="utf-8",
            )

        (tmp_path / "skill.md").write_text(
            "---\nname: Only Skill\ndescription: The only valid one\n---\nContent.\n",
            encoding="utf-8",
        )

        source = LocalSkillSource(str(tmp_path))
        skills = await source.load_skills()

        assert len(skills) == 1
        assert skills[0].metadata.name == "Only Skill"


class TestLocalSampleSourceIntegration:
    """End-to-end tests for sample search across real filesystem directories."""

    @pytest.fixture
    def code_dir(self, tmp_path):
        """Create a realistic code sample directory."""
        # Python file
        (tmp_path / "auth_handler.py").write_text(
            "import httpx\n\n"
            "async def authenticate(token: str) -> dict:\n"
            '    """Authenticate with the API using a bearer token."""\n'
            "    async with httpx.AsyncClient() as client:\n"
            "        resp = await client.get(\n"
            "            'https://api.example.com/auth',\n"
            "            headers={'Authorization': f'Bearer {token}'}\n"
            "        )\n"
            "        return resp.json()\n",
            encoding="utf-8",
        )

        # JavaScript file
        (tmp_path / "app.js").write_text(
            "const express = require('express');\n"
            "const app = express();\n\n"
            "app.get('/health', (req, res) => {\n"
            "    res.json({ status: 'ok' });\n"
            "});\n\n"
            "module.exports = app;\n",
            encoding="utf-8",
        )

        # TypeScript file
        (tmp_path / "service.ts").write_text(
            "export interface AuthConfig {\n"
            "    token: string;\n"
            "    baseUrl: string;\n"
            "}\n\n"
            "export async function authenticate(config: AuthConfig): Promise<void> {\n"
            "    const response = await fetch(config.baseUrl + '/auth', {\n"
            "        headers: { Authorization: `Bearer ${config.token}` }\n"
            "    });\n"
            "    if (!response.ok) throw new Error('Auth failed');\n"
            "}\n",
            encoding="utf-8",
        )

        return tmp_path

    async def test_search_finds_relevant_files(self, code_dir):
        """Search returns files containing the query terms."""
        source = LocalSampleSource(str(code_dir), "code-samples")
        results = await source.search("authenticate")

        paths = [r[0] for r in results]
        assert "auth_handler.py" in paths
        assert "service.ts" in paths

    async def test_search_results_ranked_by_relevance(self, code_dir):
        """Results are sorted by relevance score (highest first)."""
        source = LocalSampleSource(str(code_dir), "code-samples")
        results = await source.search("auth")

        # auth_handler.py has "auth" in both path and content
        # service.ts has "auth" in content but not path
        assert len(results) >= 2
        scores = [r[2] for r in results]
        assert scores == sorted(scores, reverse=True)

        # auth_handler.py should rank highest due to path match bonus
        assert results[0][0] == "auth_handler.py"

    async def test_search_returns_file_content(self, code_dir):
        """Search results include the full file content."""
        source = LocalSampleSource(str(code_dir), "code-samples")
        results = await source.search("express")

        assert len(results) == 1
        path, content, score = results[0]
        assert path == "app.js"
        assert "const express = require('express')" in content
        assert score > 0

    async def test_search_across_nested_directories(self, tmp_path):
        """Search discovers files in nested subdirectories."""
        nested = tmp_path / "src" / "utils"
        nested.mkdir(parents=True)

        (nested / "helper.py").write_text(
            "def format_date(dt):\n    return dt.strftime('%Y-%m-%d')\n",
            encoding="utf-8",
        )

        (tmp_path / "main.py").write_text(
            "from src.utils.helper import format_date\n\nprint(format_date(now))\n",
            encoding="utf-8",
        )

        source = LocalSampleSource(str(tmp_path), "nested-samples")
        results = await source.search("format_date")

        paths = [r[0] for r in results]
        assert len(paths) == 2
        # Both files reference format_date
        assert any("helper.py" in p for p in paths)
        assert any("main.py" in p for p in paths)


class TestLocalSampleSourceDotDirectoryExclusion:
    """Integration tests for dot-directory exclusion in sample search."""

    async def test_git_directory_excluded_from_search(self, tmp_path):
        """Files inside .git/ are not included in search results."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text(
            "repositoryformatversion = 0\nfilemode = true\n",
            encoding="utf-8",
        )

        (tmp_path / "main.py").write_text(
            "# Main application\nprint('hello')\n",
            encoding="utf-8",
        )

        source = LocalSampleSource(str(tmp_path), "test")
        # Search for something that exists in .git/config
        results = await source.search("repositoryformatversion")
        assert results == []

    async def test_github_directory_excluded_from_search(self, tmp_path):
        """Files inside .github/ are not included in search results."""
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        workflows = github_dir / "workflows"
        workflows.mkdir()
        (workflows / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
            encoding="utf-8",
        )

        (tmp_path / "app.py").write_text(
            "# Application code\ndef run(): pass\n",
            encoding="utf-8",
        )

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("ubuntu")
        assert results == []

    async def test_dot_files_in_root_excluded(self, tmp_path):
        """Dot-prefixed files (not just directories) are excluded from search."""
        (tmp_path / ".env").write_text(
            "SECRET_KEY=mysecret\nDATABASE_URL=postgres://localhost\n",
            encoding="utf-8",
        )

        (tmp_path / "config.py").write_text(
            "import os\nSECRET = os.getenv('SECRET_KEY')\n",
            encoding="utf-8",
        )

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("SECRET")

        paths = [r[0] for r in results]
        assert "config.py" in paths
        assert ".env" not in paths


class TestLocalSampleSourceBinaryFileSkipping:
    """Integration tests for binary file skipping in sample search."""

    async def test_png_files_skipped(self, tmp_path):
        """PNG image files are not included in search results."""
        (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        (tmp_path / "readme.txt").write_text("See logo.png for the logo\n", encoding="utf-8")

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("logo")

        paths = [r[0] for r in results]
        assert "readme.txt" in paths
        assert "logo.png" not in paths

    async def test_jpg_files_skipped(self, tmp_path):
        """JPEG image files are not included in search results."""
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        (tmp_path / "gallery.html").write_text(
            "<img src='photo.jpg' alt='photo'>\n", encoding="utf-8"
        )

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("photo")

        paths = [r[0] for r in results]
        assert "gallery.html" in paths
        assert "photo.jpg" not in paths

    async def test_gif_files_skipped(self, tmp_path):
        """GIF image files are not included in search results."""
        (tmp_path / "animation.gif").write_bytes(b"GIF89a" + b"\x00" * 100)
        (tmp_path / "page.html").write_text("<img src='animation.gif'>\n", encoding="utf-8")

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("animation")

        paths = [r[0] for r in results]
        assert "page.html" in paths
        assert "animation.gif" not in paths

    async def test_font_files_skipped(self, tmp_path):
        """Font files (.woff, .ttf) are not included in search results."""
        (tmp_path / "custom.woff").write_bytes(b"wOFF" + b"\x00" * 100)
        (tmp_path / "icons.ttf").write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 100)
        (tmp_path / "styles.css").write_text(
            "@font-face { font-family: 'custom'; src: url('custom.woff'); }\n",
            encoding="utf-8",
        )

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("custom")

        paths = [r[0] for r in results]
        assert "styles.css" in paths
        assert "custom.woff" not in paths
        assert "icons.ttf" not in paths

    async def test_text_files_with_binary_content_handled(self, tmp_path):
        """Files that fail UTF-8 decoding are silently skipped."""
        # Write actual binary content without a known-skip extension
        (tmp_path / "data.bin").write_bytes(b"\x80\x81\x82\x83\xff\xfe\xfd")
        (tmp_path / "reader.py").write_text(
            "with open('data.bin', 'rb') as f:\n    data = f.read()\n",
            encoding="utf-8",
        )

        source = LocalSampleSource(str(tmp_path), "test")
        results = await source.search("data")

        paths = [r[0] for r in results]
        assert "reader.py" in paths
        # data.bin should be skipped due to UnicodeDecodeError
        assert "data.bin" not in paths
