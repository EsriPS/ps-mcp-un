"""Skill and sample registries that coordinate sources."""

import logging

from psmcp_router_developer_tools.models import (
    SampleResult,
    SampleSetConfig,
    SampleSetSummary,
    Skill,
    SkillSummary,
)
from psmcp_router_developer_tools.sources.base import SampleSource, SkillSource

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Manages skill loading and lookup across multiple sources.

    Delegates caching to individual sources (e.g., GitHubSkillSource uses
    TTLCache, LocalSkillSource always reads fresh). Each call to list/get
    re-fetches from sources, allowing TTL-based refresh to take effect.
    """

    def __init__(self, sources: list[SkillSource]):
        self._sources = sources

    async def _load_all(self) -> tuple[list[Skill], dict[str, tuple[Skill, SkillSource]]]:
        """Load skills from all sources (sources handle their own caching)."""
        skills: list[Skill] = []
        by_name: dict[str, tuple[Skill, SkillSource]] = {}
        for source in self._sources:
            try:
                loaded = await source.load_skills()
                for skill in loaded:
                    skills.append(skill)
                    by_name[skill.metadata.name.lower()] = (skill, source)
            except Exception as e:
                logger.error("Failed to load skills from %s: %s", source.source_id, e)
        return skills, by_name

    async def list_skills(self, tags: list[str] | None = None) -> list[SkillSummary]:
        """List all skills, optionally filtered by tags.

        Args:
            tags: Optional list of tags to filter by. Returns skills matching
                  at least one of the specified tags. Case-insensitive.

        Returns:
            List of SkillSummary objects for matching skills.
        """
        skills, _ = await self._load_all()

        filter_tags = {t.lower() for t in tags} if tags else None
        results = []
        for skill in skills:
            if filter_tags and not any(t in filter_tags for t in skill.metadata.tags):
                continue
            results.append(
                SkillSummary(
                    name=skill.metadata.name,
                    description=skill.metadata.description,
                    tags=skill.metadata.tags,
                    source=skill.metadata.source_id,
                )
            )
        return results

    async def get_skill(self, name: str) -> tuple[Skill, SkillSource] | None:
        """Look up a skill by name (case-insensitive).

        Args:
            name: The skill name to look up.

        Returns:
            Tuple of (Skill, SkillSource) if found, None otherwise.
        """
        _, by_name = await self._load_all()
        return by_name.get(name.lower())

    async def get_available_names(self) -> list[str]:
        """Return all loaded skill names.

        Returns:
            List of skill names as originally defined in their metadata.
        """
        skills, _ = await self._load_all()
        return [s.metadata.name for s in skills]


class SampleRegistry:
    """Manages sample set lookup and search."""

    def __init__(self, configs: list[SampleSetConfig], sources: dict[str, SampleSource]):
        self._configs = configs
        self._sources = sources  # keyed by sample set name

    def list_sample_sets(self) -> list[SampleSetSummary]:
        """List all configured sample sets.

        Returns:
            List of SampleSetSummary objects for all configured sets.
        """
        return [
            SampleSetSummary(
                name=cfg.name,
                source_type=cfg.source_type,
                languages=cfg.languages,
                apis=cfg.apis,
            )
            for cfg in self._configs
        ]

    async def search(self, sample_set_name: str, query: str) -> list[SampleResult] | None:
        """Search within a named sample set.

        Args:
            sample_set_name: Name of the sample set to search.
            query: Search query string.

        Returns:
            List of SampleResult objects, or None if sample set not found.
        """
        source = self._sources.get(sample_set_name)
        if source is None:
            return None

        raw_results = await source.search(query)
        return [
            SampleResult(file_path=path, content=content, relevance_score=score)
            for path, content, score in raw_results
        ]

    def get_available_names(self) -> list[str]:
        """Return all configured sample set names.

        Returns:
            List of sample set names from configuration.
        """
        return [cfg.name for cfg in self._configs]
