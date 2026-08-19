# Address to Network Element Resolution Workflow

You are resolving a street address to a utility network feature GlobalID.

## When to Use

When the user provides an address instead of a GlobalID and you need to find the corresponding network feature to trace from.

## Step 1: Ask the User Which Method to Use

Present two options:

> "How would you like me to find the network element for this address?
> 1. **Geocode** — locate the address on the map and find nearby network features by proximity
> 2. **Address field lookup** — search network features or customer records that have address fields matching this address"

- If the user says **geocode** (or doesn't have a preference): proceed to **Path A** below
- If the user says **address field lookup**: proceed to **Path B** below

---

## Path A: Geocode and Spatial Proximity

### A1. Geocode the address

Call `find_address_candidates(single_line="{address}")`.
- Take the highest-scoring candidate
- Note the coordinates (x, y) and spatial reference

### A2. Identify addressable asset types and their layer context

Call `network_get_metadata(section="asset_types")` and search for asset groups/types that represent addressable locations — features that could be linked to a street address.

Look for names containing:
- "service point", "service delivery"
- "premise", "location"
- "meter", "customer"
- "delivery point", "connection point"

Note the `sourceName` and `layerId` of the source(s) containing these asset groups, and their `assetGroupCode`/`assetTypeCode` values.

**Determine the layer structure:**
- **Dedicated layer:** If the addressable asset types are in their own source (e.g., a "ServicePoint" layer), you can query that layer directly without a WHERE filter on asset group/type.
- **Shared layer:** If the addressable asset types are in a shared source alongside other asset groups (e.g., "ElectricDevice" contains both transformers AND service points), you MUST add a WHERE clause filtering by `assetgroup IN ({codes})` and `assettype IN ({codes})` to avoid returning unrelated devices.

If no obvious addressable types exist, fall back to querying device layers broadly.

### A3. Spatial query for nearby addressable features

Query the identified layer(s) with a spatial filter around the geocoded point:

**If dedicated layer (no WHERE needed):**
```
query_feature_layer(
  endpoint_url="{UTILITY_NETWORK_URL}/{layerId}",
  parameters={
    "geometry": "{\"x\": {x}, \"y\": {y}}",
    "geometryType": "esriGeometryPoint",
    "distance": 100,
    "units": "esriSRUnit_Meter",
    "spatialRel": "esriSpatialRelIntersects",
    "outFields": "globalid,assetgroup,assettype",
    "returnGeometry": "false",
    "inSR": "4326"
  }
)
```

**If shared layer (WHERE clause required):**
```
query_feature_layer(
  endpoint_url="{UTILITY_NETWORK_URL}/{layerId}",
  parameters={
    "where": "assetgroup IN ({code1},{code2}) AND assettype IN ({code3},{code4})",
    "geometry": "{\"x\": {x}, \"y\": {y}}",
    "geometryType": "esriGeometryPoint",
    "distance": 100,
    "units": "esriSRUnit_Meter",
    "spatialRel": "esriSpatialRelIntersects",
    "outFields": "globalid,assetgroup,assettype",
    "returnGeometry": "false",
    "inSR": "4326"
  }
)
```

- If no results at 100m: expand distance to 250m, then 500m
- If still no results: broaden the query (remove the WHERE clause or try other device layers)

### A4. Identify and confirm

- If single result: present to user for confirmation
- If multiple results: present options with resolved asset type names
- Prefer service point / meter / premise features over generic devices
- "I found a service point (meter) near 123 Main St with GlobalID {id}. Is this the feature you want to trace from?"

---

## Path B: Address Field Lookup

### B1. Probe network sources for address fields

Call `get_service_or_layer_details(endpoint_url="{UTILITY_NETWORK_URL}")` to list all layers and tables.

For each layer/table that looks like it could contain addressable features (service points, premises, customer tables), call:
```
get_service_or_layer_details(endpoint_url="{UTILITY_NETWORK_URL}/{layerId}")
```

Inspect the `fields` array for address-like fields:
- `streetaddress`, `address`, `street`, `premise_address`
- `city`, `state`, `zip`, `postal`
- `location_description`, `service_address`
- `full_address`, `addr1`

### B2. Query by address value

If address fields are found on a network source layer:
```
query_feature_layer(
  endpoint_url="{UTILITY_NETWORK_URL}/{layerId}",
  parameters={
    "where": "{address_field} LIKE '%{street_number} {street_name}%'",
    "outFields": "globalid,assetgroup,assettype,{address_field}",
    "returnGeometry": "false"
  }
)
```

Use LIKE with wildcards to handle formatting variations. Try progressively looser matches if exact match fails.

### B3. If no address fields on network layers, use Customer Data Discovery

If no network source has address fields, the address may be stored in a customer or premise table. Follow the `utility_network_customer_data_discovery` prompt workflow to:
1. Discover customer/premise tables
2. Identify address fields on those tables
3. Query by address to find the customer/premise record
4. Follow the join relationship back to a service point GlobalID (via meter_id, premise_id, etc.)

### B4. Confirm with user

Present the found feature(s) and confirm before proceeding with the trace workflow.

---

## Important Caveats

- Geocode accuracy varies — rural addresses may be imprecise
- Billing address ≠ service address (P.O. Box, different mailing address)
- Multiple meters may exist at one address (apartments, commercial)
- Address field formatting varies (abbreviations, case, spacing)
- Always confirm the identified feature before tracing
- Present results as approximate when derived from geocoding
