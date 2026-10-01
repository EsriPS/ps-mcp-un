# psmcp-router-developer-tools

PS-MCP router plugin exposing curated skill documents and code samples. Skill
sources can be local directories, installed Python packages, or GitHub repositories.

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
  {"type": "local", "path": "C:\\client\\skills"},
  {"type": "package", "package": "psmcp_router_utilitynetwork", "path": "skills"}
]
```

Choose the deployment's collection explicitly; no configuration is an intentional
empty collection. Package sources use `importlib.resources`, not checkout paths.
The package must be installed. A collection owned by a router is hidden when that
router did not successfully mount. Install and enable `developer_tools` to expose
list/get, plus the workflow's dependent routers. Never configure the repository's
`.skills` directory as browser agent policy.

Invalid JSON/configured directories, unreadable or malformed documents, GitHub
failures/truncated trees, and case-insensitive duplicate names are errors, not an
empty or partial success. Local and package sources are reread on each request.
GitHub content follows `DEVTOOLS_CACHE_TTL_MINUTES`.

## Browser runtime delivery contract

Use `list_skills({"tags":["agent-runtime","agent-system"]})` (OR matching), then
`get_skill({"name":"..."})`. Existing list/get keys remain; `requires_tools` is an
optional string array in frontmatter and responses. Only documents whose required
tools are actually mounted on that provider are published. The root server wires
request-scoped `SkillPublicationMiddleware` because FastMCP mounted calls otherwise
see only the child router. Custom FastMCP hosts must add this middleware to their
root before mounting developer-tools; no process-global root pointer is used.
For router-owned package sources, custom hosts must also record successful mount
module names in the root's `_psmcp_mounted_router_packages` set (for example
`{"psmcp_router_utilitynetwork"}`). Without that ownership information, router-owned
package collections are conservatively hidden. The standard PS-MCP host supplies
both pieces automatically.

```yaml
---
name: client-workflow
description: Analyze this deployment's network using its published tools.
tags: [agent-runtime]
requires_tools: [network_named_trace]
---
Follow the [rules](references/rules.md).
```

- Agent names are lower-case ASCII kebab-case (up to 64 characters); descriptions
  are nonempty strings up to 1024 characters.
- Use `agent-runtime` for optional workflows or `agent-system` for always-on
  policy, never both. Browser requirements belong in prose, not `requires_tools`.
- `get_skill.content` is the body without frontmatter. Reconstruct YAML using
  JSON-quoted scalar values from metadata. References are `{label,path,content}`;
  reference paths are relative to the root document.
- Markdown links expand transitively through **eight edges**, with cycle
  deduplication. Keep links inside the skill's directory. Missing references,
  escaping/absolute/drive/backslash/encoded paths, case collisions, and unsupported
  local assets fail for agent-tagged documents. HTTPS citations are not fetched.
  Scripts and binary files are neither mounted nor executed.
- Untagged developer documents retain permissive metadata, original immediate
  reference path spelling, and explicit missing-reference error entries.
- Prefer MCP structured content; otherwise decode the single JSON text block.
  Errors must remain visible. Absence of both list/get tools is distinct from an
  intentional empty collection; advertising only one is a configuration error.

The browser should compose its generic prompt followed by system bodies sorted by
server/skill name, mount runtime documents under `/skills/<name>/SKILL.md`, and
mount system-only documents under `/instructions/<name>/SKILL.md`. Capture tools,
files and instructions as one session snapshot; reload on new chat/reconnect,
invalidate on endpoint/token changes, and never hot-replace an in-flight turn.
Duplicate names across providers are errors. No bundled frontend fallback.

The `tests/fixtures/blue-cats` collection preserves the former demonstration and
all its supporting files. It is intentionally **not** production policy. Its
original untagged document delivers Markdown references only; tagging that exact
fixture `agent-runtime` fails because it links an executable script.

## Validation

From the workspace root, run the local/config/parsing/registry/service suites plus
`tests/test_runtime_publication.py` in this package, and utility-network
`tests/test_canonical_skills.py`. Build with
`uv build --package psmcp-router-developer-tools --wheel`; utility documents ship
in the utility-network wheel. No live ArcGIS service is needed for these tests.

### Sample Sources (`DEVTOOLS_SAMPLE_SOURCES`)

```json
[
  {"type": "github", "name": "my-samples", "url": "https://github.com/owner/repo", "languages": ["python"], "apis": ["arcgis"]},
  {"type": "local", "name": "local-samples", "path": "/path/to/samples", "languages": ["python"], "apis": ["arcgis"]}
]
```
