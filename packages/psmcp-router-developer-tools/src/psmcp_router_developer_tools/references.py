"""Contained, bounded Markdown reference expansion for published instructions."""

import posixpath
import re
from collections import deque
from pathlib import PurePosixPath

from psmcp_router_developer_tools.models import Skill
from psmcp_router_developer_tools.parsing import find_relative_references
from psmcp_router_developer_tools.sources.base import SkillSource

MAX_REFERENCE_DEPTH = 8
_LINK = re.compile(r"!?\[([^\]]*)\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+['\"].*?['\"])?\s*\)")
_DEFINITION = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", re.MULTILINE)


def _links(content: str) -> list[tuple[str, str]]:
    return [
        (match[1], match[2].removeprefix("<").removesuffix(">"))
        for pattern in (_LINK, _DEFINITION)
        for match in pattern.finditer(content)
    ]


def _relative_path(current: str, reference: str) -> str:
    if any(char in reference for char in ("\\", ":", "%", "?", "\x00")) or reference.startswith(
        "/"
    ):
        raise ValueError(f"Unsafe skill reference: {reference!r}")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(current), reference))
    if path == ".." or path.startswith("../"):
        raise ValueError(f"Skill reference escapes its document directory: {reference!r}")
    if any(part.startswith(".") for part in PurePosixPath(path).parts):
        raise ValueError(f"Hidden skill reference is unsupported: {reference!r}")
    if not path.endswith(".md"):
        raise ValueError(
            f"Unsupported local skill asset: {reference!r}; only Markdown is delivered"
        )
    return path


async def resolve_references(skill: Skill, source: SkillSource) -> list[dict]:
    """Expand references through eight edges; strict agent bundles fail atomically.

    Untagged developer documents retain immediate path spelling and explicit errors.
    Agent reference paths are relative to the root document, never the source root.
    """
    strict = bool({"agent-runtime", "agent-system"} & set(skill.metadata.tags))
    root = PurePosixPath(skill.file_path)
    # The client mounts the body as SKILL.md. A differently named source file
    # linked by a cycle still needs to be delivered as a reference alias.
    seen = {root.name.casefold(): root.name} if root.name.casefold() == "skill.md" else {}
    queue = deque([(root.name, skill.content, 0)])
    results = []
    while queue:
        current, body, depth = queue.popleft()
        for label, reference in _links(body) if strict else find_relative_references(body):
            if reference.startswith(("https://", "#")):
                continue
            path = _relative_path(current, reference)
            key = path.casefold()
            if key in seen:
                if seen[key] != path:
                    raise ValueError(f"Case-colliding skill reference: {path}")
                continue
            if key == "skill.md":
                raise ValueError("Reference collides with virtual SKILL.md")
            if depth >= MAX_REFERENCE_DEPTH:
                if strict:
                    raise ValueError(f"Skill reference depth exceeds {MAX_REFERENCE_DEPTH}: {path}")
                results.append({"label": label, "path": path, "error": "Reference depth exceeds 8"})
                continue
            source_path = str(root.parent / path)
            validate = getattr(type(source), "validate_reference", None)
            if validate is not None:
                validate(source, skill.file_path, source_path)
            content = await source.read_file(source_path)
            if content is None:
                if strict:
                    raise ValueError(f"Could not resolve required skill reference: {path}")
                results.append(
                    {
                        "label": label,
                        "path": reference if depth == 0 else path,
                        "error": "Could not resolve reference",
                    }
                )
                continue
            seen[key] = path
            results.append(
                {
                    "label": label,
                    "path": reference if not strict and depth == 0 else path,
                    "content": content,
                }
            )
            queue.append((path, content, depth + 1))
    return results
