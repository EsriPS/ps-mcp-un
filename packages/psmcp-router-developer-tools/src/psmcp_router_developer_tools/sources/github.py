"""GitHub-backed source implementation."""

import logging
from pathlib import PurePosixPath

import httpx

from psmcp_router_developer_tools.cache import TTLCache
from psmcp_router_developer_tools.config import GITHUB_TOKEN
from psmcp_router_developer_tools.models import Skill
from psmcp_router_developer_tools.parsing import parse_skill_file
from psmcp_router_developer_tools.scoring import compute_relevance

logger = logging.getLogger(__name__)


class GitHubSkillSource:
    """Loads skills from a GitHub repository.

    Uses the GitHub Trees API to list files and the raw content API
    to fetch individual files. Results are cached via the shared TTLCache.
    """

    def __init__(self, url: str, cache: TTLCache, token: str | None = None, ref: str | None = None):
        self._url = url
        self._cache = cache
        self._token = token or GITHUB_TOKEN
        self._owner, self._repo = _parse_github_url(url)
        self._ref = ref  # resolved lazily on first use

    @property
    def source_id(self) -> str:
        return f"github:{self._owner}/{self._repo}"

    async def load_skills(self) -> list[Skill]:
        """Fetch all .md files from the repo, parse as skills."""
        cached = self._cache.get(f"skills:{self.source_id}")
        if cached is not None:
            return cached

        skills: list[Skill] = []
        tree = await self._fetch_tree()
        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not path.endswith(".md"):
                continue
            if _is_dot_directory(path):
                continue
            content = await self._fetch_file_content(path)
            if content is None:
                continue
            skill = parse_skill_file(content, path, self.source_id)
            if skill is not None:
                skills.append(skill)

        self._cache.set(f"skills:{self.source_id}", skills)
        return skills

    async def read_file(self, relative_path: str) -> str | None:
        """Read a single file from the repo for reference resolution.

        Dot-directory paths are excluded for security (consistent with discovery).
        """
        if _is_dot_directory(relative_path):
            logger.debug("Blocked read_file for dot-directory path: %s", relative_path)
            return None
        cache_key = f"file:{self.source_id}:{relative_path}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        content = await self._fetch_file_content(relative_path)
        if content is not None:
            self._cache.set(cache_key, content)
        return content

    async def _resolve_ref(self) -> str:
        """Resolve the default branch ref for this repo (cached)."""
        if self._ref is not None:
            return self._ref
        cache_key = f"ref:{self.source_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._ref = cached
            return self._ref
        url = f"https://api.github.com/repos/{self._owner}/{self._repo}"
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    self._ref = resp.json().get("default_branch", "main")
                else:
                    logger.warning(
                        "Could not resolve default branch for %s/%s (status %d), using 'main'",
                        self._owner,
                        self._repo,
                        resp.status_code,
                    )
                    self._ref = "main"
            except httpx.HTTPError:
                self._ref = "main"
        self._cache.set(cache_key, self._ref)
        return self._ref

    async def _fetch_tree(self) -> list[dict]:
        """Fetch the full repo tree via GitHub Trees API."""
        ref = await self._resolve_ref()
        url = f"https://api.github.com/repos/{self._owner}/{self._repo}/git/trees/{ref}"
        headers = self._auth_headers()
        params = {"recursive": "1"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code in (401, 403):
                    raise PermissionError(
                        f"GitHub API authentication failed ({resp.status_code}) for "
                        f"{self._owner}/{self._repo}. Ensure GITHUB_TOKEN is set and valid "
                        f"for this repository."
                    )
                if resp.status_code == 404:
                    logger.warning("GitHub repo not found: %s/%s", self._owner, self._repo)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return data.get("tree", [])
            except httpx.HTTPStatusError as e:
                logger.error("GitHub tree fetch failed: %s", e)
                return []

    async def _fetch_file_content(self, path: str) -> str | None:
        """Fetch raw file content from GitHub."""
        ref = await self._resolve_ref()
        url = f"https://raw.githubusercontent.com/{self._owner}/{self._repo}/{ref}/{path}"
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code in (401, 403):
                    logger.warning("GitHub auth error (%d) fetching %s", resp.status_code, path)
                    return None
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                logger.error("GitHub file fetch failed for %s: %s", path, e)
                return None

    def _auth_headers(self) -> dict[str, str]:
        """Build request headers with optional Bearer token auth."""
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers


class GitHubSampleSource:
    """Searches code samples in a GitHub repository."""

    def __init__(
        self, url: str, name: str, cache: TTLCache, token: str | None = None, ref: str | None = None
    ):
        self._url = url
        self._name = name
        self._cache = cache
        self._token = token or GITHUB_TOKEN
        self._owner, self._repo = _parse_github_url(url)
        self._ref = ref  # resolved lazily on first use

    @property
    def source_id(self) -> str:
        return f"github:{self._name}"

    async def search(self, query: str) -> list[tuple[str, str, float]]:
        """Search repo files for query matches.

        Args:
            query: Space-separated search terms.

        Returns:
            List of (file_path, content, relevance_score) tuples sorted by score.
        """
        files = await self._load_files()
        results: list[tuple[str, str, float]] = []
        query_terms = query.lower().split()
        for path, content in files:
            score = compute_relevance(content, path, query_terms)
            if score > 0:
                results.append((path, content, score))
        results.sort(key=lambda r: r[2], reverse=True)
        return results

    async def _load_files(self) -> list[tuple[str, str]]:
        """Load all text files from the repo (cached)."""
        cache_key = f"sample_files:{self.source_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        files: list[tuple[str, str]] = []
        tree = await self._fetch_tree()
        for item in tree:
            path = item.get("path", "")
            if item.get("type") != "blob":
                continue
            if _is_dot_directory(path):
                continue
            # Skip binary extensions
            if any(path.endswith(ext) for ext in (".png", ".jpg", ".gif", ".ico", ".woff", ".ttf")):
                continue
            content = await self._fetch_file_content(path)
            if content is not None:
                files.append((path, content))
        self._cache.set(cache_key, files)
        return files

    async def _fetch_tree(self) -> list[dict]:
        """Fetch the full repo tree via GitHub Trees API."""
        ref = await self._resolve_ref()
        url = f"https://api.github.com/repos/{self._owner}/{self._repo}/git/trees/{ref}"
        headers = self._auth_headers()
        params = {"recursive": "1"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code in (401, 403):
                    raise PermissionError(
                        f"GitHub API authentication failed ({resp.status_code}) for "
                        f"{self._owner}/{self._repo}. Ensure GITHUB_TOKEN is set and valid "
                        f"for this repository."
                    )
                if resp.status_code == 404:
                    logger.warning("GitHub repo not found: %s/%s", self._owner, self._repo)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return data.get("tree", [])
            except httpx.HTTPStatusError as e:
                logger.error("GitHub tree fetch failed: %s", e)
                return []

    async def _fetch_file_content(self, path: str) -> str | None:
        """Fetch raw file content from GitHub."""
        ref = await self._resolve_ref()
        url = f"https://raw.githubusercontent.com/{self._owner}/{self._repo}/{ref}/{path}"
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code in (401, 403):
                    logger.warning("GitHub auth error (%d) fetching %s", resp.status_code, path)
                    return None
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                logger.error("GitHub file fetch failed for %s: %s", path, e)
                return None

    async def _resolve_ref(self) -> str:
        """Resolve the default branch ref for this repo (cached)."""
        if self._ref is not None:
            return self._ref
        cache_key = f"ref:github:{self._owner}/{self._repo}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._ref = cached
            return self._ref
        url = f"https://api.github.com/repos/{self._owner}/{self._repo}"
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    self._ref = resp.json().get("default_branch", "main")
                else:
                    logger.warning(
                        "Could not resolve default branch for %s/%s (status %d), using 'main'",
                        self._owner,
                        self._repo,
                        resp.status_code,
                    )
                    self._ref = "main"
            except httpx.HTTPError:
                self._ref = "main"
        self._cache.set(cache_key, self._ref)
        return self._ref

    def _auth_headers(self) -> dict[str, str]:
        """Build request headers with optional Bearer token auth."""
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner and repo from a GitHub URL.

    Args:
        url: GitHub URL like "https://github.com/owner/repo".

    Returns:
        Tuple of (owner, repo).
    """
    parts = url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def _is_dot_directory(path: str) -> bool:
    """Check if any path component (except filename) starts with a dot.

    Args:
        path: File path to check.

    Returns:
        True if any directory component starts with '.'.
    """
    return any(part.startswith(".") for part in PurePosixPath(path).parts[:-1])
