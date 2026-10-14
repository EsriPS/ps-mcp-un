# PS-MCP Eval Harness

Measures whether the MCP server's own **tool docstrings, resources, and skills** are
sufficient to steer a *generic, unharnessed agent* to consistent, correct results —
without any task-specific system prompt.

It answers three questions per prompt (the "sufficiency" criteria):

1. **Discovery** — does the agent find and pull the right guidance (resources / skills /
   prompts) before acting?
2. **Correct following** — does it call the right tools with the right arguments and
   arrive at the one correct answer?
3. **Consistency** — are results identical across repeated, independent runs?

## Design

- The agent is **unharnessed**: it gets only a bare "you are an agent, here are your
  tools" system prompt. All domain guidance must come from the MCP server itself
  (docstrings, `resources/list` + `resources/read`, `prompts/list` + `prompts/get`).
- Each run is a **fresh MCP session** with no memory carryover.
- Each prompt has exactly **one canonical answer** so correctness is objective.
- Every prompt is run **N times** (default 5) so consistency is measurable.

## Files

| File | Purpose |
|------|---------|
| `prompts.yaml` | Test prompts + expected answers + expected discovery targets |
| `config.py` | Env-driven config (server URL, token, model, repeats) |
| `mcp_agent.py` | Bare MCP-connected agent loop (tool calling, resource pull) |
| `runner.py` | Runs the suite, writes JSONL traces to `results/` |
| `score.py` | Computes discovery / correctness / consistency and prints a report |

## Setup

The harness uses the `fastmcp` client (already a project dependency) plus an LLM
provider. Install the eval extras:

```bash
uv sync --all-packages --all-extras --all-groups
uv pip install openai      # if not already present
```

## Configuration

Set via environment (or an `.env` you point `--env-file` at):

| Var | Meaning | Default |
|-----|---------|---------|
| `EVAL_MCP_URL` | MCP server URL | `https://bnundev.esri.com/psmcp` |
| `EVAL_MCP_TOKEN` | Bearer token for the server | (required) |
| `EVAL_MODEL` | LLM model id | `gpt-4o` |
| `EVAL_REPEATS` | Runs per prompt | `5` |
| `OPENAI_KEY` / `OPENAI_BASE_URL` | LLM provider creds | — |
| `AZURE_OPENAI` | `true` to use Azure client | `false` |

> The token is sensitive. The harness never writes the token into trace files.

## Run

```bash
# 1. Run the suite (writes results/run-<timestamp>.jsonl)
uv run python evals/runner.py

# 2. Score the latest run
uv run python evals/score.py

# Score a specific run file
uv run python evals/score.py results/run-20260929-101500.jsonl
```

## Interpreting results

- **discovery_rate** — fraction of runs that pulled every `expects.discovery` target.
- **correctness_rate** — fraction of runs whose final answer matched `expects.answer`.
- **consistency** — for each prompt, agreement across the N runs (1.0 = identical).

Low consistency with high per-run correctness means the docs work but leave room for
divergent paths. Low discovery with low correctness points at guidance that agents
never load — a docs/metadata discoverability problem, not a content problem.
