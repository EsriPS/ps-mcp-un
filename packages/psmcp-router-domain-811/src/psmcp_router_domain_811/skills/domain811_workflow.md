# 811 Dig-Ticket Analysis Workflow

This skill guides the Domain 811 agent through analyzing a dig ticket against the
ArcGIS Utility Network.

## Goal

Determine which network assets a proposed dig may impact and assign a risk level.

## Steps

1. Confirm the ticket carries a georeferenced dig area with parseable geometry.
2. Analyze the ticket with `domain811_analyze_ticket` to obtain `impacted_assets`
   and a `risk` level.
3. Report `impacted_assets` and `risk` (one of `low`, `medium`, `high`).

## Rules

- Reject tickets that lack a georeferenced dig area or have unparseable geometry;
  return an error indication with no partial results.
