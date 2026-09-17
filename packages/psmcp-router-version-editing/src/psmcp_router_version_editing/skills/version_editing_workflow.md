# Version & Editing Workflow

This skill guides the Data Editor and Quality Analyst agents through safe branch
version editing on an ArcGIS Utility Network.

## Goal

Apply edits on an isolated branch version, validate network topology, and only
promote (reconcile/post) a version to `default` when it is clean.

## Steps

1. Create or select a branch version with `version_create_branch` / `version_list_branches`.
2. Take control of the version with `version_take_control` before editing.
3. Apply attribute/geometry edits with `version_apply_edits`.
4. Validate topology over dirty areas with `network_validate_topology`.
5. If `has_errors` is true, apply fixes with `quality_fix_errors` and re-validate.
6. Only when topology is clean, promote with `version_reconcile_post`
   (`abort_if_conflicts=true`).

## Rules

- Never edit `default` directly; always work on a branch version.
- Abort the post step if reconcile reports conflicts.
- Escalate to a human when errors remain after the bounded fix attempts.
