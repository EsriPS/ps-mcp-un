# Data Model Change & Service Admin Workflow

This skill guides the Data Model agent through analyzing and applying a data
model change with the required service stop/start choreography.

## Goal

Apply an approved data model change safely, restarting impacted services whether
the change succeeds or fails.

## Steps

1. Analyze the proposed change with `datamodel_analyze_change` to learn
   `requires_republish` and `impacted_services`.
2. If `requires_republish` is true, do NOT auto-apply; guide the user to
   republish manually.
3. Otherwise: stop impacted services with `serviceadmin_stop_services`.
4. Apply the change with `datamodel_apply_change`.
5. Always restart services with `serviceadmin_start_services`, even if the apply
   step failed.

## Rules

- Only apply when the associated review status is APPROVED.
- Treat a service that does not return to running as a high-severity failure.
