# Customer Data Discovery Workflow

You are discovering the customer data source before calling workflow tools.

## Why This is Needed

Customer data layer names and join fields are NEVER standardized. Each utility uses different naming, schemas, and relationships. You MUST discover and verify before passing config to workflow tools.

## Steps

1. **Probe the FeatureServer for layers and tables:**
   Call `get_service_or_layer_details(endpoint_url="{UTILITY_NETWORK_URL}")` (no layer ID).
   - Examine ALL layers AND tables in the response
   - Look for names/aliases containing: CIS, customer, account, subscriber, consumer, ratepayer, billing, meter, service

2. **Sample promising candidates:**
   For each candidate, call `get_sample_feature_layer_data(endpoint_url="{URL}/{layerId}")`.
   - Inspect field names and sample values
   - Look for fields that could join to service point features

3. **Identify the relationship type:**
   - **Direct join:** A shared field exists on both the service point layer and the customer table (e.g., `meter_id` on both)
   - **Intermediate table:** An intermediary sits between them (meter → account → customer). You must identify both links.
   - **Spatial proximity:** No key relationship; match by address/coordinate (last resort)

4. **Verify the join:**
   - Get a sample service point value: `query_feature_layer(endpoint_url="{service_point_layer}", parameters={"where": "1=1", "outFields": "globalid,meter_id", "resultRecordCount": "3"})`
   - Test against the candidate: `query_feature_layer(endpoint_url="{customer_layer}", parameters={"where": "meter_id = '{value}'"})`
   - If results come back: the join works

5. **Confirm with the user:**
   Present: "I found a customer table at [URL] that joins to service points via the `meter_id` field. Sample match: meter M-1234 → Customer John Smith. Shall I use this?"

6. **Use the discovered config:**
   After confirmation, pass `customer_layer_url` and `customer_join_field` to subsequent resolution steps (e.g., when following the Downstream Customer Impact or Spatial Impact skill).

## Common Join Patterns

| Pattern | Service Point Field | Customer Field |
|---------|-------------------|----------------|
| Meter ID | `meter_id` | `meter_id`, `meter_number` |
| Account | `account_number` | `account_no`, `acct_num` |
| GlobalID | `GlobalID` | `service_point_globalid` |
| Premise | `premise_id` | `premise_id`, `prem_id` |

## If No Customer Data Found

- Report trace results without customer resolution
- Explain what was searched
- Ask if the user knows where customer data is stored
