"""Developer Tools MCP Router — tool definitions."""

import logging

from fastmcp import FastMCP

from psmcp_router_developer_tools.cache import TTLCache
from psmcp_router_developer_tools.config import (
    CACHE_TTL_MINUTES,
    load_sample_sources,
    load_skill_sources,
)
from psmcp_router_developer_tools.models import SampleSetConfig
from psmcp_router_developer_tools.parsing import (
    find_relative_references,
    resolve_reference_path,
)
from psmcp_router_developer_tools.registry import SampleRegistry, SkillRegistry
from psmcp_router_developer_tools.sources.base import SampleSource
from psmcp_router_developer_tools.sources.github import GitHubSampleSource, GitHubSkillSource
from psmcp_router_developer_tools.sources.local import LocalSampleSource, LocalSkillSource

logger = logging.getLogger(__name__)

developer_tools_router = FastMCP(name="Developer Tools Router")

# --- Initialization (lazy, built on first tool call) ---

_skill_registry: SkillRegistry | None = None
_sample_registry: SampleRegistry | None = None
_cache = TTLCache(ttl_seconds=CACHE_TTL_MINUTES * 60)


def _build_skill_registry() -> SkillRegistry:
    """Construct the skill registry from environment config."""
    sources = []
    for cfg in load_skill_sources():
        src_type = cfg.get("type", "")
        if src_type == "github":
            url = cfg.get("url")
            if not url:
                logger.warning("GitHub skill source missing 'url', skipping: %s", cfg)
                continue
            sources.append(GitHubSkillSource(url=url, cache=_cache))
        elif src_type == "local":
            path = cfg.get("path")
            if not path:
                logger.warning("Local skill source missing 'path', skipping: %s", cfg)
                continue
            sources.append(LocalSkillSource(path=path))
        else:
            logger.warning("Unknown skill source type: %s", src_type)
    return SkillRegistry(sources)


def _build_sample_registry() -> SampleRegistry:
    """Construct the sample registry from environment config."""
    configs: list[SampleSetConfig] = []
    sources: dict[str, SampleSource] = {}
    for cfg in load_sample_sources():
        src_type = cfg.get("type", "")
        name = cfg.get("name", "")
        if not name:
            logger.warning("Sample source missing 'name', skipping")
            continue

        sample_cfg = SampleSetConfig(
            name=name,
            source_type=src_type,
            url=cfg.get("url", ""),
            path=cfg.get("path", ""),
            languages=cfg.get("languages", []),
            apis=cfg.get("apis", []),
        )
        configs.append(sample_cfg)

        if src_type == "github":
            url = cfg.get("url")
            if not url:
                logger.warning("GitHub sample source '%s' missing 'url', skipping", name)
                continue
            sources[name] = GitHubSampleSource(url=url, name=name, cache=_cache)
        elif src_type == "local":
            path = cfg.get("path")
            if not path:
                logger.warning("Local sample source '%s' missing 'path', skipping", name)
                continue
            sources[name] = LocalSampleSource(path=path, name=name)
        else:
            logger.warning("Unknown sample source type: %s", src_type)

    return SampleRegistry(configs, sources)


def _get_skill_registry() -> SkillRegistry:
    """Return the skill registry, building it on first access."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = _build_skill_registry()
    return _skill_registry


def _get_sample_registry() -> SampleRegistry:
    """Return the sample registry, building it on first access."""
    global _sample_registry
    if _sample_registry is None:
        _sample_registry = _build_sample_registry()
    return _sample_registry


# --- Tools ---


@developer_tools_router.tool
async def list_skills(tags: list[str] | None = None) -> dict:
    """List available developer skill documents with optional tag filtering.

    Skills are curated markdown guidance documents with metadata. Use this tool
    to discover what skills are available, optionally filtering by tags.

    Args:
        tags: Optional list of tags to filter by. Returns skills matching
              at least one of the specified tags. Case-insensitive.

    Returns:
        Dict with 'skills' list containing name, description, tags, and source
        for each matching skill.
    """
    registry = _get_skill_registry()
    skills = await registry.list_skills(tags=tags)
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "source": s.source,
            }
            for s in skills
        ],
        "total": len(skills),
    }


@developer_tools_router.tool
async def get_skill(name: str) -> dict:
    """Retrieve the full content of a specific skill by name.

    Returns the complete markdown content including resolved references
    to other .md files linked within the skill.

    Args:
        name: The name of the skill to retrieve (case-insensitive).

    Returns:
        Dict with skill metadata and full content, including any resolved
        references appended as additional sections.
    """
    registry = _get_skill_registry()
    result = await registry.get_skill(name)

    if result is None:
        available = await registry.get_available_names()
        return {
            "error": f"Skill '{name}' not found.",
            "available_skills": available,
        }

    skill, source = result

    # Resolve relative .md references
    references = find_relative_references(skill.content)
    resolved_refs: list[dict] = []
    for label, ref_path in references:
        resolved_path = resolve_reference_path(skill.file_path, ref_path)
        ref_content = await source.read_file(resolved_path)
        if ref_content is not None:
            resolved_refs.append({"label": label, "path": ref_path, "content": ref_content})
        else:
            resolved_refs.append(
                {"label": label, "path": ref_path, "error": "Could not resolve reference"}
            )

    return {
        "name": skill.metadata.name,
        "description": skill.metadata.description,
        "tags": skill.metadata.tags,
        "source": skill.metadata.source_id,
        "content": skill.content,
        "references": resolved_refs,
    }


@developer_tools_router.tool
async def list_sample_sets() -> dict:
    """List configured code sample repositories.

    Returns all configured sample sets with their names, source types,
    and optional metadata (languages, APIs/frameworks).

    Returns:
        Dict with 'sample_sets' list. Returns a message if none configured.
    """
    registry = _get_sample_registry()
    sets = registry.list_sample_sets()
    if not sets:
        return {"sample_sets": [], "message": "No sample sets are configured."}
    return {
        "sample_sets": [
            {
                "name": s.name,
                "source_type": s.source_type,
                "languages": s.languages,
                "apis": s.apis,
            }
            for s in sets
        ],
        "total": len(sets),
    }


@developer_tools_router.tool
async def get_sample(sample_set: str, query: str) -> dict:
    """Search for code samples within a specific sample set.

    Searches the specified sample set for files matching the query,
    returning results ranked by text relevance.

    Args:
        sample_set: Name of the sample set to search.
        query: Search query (space-separated terms for keyword matching).

    Returns:
        Dict with search results or error if sample set not found.
    """
    registry = _get_sample_registry()
    results = await registry.search(sample_set, query)

    if results is None:
        available = registry.get_available_names()
        return {
            "error": f"Sample set '{sample_set}' not found.",
            "available_sample_sets": available,
        }

    if not results:
        return {"results": [], "query": query, "sample_set": sample_set}

    return {
        "results": [
            {"file_path": r.file_path, "content": r.content, "relevance_score": r.relevance_score}
            for r in results
        ],
        "total": len(results),
        "query": query,
        "sample_set": sample_set,
    }
