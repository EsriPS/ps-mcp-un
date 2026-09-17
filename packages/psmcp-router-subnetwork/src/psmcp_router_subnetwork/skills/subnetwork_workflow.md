# Subnetwork Update & Export Workflow

This skill guides the SubNetwork agent through recomputing and exporting a
subnetwork on an ArcGIS Utility Network.

## Goal

Keep a subnetwork current and export its contents to a JSON file for downstream
integrations.

## Steps

1. Discover available subnetworks with `subnetwork_list` (optionally filter by
   `domain_network` and `tier`).
2. Recompute the subnetwork with `subnetwork_update` on the appropriate
   `version_ref` (branch or `default`).
3. Export the subnetwork to JSON with `subnetwork_export_json`, providing an
   `export_path` the process can write to.

## Rules

- Do not leave a partial file if the export path is unwritable; abort and report
  an error instead.
- Prefer running the update before an export when the subnetwork is dirty.
