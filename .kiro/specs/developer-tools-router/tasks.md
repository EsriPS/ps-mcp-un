# Implementation Plan: Developer Tools Router

## Overview

Implement the `psmcp-router-developer-tools` package as a PS-MCP router plugin exposing four MCP tools (`list_skills`, `get_skill`, `list_sample_sets`, `get_sample`) with dual source support (GitHub repositories and local filesystem). The implementation follows the project's router conventions with Python 3.13, FastMCP v3, httpx for HTTP, and hypothesis for property-based testing.

## Tasks

- [x] 1. Set up package structure and configuration
  - [x] 1.1 Create package scaffolding with pyproject.toml and module layout
    - Create `packages/psmcp-router-developer-tools/pyproject.toml` with dependencies (ps-mcp, httpx, pyyaml) and entry point
    - Create `src/psmcp_router_developer_tools/__init__.py` exporting `developer_tools_router` and `__version__`
    - Create `src/psmcp_router_developer_tools/_version.py` placeholder
    - Create `src/psmcp_router_developer_tools/sources/__init__.py`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 1.2 Implement configuration module (`config.py`)
    - Implement `GITHUB_TOKEN`, `CACHE_TTL_MINUTES` module-level constants from env vars
    - Implement `load_skill_sources()` parsing `DEVTOOLS_SKILL_SOURCES` JSON env var
    - Implement `load_sample_sources()` parsing `DEVTOOLS_SAMPLE_SOURCES` JSON env var
    - Handle invalid JSON gracefully with logging and empty list return
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 1.3 Implement data models (`models.py`)
    - Create frozen dataclasses: `SkillMetadata`, `Skill`, `SkillSummary`, `SampleSetConfig`, `SampleSetSummary`, `SampleResult`
    - _Requirements: 1.1, 2.1, 3.1, 4.1_

  - [x] 1.4 Implement TTL cache (`cache.py`)
    - Implement `TTLCache` class with `get()`, `set()`, `clear()` methods
    - Use `time.monotonic()` for expiration tracking
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 1.5 Write property test for cache TTL expiration
    - **Property 4: Cache TTL expiration**
    - **Validates: Requirements 1.7, 7.1, 7.2, 7.3**

- [x] 2. Implement parsing and source protocol
  - [x] 2.1 Implement YAML front matter parsing (`parsing.py`)
    - Implement `parse_front_matter()` to split markdown into YAML dict and body
    - Implement `parse_skill_file()` to produce `Skill` objects from raw content
    - Implement `_merge_tags()` for lowercase deduplication of tags from multiple locations
    - Implement `find_relative_references()` to extract relative `.md` links
    - Implement `resolve_reference_path()` for path resolution against skill file directory
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 2.2_

  - [ ]* 2.2 Write property test for invalid skill file rejection
    - **Property 3: Invalid skill files are rejected**
    - **Validates: Requirements 1.6, 6.3**

  - [ ]* 2.3 Write property test for front matter parsing round-trip
    - **Property 9: Front matter parsing round-trip**
    - **Validates: Requirements 6.1**

  - [ ]* 2.4 Write property test for tag merging invariants
    - **Property 10: Tag merging produces lowercase deduplicated union**
    - **Validates: Requirements 6.2**

  - [ ]* 2.5 Write property test for relative markdown reference extraction
    - **Property 6: Relative markdown reference extraction**
    - **Validates: Requirements 2.2**

  - [x] 2.6 Implement source protocol (`sources/base.py`)
    - Define `SkillSource` protocol with `source_id`, `load_skills()`, `read_file()` methods
    - Define `SampleSource` protocol with `source_id`, `search()` method
    - _Requirements: 1.3, 1.4, 4.2, 4.3_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement source backends
  - [x] 4.1 Implement local filesystem source (`sources/local.py`)
    - Implement `LocalSkillSource` with `load_skills()` reading `.md` files recursively, skipping dot-directories
    - Implement `LocalSkillSource.read_file()` for reference resolution
    - Implement `LocalSampleSource` with `search()` using case-insensitive substring matching
    - Implement `_compute_relevance()` scoring function with path and content term matching
    - _Requirements: 1.4, 1.5, 4.3_

  - [ ]* 4.2 Write property test for dot-directory exclusion
    - **Property 2: Dot-directory exclusion**
    - **Validates: Requirements 1.5**

  - [ ]* 4.3 Write property test for search results ordering
    - **Property 7: Search results are ordered by relevance**
    - **Validates: Requirements 4.1**

  - [x] 4.4 Implement GitHub source (`sources/github.py`)
    - Implement `GitHubSkillSource` with tree API fetching, raw content fetching, and cache integration
    - Implement `GitHubSkillSource.read_file()` with caching for reference resolution
    - Implement `GitHubSampleSource` with search over fetched repo content
    - Implement `_parse_github_url()` and `_is_dot_directory()` helpers
    - Use `httpx.AsyncClient` with 30s timeout and Bearer token auth
    - _Requirements: 1.3, 1.5, 1.7, 4.2, 5.3, 5.7, 7.1_

  - [ ]* 4.5 Write unit tests for GitHub source
    - Test URL parsing for various GitHub URL formats
    - Test auth header construction with and without token
    - Test dot-directory filtering logic
    - Mock httpx responses for tree fetch and file content fetch
    - Test 401/403/404 handling
    - _Requirements: 1.3, 1.5, 5.7_

- [x] 5. Implement registries and service layer
  - [x] 5.1 Implement skill and sample registries (`registry.py`)
    - Implement `SkillRegistry` with lazy loading, tag filtering, case-insensitive name lookup
    - Implement `SampleRegistry` with sample set listing and delegated search
    - _Requirements: 1.1, 1.2, 2.1, 2.3, 3.1, 4.1, 4.4_

  - [ ]* 5.2 Write property test for tag filtering subset
    - **Property 1: Tag filtering returns exact matching subset**
    - **Validates: Requirements 1.2**

  - [ ]* 5.3 Write property test for case-insensitive skill lookup
    - **Property 5: Skill lookup by name is case-insensitive**
    - **Validates: Requirements 2.1**

  - [x] 5.4 Implement service with tool definitions (`service.py`)
    - Implement `developer_tools_router` FastMCP instance
    - Implement `list_skills` tool with optional tag filtering
    - Implement `get_skill` tool with reference resolution and error handling
    - Implement `list_sample_sets` tool with empty-config message
    - Implement `get_sample` tool with search delegation and error handling
    - Wire up registry builders from config module
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 4.1, 4.4, 4.5_

  - [ ]* 5.5 Write property test for JSON config parsing round-trip
    - **Property 8: JSON config parsing round-trip**
    - **Validates: Requirements 5.1, 5.2, 5.5, 5.6**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integration tests and wiring
  - [x] 7.1 Write integration tests for local source end-to-end
    - Test full skill loading from a tmp_path directory with real markdown files
    - Test sample search across a tmp_path directory with code files
    - Test dot-directory exclusion with real filesystem structure
    - Test binary file skipping in sample search
    - _Requirements: 1.4, 1.5, 4.3_

  - [ ]* 7.2 Write integration tests for GitHub source with mocked httpx
    - Test tree fetch and skill loading with mocked GitHub API responses
    - Test cache hit/miss behavior across multiple calls
    - Test 401 error handling for private repos without token
    - _Requirements: 1.3, 1.7, 5.7, 7.1, 7.2_

  - [ ]* 7.3 Write integration tests for full tool invocations
    - Test `list_skills` with and without tag filters using mocked sources
    - Test `get_skill` with reference resolution using mocked sources
    - Test `list_sample_sets` with empty and populated configs
    - Test `get_sample` with valid and invalid sample set names
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 4.1, 4.4, 4.5_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All tests go under `packages/psmcp-router-developer-tools/tests/`
- Use `respx` for httpx mocking and `tmp_path` fixture for filesystem tests
- Run tests with `uv run pytest packages/psmcp-router-developer-tools/tests/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4", "2.6"] },
    { "id": 2, "tasks": ["1.5", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["4.5", "5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4", "5.5"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
