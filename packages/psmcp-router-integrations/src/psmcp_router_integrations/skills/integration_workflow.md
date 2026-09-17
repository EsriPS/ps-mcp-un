# Integration Transform & Mapping Workflow

This skill guides the Integrations agent through validating a field mapping and
transforming an exported subnetwork JSON into an external schema.

## Goal

Produce a transformed output that conforms to an external target schema, or abort
cleanly on invalid input.

## Steps

1. Validate the field map against a sample export with `integration_validate_mapping`.
2. If the mapping is valid, transform the export with `integration_transform_subnetwork`.
3. Report the `output_path`, `record_count`, and `target_format`.

## Rules

- An empty/zero-record input produces a zero-record output (not an error).
- Malformed JSON or an incompatible mapping aborts with no partial output.
