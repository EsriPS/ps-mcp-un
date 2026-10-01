---
name: utility-network-customer-data-discovery
description: Discover customer tables and verify relationships to service-point features before resolving trace impacts.
tags: [agent-runtime, utility-network, customers, metadata]
requires_tools: [get_service_or_layer_details, get_sample_feature_layer_data, query_feature_layer]
---

# Customer Data Discovery

Customer schemas are deployment-specific. Do not assume a fixed CIS table,
layer number, meter field, or relationship.

1. Inspect all layers and tables on the intended FeatureServer using
   `get_service_or_layer_details(endpoint_url=...)`. Names suggesting customer,
   account, subscriber, billing, premise, or meter data are discovery hints.
2. Inspect candidate schemas and relationships, then use
   `get_sample_feature_layer_data(endpoint_url=...)` for a small sample where
   authorized. Minimize personal information shown in chat.
3. Determine whether the join is direct, through an intermediate table, or
   unresolved. Possible keys include meter, account, premise, or service-point
   GlobalID fields, but verify both field names and data types.
4. Use `query_feature_layer(endpoint_url=..., parameters=...)` to test a known
   service-point key against the candidate. Read field names from metadata,
   escape string literal quotes, and check one-to-many behavior and missing keys.
   A single matching sample does not prove complete coverage.
5. Present the verified source and relationship for confirmation. Retain
   `customer_layer_url`, service-point layer, and both join-field names as workflow
   context; these are not invented arguments to trace tools.

If no reliable relationship exists, explain what was inspected and request the
missing data definition. Spatial/address proximity is a tentative match requiring
confirmation, not a substitute for a verified customer relationship. Keep trace
results available independently of customer resolution.
