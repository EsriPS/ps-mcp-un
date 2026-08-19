# Geoprocessing module

The `geoprocessing` router handles ArcGIS GP service discovery and task execution. Its workflow is: discover services/tasks, inspect the selected task schema, execute the task, then monitor or fetch results.

## Route name

`geoprocessing`

## Tools

1. `gp_catalog` — discover accessible geoprocessing services and their tasks from the portal.
2. `get_gp_task_details` — fetch the full parameter schema for a specific task.
3. `execute_gp_task` — execute a GP task in synchronous or asynchronous mode.
4. `check_gp_job_status` — check the current status of an asynchronous GP job.
5. `get_gp_job_results` — retrieve output/result URLs for a completed GP job.

## Resource

- `resource://analysis/gp-job-statuses`

This resource returns the known ArcGIS job status values and their terminal states.

## Prompt

- `gp_task_execution_prompt`

## Configuration

- `ARCGIS_PORTAL_URL` — required for `gp_catalog`
- `GP_CATALOG_DEFAULT_TAGS` — optional default tag filter for GP service discovery
- `ARCGIS_TOKEN` — optional fallback token

## Notes

- `execute_gp_task` expects the `execution_type` returned by `get_gp_task_details`.
- `gp_catalog` crawls portal search results to build a lightweight service/task catalog.
- In the current implementation, SSL verification is hard-coded off inside `geoprocessing_service.py` (`VERIFY_SSL = False`).
- `list_system_services` is not part of this router; it lives in the `arcgis` router.

## Related docs

- [`geoprocessing_service.md`](geoprocessing_service.md)
