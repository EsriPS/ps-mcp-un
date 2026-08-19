"""Data models for the developer-tools router."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillMetadata:
    """Parsed front matter metadata for a skill file."""

    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    source_id: str = ""


@dataclass(frozen=True)
class Skill:
    """A complete skill with metadata and content."""

    metadata: SkillMetadata
    content: str
    file_path: str  # relative path within the source


@dataclass(frozen=True)
class SkillSummary:
    """Lightweight skill info returned by list_skills."""

    name: str
    description: str
    tags: list[str]
    source: str


@dataclass(frozen=True)
class SampleSetConfig:
    """Configuration for a sample set source."""

    name: str
    source_type: str  # "github" or "local"
    url: str = ""  # GitHub repo URL (for github type)
    path: str = ""  # Local directory path (for local type)
    languages: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SampleSetSummary:
    """Summary info returned by list_sample_sets."""

    name: str
    source_type: str
    languages: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SampleResult:
    """A single code sample search result."""

    file_path: str
    content: str
    relevance_score: float = 0.0
