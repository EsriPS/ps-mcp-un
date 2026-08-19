"""Local filesystem source implementation."""

import asyncio
import logging
from pathlib import Path

from psmcp_router_developer_tools.models import Skill
from psmcp_router_developer_tools.parsing import parse_skill_file
from psmcp_router_developer_tools.scoring import compute_relevance

logger = logging.getLogger(__name__)


class LocalSkillSource:
    """Loads skills from a local filesystem directory."""

    def __init__(self, path: str, source_id: str | None = None):
        self._path = Path(path)
        self._source_id = source_id or f"local:{path}"

    @property
    def source_id(self) -> str:
        return self._source_id

    async def load_skills(self) -> list[Skill]:
        """Read all .md files from the directory, parse as skills."""
        return await asyncio.to_thread(self._load_skills_sync)

    def _load_skills_sync(self) -> list[Skill]:
        """Synchronous skill loading (run in a thread to avoid blocking the event loop)."""
        if not self._path.is_dir():
            logger.warning("Skill source path does not exist: %s", self._path)
            return []

        skills = []
        for md_file in self._path.rglob("*.md"):
            # Skip dot-directories
            relative = md_file.relative_to(self._path)
            if any(part.startswith(".") for part in relative.parts[:-1]):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("Failed to read %s: %s", md_file, e)
                continue

            skill = parse_skill_file(content, str(relative), self.source_id)
            if skill is not None:
                skills.append(skill)

        return skills

    async def read_file(self, relative_path: str) -> str | None:
        """Read a file relative to the source directory.

        Dot-directory paths are excluded for security (consistent with discovery).
        """
        # Block access to dot-directories for consistency with load_skills filtering
        parts = Path(relative_path).parts
        if any(part.startswith(".") for part in parts[:-1]):
            logger.debug("Blocked read_file for dot-directory path: %s", relative_path)
            return None
        target = self._path / relative_path
        if not target.is_file():
            return None
        try:
            return target.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read referenced file %s: %s", target, e)
            return None


class LocalSampleSource:
    """Searches code samples in a local directory."""

    def __init__(self, path: str, name: str):
        self._path = Path(path)
        self._name = name

    @property
    def source_id(self) -> str:
        return f"local:{self._name}"

    async def search(self, query: str) -> list[tuple[str, str, float]]:
        """Search files for query matches using case-insensitive substring matching."""
        return await asyncio.to_thread(self._search_sync, query)

    def _search_sync(self, query: str) -> list[tuple[str, str, float]]:
        """Synchronous search (run in a thread to avoid blocking the event loop)."""
        if not self._path.is_dir():
            logger.warning("Sample source path does not exist: %s", self._path)
            return []

        results: list[tuple[str, str, float]] = []
        query_lower = query.lower()
        query_terms = query_lower.split()

        for file_path in self._path.rglob("*"):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(self._path)
            if any(part.startswith(".") for part in relative.parts):
                continue
            # Skip binary files by extension
            if file_path.suffix in {".png", ".jpg", ".gif", ".ico", ".woff", ".ttf"}:
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            score = compute_relevance(content, str(relative), query_terms)
            if score > 0:
                results.append((str(relative), content, score))

        results.sort(key=lambda r: r[2], reverse=True)
        return results
