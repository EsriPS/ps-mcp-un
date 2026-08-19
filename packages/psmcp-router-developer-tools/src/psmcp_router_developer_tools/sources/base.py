"""Abstract base for content sources."""

from typing import Protocol

from psmcp_router_developer_tools.models import Skill


class SkillSource(Protocol):
    """Protocol for loading skills from a source."""

    @property
    def source_id(self) -> str: ...

    async def load_skills(self) -> list[Skill]: ...

    async def read_file(self, relative_path: str) -> str | None:
        """Read a file by relative path for reference resolution."""
        ...


class SampleSource(Protocol):
    """Protocol for searching samples in a source."""

    @property
    def source_id(self) -> str: ...

    async def search(self, query: str) -> list[tuple[str, str, float]]:
        """Search for files matching query.

        Returns:
            List of (file_path, content, relevance_score) tuples.
        """
        ...
