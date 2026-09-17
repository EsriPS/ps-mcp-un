# Outage-Event Analysis Workflow

This skill guides the Domain Outage agent through analyzing an outage event against
the ArcGIS Utility Network.

## Goal

Determine which customers and network assets are affected by a reported outage.

## Steps

1. Confirm the outage event references a locatable, traceable network location.
2. Analyze the event with `domainoutage_analyze_event` to obtain
   `affected_customers` and `affected_assets`.
3. Report `affected_customers` and the `affected_assets` list.

## Rules

- Reject outage events that reference a nonexistent or untraceable location;
  return an error indication with no partial results.
