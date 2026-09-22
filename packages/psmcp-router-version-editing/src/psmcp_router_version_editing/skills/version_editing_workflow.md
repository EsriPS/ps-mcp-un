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

Use `version_edit_summary` at any time for a read-only snapshot of a branch
version — it returns `features_edited` (features that differ from `default`),
`dirty_areas` (areas awaiting validation), and `error_count` (topology errors),
plus `has_dirty_areas` / `has_errors` flags, without taking control or editing.

`version_reconcile_post` takes a `with_post` flag: `with_post=true` (default)
reconciles then posts (promotes) to `default`; `with_post=false` reconciles only
(brings the branch up to date with `default` without promoting it).

## Rules

- Never edit `default` directly; always work on a branch version.
- Abort the post step if reconcile reports conflicts.
- Escalate to a human when errors remain after the bounded fix attempts.
