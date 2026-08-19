# psmcp-router-developer-tools

PS-MCP router plugin exposing developer productivity tools as MCP tools. Provides access to curated skill documents and code sample sets from GitHub repositories and local filesystem directories.

## Tools

| Tool | Description |
|------|-------------|
| `list_skills` | List available skill documents with optional tag filtering |
| `get_skill` | Retrieve a specific skill's full content by name |
| `list_sample_sets` | List configured code sample repositories |
| `get_sample` | Search for code samples within a sample set |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEVTOOLS_SKILL_SOURCES` | No | `""` | JSON array of skill source configs |
| `DEVTOOLS_SAMPLE_SOURCES` | No | `""` | JSON array of sample set configs |
| `GITHUB_TOKEN` | No | `None` | GitHub API token for private repos |
| `DEVTOOLS_CACHE_TTL_MINUTES` | No | `60` | Cache TTL for GitHub content (minutes) |

## Source Configuration

### Skill Sources (`DEVTOOLS_SKILL_SOURCES`)

```json
[
  {"type": "github", "url": "https://github.com/owner/repo"},
  {"type": "local", "path": "/path/to/skills"}
]
```

### Sample Sources (`DEVTOOLS_SAMPLE_SOURCES`)

```json
[
  {"type": "github", "name": "my-samples", "url": "https://github.com/owner/repo", "languages": ["python"], "apis": ["arcgis"]},
  {"type": "local", "name": "local-samples", "path": "/path/to/samples", "languages": ["python"], "apis": ["arcgis"]}
]
```
