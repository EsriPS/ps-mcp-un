"""YAML front matter parsing and reference resolution."""

import logging
import re
from pathlib import PurePosixPath

from psmcp_router_developer_tools.models import Skill, SkillMetadata

logger = logging.getLogger(__name__)

# Regex for YAML front matter delimited by ---
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Regex for relative markdown links: [label](path.md)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Split a markdown file into front matter dict and body.

    Args:
        text: Raw file content.

    Returns:
        Tuple of (front_matter_dict, body_text).
        Returns ({}, full_text) if no valid front matter found.
    """
    import yaml  # lazy import to keep module load fast

    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text

    yaml_str = match.group(1)
    body = text[match.end() :]

    try:
        fm = yaml.safe_load(yaml_str)
        if not isinstance(fm, dict):
            return {}, text
        return fm, body
    except yaml.YAMLError as e:
        logger.warning("Invalid YAML front matter: %s", e)
        return {}, text


def parse_skill_file(content: str, file_path: str, source_id: str) -> Skill | None:
    """Parse a markdown file into a Skill object.

    Args:
        content: Raw file content.
        file_path: Relative path within the source.
        source_id: Identifier of the source this file came from.

    Returns:
        Skill object, or None for ordinary Markdown/non-agent files without names.

    Raises:
        ValueError: Frontmatter is malformed or agent metadata violates the contract.
    """
    fm, body = parse_front_matter(content)

    if not fm:
        if content.startswith("---"):
            raise ValueError(f"Invalid skill front matter: {file_path}")
        logger.warning("Skipping %s: no valid front matter", file_path)
        return None

    tags = _merge_tags(fm)
    agent_tags = {"agent-runtime", "agent-system"} & set(tags)
    requires_tools = fm.get("requires_tools", [])
    if not isinstance(requires_tools, list) or any(
        not isinstance(tool, str) or not tool.strip() for tool in requires_tools
    ):
        raise ValueError(f"Invalid requires_tools in {file_path}: expected string array")
    if agent_tags:
        if len(agent_tags) > 1:
            raise ValueError(f"Skill cannot be both agent-runtime and agent-system: {file_path}")
        if (
            not isinstance(fm.get("name"), str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fm["name"])
            or len(fm["name"]) > 64
        ):
            raise ValueError(f"Invalid agent skill name: {file_path}")
        if (
            not isinstance(fm.get("description"), str)
            or not fm["description"].strip()
            or len(fm["description"]) > 1024
        ):
            raise ValueError(f"Invalid agent skill description: {file_path}")
    raw_name = fm.get("name", "")
    name = str(raw_name).strip() if raw_name is not None else ""
    if not name:
        logger.warning("Skipping %s: empty name field", file_path)
        return None

    description = fm.get("description", "")

    metadata = SkillMetadata(
        name=name,
        description=description,
        tags=tags,
        source_id=source_id,
        requires_tools=requires_tools,
    )
    return Skill(metadata=metadata, content=body, file_path=file_path)


def _merge_tags(fm: dict) -> list[str]:
    """Merge and normalize tags from front matter.

    Combines top-level 'tags' and 'metadata.tags', deduplicates,
    and normalizes to lowercase.
    """
    raw_tags: list[str] = []

    top_tags = fm.get("tags")
    if isinstance(top_tags, list):
        raw_tags.extend(str(t) for t in top_tags)
    elif isinstance(top_tags, str):
        raw_tags.append(top_tags)

    metadata = fm.get("metadata")
    if isinstance(metadata, dict):
        meta_tags = metadata.get("tags")
        if isinstance(meta_tags, list):
            raw_tags.extend(str(t) for t in meta_tags)
        elif isinstance(meta_tags, str):
            raw_tags.append(meta_tags)

    # Normalize and deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def find_relative_references(content: str) -> list[tuple[str, str]]:
    """Find relative .md file references in skill content.

    Args:
        content: Markdown body text.

    Returns:
        List of (label, relative_path) tuples for .md links.
    """
    refs = []
    for match in _MD_LINK_RE.finditer(content):
        label = match.group(1)
        path = match.group(2)
        # Only include relative paths (not http:// or absolute)
        if not path.startswith(("http://", "https://", "/")):
            refs.append((label, path))
    return refs


def resolve_reference_path(skill_file_path: str, reference: str) -> str:
    """Resolve a relative reference path against the skill file's directory.

    Args:
        skill_file_path: The skill file's path within the source.
        reference: The relative path from the markdown link.

    Returns:
        Resolved path relative to the source root.
    """
    skill_dir = PurePosixPath(skill_file_path).parent
    resolved = skill_dir / reference
    # Normalize path segments (resolve .. and .)
    parts: list[str] = []
    for part in resolved.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return str(PurePosixPath(*parts)) if parts else "."
