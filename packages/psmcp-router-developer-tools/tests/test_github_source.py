"""Tests for GitHub source implementation."""

import httpx
import pytest
import respx
from psmcp_router_developer_tools.cache import TTLCache
from psmcp_router_developer_tools.sources.github import (
    GitHubSampleSource,
    GitHubSkillSource,
    _is_dot_directory,
    _parse_github_url,
)


class TestParseGitHubUrl:
    """Tests for _parse_github_url()."""

    def test_standard_url(self):
        owner, repo = _parse_github_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_trailing_slash(self):
        owner, repo = _parse_github_url("https://github.com/owner/repo/")
        assert owner == "owner"
        assert repo == "repo"

    def test_org_with_hyphens(self):
        owner, repo = _parse_github_url("https://github.com/my-org/my-repo")
        assert owner == "my-org"
        assert repo == "my-repo"

    def test_url_with_dots_in_repo(self):
        owner, repo = _parse_github_url("https://github.com/org/repo.js")
        assert owner == "org"
        assert repo == "repo.js"


class TestIsDotDirectory:
    """Tests for _is_dot_directory()."""

    def test_dot_git_directory(self):
        assert _is_dot_directory(".git/config") is True

    def test_dot_github_directory(self):
        assert _is_dot_directory(".github/workflows/ci.yml") is True

    def test_nested_dot_directory(self):
        assert _is_dot_directory("src/.hidden/file.py") is True

    def test_normal_path(self):
        assert _is_dot_directory("src/main.py") is False

    def test_root_file(self):
        assert _is_dot_directory("README.md") is False

    def test_dotfile_in_root(self):
        # Only directories matter, not the filename itself
        assert _is_dot_directory(".gitignore") is False

    def test_deeply_nested_dot_directory(self):
        assert _is_dot_directory("a/b/.hidden/c/file.txt") is True

    def test_dot_in_filename_not_directory(self):
        assert _is_dot_directory("src/my.module/file.py") is False


class TestGitHubSkillSource:
    """Tests for GitHubSkillSource with mocked HTTP."""

    @pytest.fixture
    def cache(self):
        return TTLCache(ttl_seconds=300)

    @pytest.fixture
    def source(self, cache):
        return GitHubSkillSource(
            url="https://github.com/test-org/skills-repo",
            cache=cache,
            token="ghp_test_token",
        )

    def test_source_id(self, source):
        assert source.source_id == "github:test-org/skills-repo"

    @respx.mock
    async def test_load_skills_fetches_tree_and_files(self, source):
        """load_skills fetches the tree, then each .md file."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "skill-one.md", "type": "blob"},
                        {"path": "skill-two.md", "type": "blob"},
                        {"path": "not-markdown.py", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        respx.get(f"{raw_base}/skill-one.md").mock(
            return_value=httpx.Response(
                200,
                text="---\nname: Skill One\ndescription: First skill\ntags:\n  - python\n---\n"
                "# Skill One\n\nContent here.\n",
            )
        )
        respx.get(f"{raw_base}/skill-two.md").mock(
            return_value=httpx.Response(
                200,
                text="---\nname: Skill Two\ndescription: Second skill\n---\n"
                "# Skill Two\n\nMore content.\n",
            )
        )

        skills = await source.load_skills()
        assert len(skills) == 2
        names = {s.metadata.name for s in skills}
        assert names == {"Skill One", "Skill Two"}

    @respx.mock
    async def test_load_skills_skips_dot_directories(self, source):
        """Files in dot-directories are not fetched."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": ".github/workflows/ci.yml", "type": "blob"},
                        {"path": ".hidden/secret.md", "type": "blob"},
                        {"path": "valid.md", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        respx.get(f"{raw_base}/valid.md").mock(
            return_value=httpx.Response(
                200,
                text="---\nname: Valid\ndescription: OK\n---\nBody.\n",
            )
        )

        skills = await source.load_skills()
        assert len(skills) == 1
        assert skills[0].metadata.name == "Valid"

    @respx.mock
    async def test_load_skills_handles_404_repo(self, source):
        """Returns empty list when repo is not found."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        respx.get(tree_url).mock(return_value=httpx.Response(404))

        skills = await source.load_skills()
        assert skills == []

    @respx.mock
    async def test_load_skills_handles_401_auth_error(self, source):
        """Returns empty list on authentication failure."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        respx.get(tree_url).mock(return_value=httpx.Response(401))

        skills = await source.load_skills()
        assert skills == []

    @respx.mock
    async def test_load_skills_handles_403_forbidden(self, source):
        """Returns empty list on forbidden response."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        respx.get(tree_url).mock(return_value=httpx.Response(403))

        skills = await source.load_skills()
        assert skills == []

    @respx.mock
    async def test_load_skills_caches_results(self, source, cache):
        """Second call returns cached results without HTTP requests."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        tree_route = respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={"tree": [{"path": "skill.md", "type": "blob"}]},
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        respx.get(f"{raw_base}/skill.md").mock(
            return_value=httpx.Response(
                200,
                text="---\nname: Cached Skill\n---\nBody.\n",
            )
        )

        # First call — hits network
        skills1 = await source.load_skills()
        assert len(skills1) == 1
        assert tree_route.call_count == 1

        # Second call — from cache
        skills2 = await source.load_skills()
        assert len(skills2) == 1
        assert tree_route.call_count == 1  # No additional request

    @respx.mock
    async def test_load_skills_skips_file_on_404(self, source):
        """Individual file 404s are skipped gracefully."""
        tree_url = "https://api.github.com/repos/test-org/skills-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "exists.md", "type": "blob"},
                        {"path": "missing.md", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        respx.get(f"{raw_base}/exists.md").mock(
            return_value=httpx.Response(
                200,
                text="---\nname: Exists\n---\nBody.\n",
            )
        )
        respx.get(f"{raw_base}/missing.md").mock(return_value=httpx.Response(404))

        skills = await source.load_skills()
        assert len(skills) == 1
        assert skills[0].metadata.name == "Exists"

    @respx.mock
    async def test_read_file_returns_content(self, source):
        """read_file fetches and returns file content."""
        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        respx.get(f"{raw_base}/docs/reference.md").mock(
            return_value=httpx.Response(200, text="# Reference\n\nSome content.\n")
        )

        content = await source.read_file("docs/reference.md")
        assert content == "# Reference\n\nSome content.\n"

    @respx.mock
    async def test_read_file_returns_none_on_404(self, source):
        """read_file returns None when file doesn't exist."""
        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        respx.get(f"{raw_base}/missing.md").mock(return_value=httpx.Response(404))

        content = await source.read_file("missing.md")
        assert content is None

    @respx.mock
    async def test_read_file_caches_result(self, source):
        """read_file caches successful fetches."""
        raw_base = "https://raw.githubusercontent.com/test-org/skills-repo/main"
        route = respx.get(f"{raw_base}/cached.md").mock(
            return_value=httpx.Response(200, text="Cached content")
        )

        content1 = await source.read_file("cached.md")
        content2 = await source.read_file("cached.md")
        assert content1 == content2 == "Cached content"
        assert route.call_count == 1

    def test_auth_headers_with_token(self, source):
        """Headers include Bearer token when configured."""
        headers = source._auth_headers()
        assert headers["Authorization"] == "Bearer ghp_test_token"
        assert headers["Accept"] == "application/vnd.github.v3+json"

    def test_auth_headers_without_token(self, cache):
        """Headers omit Authorization when no token is set."""
        source = GitHubSkillSource(url="https://github.com/org/repo", cache=cache, token=None)
        # Override the module-level GITHUB_TOKEN
        source._token = None
        headers = source._auth_headers()
        assert "Authorization" not in headers


class TestGitHubSampleSource:
    """Tests for GitHubSampleSource with mocked HTTP."""

    @pytest.fixture
    def cache(self):
        return TTLCache(ttl_seconds=300)

    @pytest.fixture
    def source(self, cache):
        return GitHubSampleSource(
            url="https://github.com/test-org/samples-repo",
            name="test-samples",
            cache=cache,
            token="ghp_test_token",
        )

    def test_source_id(self, source):
        assert source.source_id == "github:test-samples"

    @respx.mock
    async def test_search_returns_matching_files(self, source):
        """search fetches all files and returns matches ranked by relevance."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "auth_example.py", "type": "blob"},
                        {"path": "utils.py", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/samples-repo/main"
        respx.get(f"{raw_base}/auth_example.py").mock(
            return_value=httpx.Response(
                200, text="def authenticate(token):\n    return verify(token)\n"
            )
        )
        respx.get(f"{raw_base}/utils.py").mock(
            return_value=httpx.Response(200, text="def helper():\n    pass\n")
        )

        results = await source.search("auth")
        assert len(results) == 1
        assert results[0][0] == "auth_example.py"
        assert results[0][2] > 0  # has a relevance score

    @respx.mock
    async def test_search_skips_binary_extensions(self, source):
        """Binary files are not fetched or included in results."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "logo.png", "type": "blob"},
                        {"path": "icon.ico", "type": "blob"},
                        {"path": "code.py", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/samples-repo/main"
        respx.get(f"{raw_base}/code.py").mock(
            return_value=httpx.Response(200, text="print('hello')\n")
        )

        results = await source.search("hello")
        paths = [r[0] for r in results]
        assert "code.py" in paths
        assert "logo.png" not in paths
        assert "icon.ico" not in paths

    @respx.mock
    async def test_search_skips_dot_directories(self, source):
        """Files in dot-directories are excluded from search."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": ".github/ci.yml", "type": "blob"},
                        {"path": "app.py", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/samples-repo/main"
        respx.get(f"{raw_base}/app.py").mock(
            return_value=httpx.Response(200, text="app = create_app()\n")
        )

        results = await source.search("app")
        assert len(results) == 1
        assert results[0][0] == "app.py"

    @respx.mock
    async def test_search_caches_file_list(self, source):
        """File list is cached after first search."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        tree_route = respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={"tree": [{"path": "file.py", "type": "blob"}]},
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/samples-repo/main"
        respx.get(f"{raw_base}/file.py").mock(return_value=httpx.Response(200, text="content"))

        await source.search("content")
        await source.search("other")

        assert tree_route.call_count == 1

    @respx.mock
    async def test_search_handles_repo_not_found(self, source):
        """Returns empty results when repo is not found."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        respx.get(tree_url).mock(return_value=httpx.Response(404))

        results = await source.search("anything")
        assert results == []

    @respx.mock
    async def test_search_returns_empty_for_no_match(self, source):
        """Returns empty list when no files match the query."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={"tree": [{"path": "hello.py", "type": "blob"}]},
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/samples-repo/main"
        respx.get(f"{raw_base}/hello.py").mock(
            return_value=httpx.Response(200, text="print('hello')\n")
        )

        results = await source.search("nonexistent_xyz")
        assert results == []

    @respx.mock
    async def test_search_only_includes_blobs(self, source):
        """Tree entries that are not blobs (e.g., trees) are skipped."""
        tree_url = "https://api.github.com/repos/test-org/samples-repo/git/trees/main"
        respx.get(tree_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "src", "type": "tree"},
                        {"path": "src/main.py", "type": "blob"},
                    ]
                },
            )
        )

        raw_base = "https://raw.githubusercontent.com/test-org/samples-repo/main"
        respx.get(f"{raw_base}/src/main.py").mock(
            return_value=httpx.Response(200, text="def main(): pass\n")
        )

        results = await source.search("main")
        assert len(results) == 1
        assert results[0][0] == "src/main.py"
