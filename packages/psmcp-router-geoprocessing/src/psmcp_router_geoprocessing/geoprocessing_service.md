# Geoprocessing Service Module

## Overview

The `geoprocessing_service.py` module enables AI applications to discover and execute ArcGIS Geoprocessing (GP) services dynamically through the MCP (Model Context Protocol) server. It provides a lightweight catalog for service discovery, detailed parameter retrieval, and unified sync/async task execution — all scoped to the authenticated user's portal permissions.

Only GP services tagged with **"MCP"** (or **"mcp"**) in the ArcGIS Portal are included. This gives administrators control over which GP services participate in the MCP workflow.

---

## Design Decision: What alternatives considered and Why the Hybrid Approach Selected

Three architectural approaches were evaluated for GP service discovery and execution. Each was assessed against two competing goals: ensuring the AI always knows what GP capabilities exist (awareness), and keeping the AI's context window efficient (cost).

### Approach 1: Tool-Only

In this approach, a single tool (`get_gp_catalog`) would return the full catalog — service names, descriptions, and complete parameter schemas — on demand.

**Pros:**
- Context window stays clean until the AI decides to call the tool.
- No upfront cost for non-GP questions like "what's the weather in Dover?"

**Cons:**
- The AI must decide *when* to call the discovery tool, which depends on recognizing the user's question as a geoprocessing problem. This creates a **"discovery gap"** — the AI might fail to check for GP capabilities when the user's question warrants it, because it doesn't know those capabilities exist.
- Relies entirely on the tool description and system prompt to guide the AI's decision, which is fragile for edge cases.

**Outcome:** Rejected. The discovery gap is a fundamental flaw — the AI cannot reliably decide to look for something it doesn't know exists.

### Approach 2: Resource-Only (Full Catalog)

In this approach, a single dynamic resource would return the complete catalog including full parameter schemas for every task, loaded into the AI's context at session start.

**Pros:**
- The AI always knows what GP tasks exist and how to call them — zero ambiguity.
- No extra tool call needed before execution.

**Cons:**
- The full catalog (with all parameter schemas) consumes significant context window space on every request, regardless of whether the user's question involves geoprocessing.
- Context cost scales with the number of GP services and tasks the user has access to. For organizations with many published GP services, this could crowd out space for actual conversation and results.

**Outcome:** Rejected. Context cost scales unpredictably with catalog size and is wasted on non-GP requests.

### Approach 3: Hybrid — Lightweight Resource + Detail Tool (Selected)

The selected approach splits discovery into two tiers:

1. A **lightweight dynamic resource** provides service names, descriptions, URLs, and task descriptions — enough for the AI to know *what's available* without consuming excessive context.
2. A **detail tool** (`get_gp_task_details`) retrieves full parameter schemas on demand — only when the AI has selected a task and needs to know *how to call it*.

**Pros:**
- Eliminates the discovery gap: the AI always sees the catalog resource and knows GP capabilities exist.
- Context-efficient: only lightweight metadata is loaded upfront; full schemas are fetched on demand for the selected task only.
- Generic: works for organizations with 5 GP services or 50, without requiring tuning.

**Cons:**
- Adds one extra tool call (to `get_gp_task_details`) before execution, compared to the full-resource approach.

**Outcome:** Selected. Balances awareness with context efficiency, and the extra tool call is a minor tradeoff for scalability.

---

## Components

### Resources

#### `gp_catalog`

| Property | Value |
|---|---|
| **URI** | `resource://analysis/gp-catalog` |
| **Type** | Dynamic (per session) |
| **Authentication** | Resolved from MCP auth context via `resolve_token()` |
| **MIME Type** | `application/json` |

**Purpose:** Provides the AI with a lightweight overview of all GP services and tasks the user can access. MCP clients typically read resources at session start, so the AI always has this catalog in context without needing to call a tool.

**Discovery mechanism:** Searches the ArcGIS Portal for items of type `"Geoprocessing Service"` that are tagged with `"MCP"` or `"mcp"`. For each matching item, crawls the GPServer endpoint to extract task names and descriptions.

**Return structure:**

```json
{
  "total_services": 3,
  "catalog": [
    {
      "service_name": "SuitabilityAnalysis",
      "service_description": "Land suitability modeling tools",
      "service_url": "https://server/arcgis/rest/services/SuitabilityAnalysis",
      "tasks": [
        {
          "task_name": "FindSuitableSites",
          "task_description": "Identifies areas meeting specified criteria"
        }
      ]
    }
  ],
  "elapsed_time": 2.34
}
```

> **Note:** The catalog intentionally excludes parameter details (input schemas, data types, defaults, choice lists) to keep the context window footprint small. Use `get_gp_task_details` for full parameter schemas.

---

#### `gp_job_statuses`

| Property | Value |
|---|---|
| **URI** | `resource://analysis/gp-job-statuses` |
| **Type** | Static |
| **Authentication** | None required |
| **MIME Type** | `application/json` |

**Purpose:** Reference resource listing all possible GPServer job status values and their meanings. Useful for the AI to interpret status responses from `check_gp_job_status`.

**Job status values:**

| Status | Meaning |
|---|---|
| `esriJobSubmitted` | Job has been submitted to the server |
| `esriJobWaiting` | Job is waiting for available resources |
| `esriJobExecuting` | Job is currently being executed |
| `esriJobSucceeded` | Job completed successfully |
| `esriJobFailed` | Job failed during execution |
| `esriJobTimedOut` | Job exceeded the maximum execution time |
| `esriJobCancelling` | Job is being cancelled |
| `esriJobCancelled` | Job was cancelled |

**Terminal states** (job is complete): `esriJobSucceeded`, `esriJobFailed`, `esriJobTimedOut`, `esriJobCancelled`

---

### Tools

#### `get_gp_task_details`

Retrieves the full parameter schema for a specific GP task. This is the bridge between the lightweight catalog (which tells the AI *what* exists) and execution (which requires knowing *how* to call a task).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_url` | `str` | Yes | Base URL of the GP service (from catalog resource) |
| `task_name` | `str` | Yes | Name of the task (from catalog resource) |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |

**Returns:**

| Field | Description |
|---|---|
| `task_name` | Name of the task |
| `task_description` | Description of what the task does |
| `execution_type` | `esriExecutionTypeSynchronous` or `esriExecutionTypeAsynchronous` |
| `input_parameters` | List of inputs, each with: `name`, `description`, `data_type`, `default_value`, `required`, `choice_list` |
| `output_parameters` | List of outputs, each with: `name`, `description`, `data_type` |

The `execution_type` value returned here must be passed to `execute_gp_task` so it knows whether to call the synchronous `/execute` endpoint or the asynchronous `/submitJob` endpoint.

---

#### `execute_gp_task`

Submits a GP task for execution. Handles both synchronous and asynchronous tasks based on the `execution_type` parameter.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `gp_service_url` | `str` | Yes | Base URL of the GP service |
| `task_name` | `str` | Yes | Name of the task to execute |
| `parameters` | `Dict[str, Any]` | Yes | Input parameters matching the task's schema |
| `execution_type` | `str` | No | `"esriExecutionTypeSynchronous"` or `"esriExecutionTypeAsynchronous"` (default) |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |

**Synchronous return:**

```json
{
  "results": [...],
  "messages": [...],
  "elapsed_time": 5.12
}
```

**Asynchronous return:**

```json
{
  "jobId": "j1234567890abcdef",
  "jobStatus": "esriJobSubmitted",
  "message": "Job submitted successfully. Use check_gp_job_status to monitor progress.",
  "elapsed_time": 0.45
}
```

**Timeout behavior:**
- Synchronous tasks: 300-second timeout (task runs to completion).
- Asynchronous tasks: 30-second timeout (only covers the job submission, not execution).

> **Note:** For asynchronous tasks, the tool does not poll for completion. The AI must use `check_gp_job_status` and `get_gp_job_results` separately.

---

#### `check_gp_job_status`

Polls the current status of a previously submitted asynchronous GP job.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `gp_service_url` | `str` | Yes | Base URL of the GP service |
| `task_name` | `str` | Yes | Name of the task |
| `job_id` | `str` | Yes | Job ID returned by `execute_gp_task` |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |

**Returns:** `jobId`, `jobStatus`, `messages`, and `results` (if available).

Only needed for asynchronous jobs. Synchronous tasks return results directly from `execute_gp_task`.

---

#### `get_gp_job_results`

Retrieves the output values from a completed asynchronous GP job.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `gp_service_url` | `str` | Yes | Base URL of the GP service |
| `task_name` | `str` | Yes | Name of the task |
| `job_id` | `str` | Yes | Job ID of the completed job |
| `token` | `str` | No | Authentication token. Falls back to auth context if omitted. |

**Returns:** `jobId`, `jobStatus`, `results` (output parameter values), and `messages`.

Should only be called after `check_gp_job_status` confirms the job has reached a terminal state (typically `esriJobSucceeded`).

---

### Prompt

#### `gp_task_execution_prompt`

A system prompt template that guides the AI through the GP task execution workflow. This prompt is registered with FastMCP and can be referenced by AI applications to configure the AI's behavior.

**Workflow described in the prompt:**

1. Check the GP catalog resource (`resource://analysis/gp-catalog`) to find the best matching task.
2. Call `get_gp_task_details` to retrieve the full parameter schema.
3. Call `execute_gp_task` to submit the job, passing the `execution_type` from step 2.
4. For asynchronous jobs only: call `check_gp_job_status` to monitor progress.
5. For asynchronous jobs only: call `get_gp_job_results` to retrieve output values.

The prompt instructs the AI to never guess task names or parameter names — always use values from the catalog resource and `get_gp_task_details`.

---

## AI Workflow

```
User asks a geospatial analysis question
        │
        ▼
┌─────────────────────────────┐
│  GP Catalog Resource        │  ◄── AI application already has this in context
│  (lightweight: names,       │
│   descriptions, URLs)       │
└──────────────┬──────────────┘
               │ AI application selects the best matching task
               ▼
┌─────────────────────────────┐
│  get_gp_task_details        │  ◄── Tool call: full parameter schema
│  (inputs, outputs, types,   │
│   defaults, choice_list,    │
│   execution_type)           │
└──────────────┬──────────────┘
               │ AI application constructs valid parameters
               ▼
┌─────────────────────────────┐
│  execute_gp_task            │  ◄── Tool call: submit for execution
│  (sync → results directly)  │
│  (async → job ID)           │
└──────────────┬──────────────┘
               │
       ┌───────┴───────┐
       │ Sync          │ Async
       ▼               ▼
   Done ✓       check_gp_job_status
                       │
                       ▼
                get_gp_job_results
                       │
                       ▼
                   Done ✓
```

---

## Authentication

All tools and the catalog resource accept an optional `token` parameter. If not provided, the token is resolved automatically from the MCP authentication context using `resolve_token()`. This function uses Python's `contextvars`, ensuring that each concurrent request gets its own token — safe for multi-client scenarios where different users connect to the same MCP server simultaneously.

---

## MCP Tag Filtering

The catalog resource only discovers GP services that are tagged with **"MCP"** or **"mcp"** in the ArcGIS Portal. This is an intentional design choice that gives portal administrators explicit control over which GP services are exposed to AI applications.

To include a GP service in the MCP workflow, add the tag `MCP` to the service item in the portal. To exclude it, remove the tag.

Portal search query used:
```
type:"Geoprocessing Service" AND (tags:"MCP" OR tags:"mcp")
```

---

## Helper Functions

The module includes eight internal helper functions that handle the low-level HTTP interactions with ArcGIS REST APIs:

| Function | Purpose |
|---|---|
| `_search_gp_services` | Portal search for GP service items with MCP tag, with pagination |
| `_crawl_gp_service` | Extract service metadata and task list from a GPServer endpoint |
| `_fetch_task_description` | Lightweight task description for the catalog |
| `_fetch_task_details` | Full parameter schema retrieval (inputs, outputs, execution type) |
| `_submit_gp_job` | Submit an asynchronous job via `/submitJob` |
| `_execute_gp_task_sync` | Execute a synchronous task via `/execute` |
| `_check_job_status` | Poll job status from the jobs endpoint |
| `_get_job_results` | Retrieve output parameter values from a completed job |
