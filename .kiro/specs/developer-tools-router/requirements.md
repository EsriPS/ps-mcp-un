# Requirements Document

## Introduction

The developer-tools router is a new PS-MCP router plugin (`psmcp-router-developer-tools`) that exposes developer productivity tools as MCP tools. It provides access to curated skill documents and code sample sets from both GitHub repositories and local filesystem directories. This router ports and extends the functionality of the existing Go-based ps-codex-mcp server into the PS-MCP Python ecosystem, adding local filesystem support as a first-class source type.

## Glossary

- **Router**: A FastMCP plugin package discovered at startup via Python entry points, exposing MCP tools/resources/prompts.
- **Skill**: A markdown file with YAML front matter containing a name, description, tags, and content body intended to guide LLM behavior.
- **Skill_Source**: A configured origin (GitHub repository or local directory) from which skills are loaded.
- **Sample_Set**: A configured repository or local folder containing code samples, identified by a unique name.
- **Front_Matter**: YAML metadata block delimited by `---` at the top of a markdown file.
- **Reference_Resolution**: The process of resolving relative markdown file references within a skill's content and appending the referenced file content to the response.
- **GitHub_Source**: A skill or sample source backed by a GitHub repository, accessed via the GitHub REST API using httpx.
- **Local_Source**: A skill or sample source backed by a local filesystem directory.
- **Cache**: An in-memory time-based cache for GitHub-fetched content, controlled by a configurable TTL.
- **Tag_Filter**: An optional list of tags used to narrow skill listing results to only skills matching at least one specified tag.

## Requirements

### Requirement 1: List Skills

**User Story:** As a developer using an LLM client, I want to list available skills with optional tag filtering, so that I can discover relevant guidance documents for my current task.

#### Acceptance Criteria

1. WHEN the list_skills tool is invoked without tag filters, THE Developer_Tools_Router SHALL return all skills from all configured Skill_Sources with each skill's name, description, tags, and source identifier.
2. WHEN the list_skills tool is invoked with one or more tag filters, THE Developer_Tools_Router SHALL return only skills whose tags (normalized to lowercase, merged from top-level and metadata.tags) contain at least one of the specified filter tags.
3. WHEN a Skill_Source is a GitHub_Source, THE Developer_Tools_Router SHALL fetch skill files via the GitHub REST API using httpx with the configured GITHUB_TOKEN.
4. WHEN a Skill_Source is a Local_Source, THE Developer_Tools_Router SHALL read skill files directly from the configured filesystem path.
5. WHEN loading skills, THE Developer_Tools_Router SHALL ignore files in dot-directories (directories whose names start with a dot, such as `.git/` or `.github/`).
6. IF a skill file is missing Front_Matter, has invalid YAML, or has an empty name field, THEN THE Developer_Tools_Router SHALL skip that file and log a warning with the file path and reason.
7. WHEN GitHub content has been fetched within the configured Cache TTL, THE Developer_Tools_Router SHALL serve the cached content instead of making a new API request.

### Requirement 2: Get Skill

**User Story:** As a developer using an LLM client, I want to retrieve a specific skill's full content by name, so that I can get detailed guidance for a particular topic.

#### Acceptance Criteria

1. WHEN the get_skill tool is invoked with a valid skill name, THE Developer_Tools_Router SHALL return the full markdown content of the matching skill including its front matter metadata.
2. WHEN the skill content contains relative markdown references (links in the form `[label](path.md)` pointing to `.md` files), THE Developer_Tools_Router SHALL resolve those references by reading the referenced files and appending their content in clearly delimited sections.
3. IF the get_skill tool is invoked with a name that does not match any loaded skill, THEN THE Developer_Tools_Router SHALL return a descriptive error indicating the skill was not found and listing available skill names.
4. IF a referenced file cannot be found or read during Reference_Resolution, THEN THE Developer_Tools_Router SHALL include a note in the response indicating the reference could not be resolved, without failing the entire request.

### Requirement 3: List Sample Sets

**User Story:** As a developer using an LLM client, I want to list configured code sample repositories, so that I can discover what sample collections are available to search.

#### Acceptance Criteria

1. WHEN the list_sample_sets tool is invoked, THE Developer_Tools_Router SHALL return all configured Sample_Sets with each set's name, source type, and optional metadata (languages, APIs/frameworks).
2. IF no Sample_Sets are configured, THEN THE Developer_Tools_Router SHALL return an empty list with a message indicating no sample sets are configured.

### Requirement 4: Get Sample

**User Story:** As a developer using an LLM client, I want to search for code samples within a specific sample set, so that I can find relevant code examples for my current task.

#### Acceptance Criteria

1. WHEN the get_sample tool is invoked with a sample set name and a search query, THE Developer_Tools_Router SHALL search within the specified Sample_Set and return matching code samples ranked by text relevance.
2. WHEN the specified Sample_Set is a GitHub_Source, THE Developer_Tools_Router SHALL search the repository contents via the GitHub REST API.
3. WHEN the specified Sample_Set is a Local_Source, THE Developer_Tools_Router SHALL search files in the configured local directory.
4. IF the get_sample tool is invoked with a sample set name that does not match any configured Sample_Set, THEN THE Developer_Tools_Router SHALL return a descriptive error listing available sample set names.
5. IF no samples match the search query, THEN THE Developer_Tools_Router SHALL return an empty results list with the query echoed back.

### Requirement 5: Configuration

**User Story:** As a system administrator, I want to configure skill and sample sources via environment variables, so that I can control which content is available without code changes.

#### Acceptance Criteria

1. THE Developer_Tools_Router SHALL read skill source configuration from the DEVTOOLS_SKILL_SOURCES environment variable as a JSON-encoded list where each entry specifies a type ("github" or "local"), a url (for GitHub) or path (for local), and optional metadata.
2. THE Developer_Tools_Router SHALL read sample set configuration from the DEVTOOLS_SAMPLE_SOURCES environment variable as a JSON-encoded list where each entry specifies a type ("github" or "local"), a name, a url or path, and optional languages and apis fields.
3. THE Developer_Tools_Router SHALL read the GitHub API token from the GITHUB_TOKEN environment variable for authenticating GitHub API requests.
4. THE Developer_Tools_Router SHALL read the cache TTL from the DEVTOOLS_CACHE_TTL_MINUTES environment variable, defaulting to 60 minutes when not set.
5. IF DEVTOOLS_SKILL_SOURCES contains invalid JSON, THEN THE Developer_Tools_Router SHALL log an error and start with an empty skill source list.
6. IF DEVTOOLS_SAMPLE_SOURCES contains invalid JSON, THEN THE Developer_Tools_Router SHALL log an error and start with an empty sample set list.
7. IF a configured GitHub_Source is accessed without a GITHUB_TOKEN and the repository is private, THEN THE Developer_Tools_Router SHALL return a descriptive error indicating authentication is required.

### Requirement 6: Skill File Parsing

**User Story:** As a developer, I want skills to be parsed consistently from markdown files with YAML front matter, so that skill metadata is reliable and predictable.

#### Acceptance Criteria

1. WHEN parsing a skill file, THE Developer_Tools_Router SHALL extract the YAML front matter block delimited by `---` markers and parse the remaining content as the skill body.
2. WHEN a skill file contains tags at the top level and under metadata.tags, THE Developer_Tools_Router SHALL merge both tag lists, deduplicate them, and normalize all tags to lowercase.
3. THE Developer_Tools_Router SHALL require the name field in front matter to be non-empty for a skill to be considered valid.
4. WHEN a skill file contains a description field in front matter, THE Developer_Tools_Router SHALL include that description in list_skills results.

### Requirement 7: Caching

**User Story:** As a system operator, I want GitHub-fetched content to be cached, so that repeated requests do not cause excessive API calls and the router responds quickly.

#### Acceptance Criteria

1. WHEN content is fetched from a GitHub_Source, THE Developer_Tools_Router SHALL store the result in an in-memory cache keyed by source identifier.
2. WHILE the cached content age is less than the configured DEVTOOLS_CACHE_TTL_MINUTES, THE Developer_Tools_Router SHALL serve the cached content for subsequent requests.
3. WHEN the cached content age exceeds the configured TTL, THE Developer_Tools_Router SHALL fetch fresh content from the GitHub API on the next request.
4. THE Developer_Tools_Router SHALL NOT cache content from Local_Sources (local filesystem reads are always fresh).
