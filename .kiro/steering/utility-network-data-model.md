---
inclusion: manual
---

# Utility Network Data Model Guidance

This document teaches you how to resolve ambiguous user references to specific utility network data model elements and interpret coded attribute values.

---

## Core Rule: NEVER Assume Asset Group or Type

You MUST NOT assume you know the exact asset group, asset type, or layer name for any user-provided term. Utility network configurations vary significantly between deployments. Always verify against live metadata before constructing queries.

**Wrong approach:** User says "transformer" → assume asset group code 4, type code 1
**Correct approach:** User says "transformer" → call `network_get_metadata(section="asset_types")` → search results → present matches → confirm with user

---

## Core Rule: NEVER Return Unresolved Codes to the User

You MUST resolve all asset group codes and asset type codes to their human-readable names before presenting results to the user. Raw numeric codes are meaningless to users.

- If trace results contain `assetGroupCode` / `assetTypeCode` without corresponding names: call `network_get_metadata(section="asset_types")` to look up the names before reporting.
- If using `network_named_trace` (which returns raw elements): cross-reference element codes against `sourceMapping` and the asset types metadata to produce readable names.
- NEVER present output like "assetGroup 4, assetType 12" — always resolve to "Distribution Transformer, Three Phase Pad Mounted" (or whatever the names are).

---

## Metadata Section Reference

At the start of any utility network session, orient yourself by calling `network_get_metadata(section="domain_networks")` to discover available domain networks, tiers, topology type, and tier groups.

The `network_get_metadata(section)` tool exposes 7 focused views of the utility network schema:

| Section | What It Returns | When to Use |
|---------|-----------------|-------------|
| `domain_networks` | Domain networks with tiers, topology type, tier groups, subnetwork definitions | Session start; orienting to the network structure; determining tier hierarchy |
| `asset_types` | Asset groups and types with numeric codes, categories, terminal config IDs (filterable by `domain_network`, `source_name`) | Disambiguating user terms ("transformer", "switch"); getting codes for queries; identifying what's in a source layer |
| `network_attributes` | Network attributes with data type, domain, usage type, apportionability | Understanding what attributes are available for trace functions, propagators, and conditions; interpreting globalFunctionResults |
| `terminal_configurations` | Terminal configs with terminal names, IDs, traversability paths, directionality | Understanding multi-terminal devices when `network_device_terminals` returns a config you need more detail on |
| `categories` | Network categories with their member asset types across all domains | Identifying which asset types are "Service Point", "Protective", "Subnetwork Controller" — useful for understanding trace filtering |
| `topology_rules` | Connectivity rules, edge-junction rules, containment rules | Understanding valid connection patterns; diagnosing why features can't connect |
| `propagators` | Network attribute propagators (bitwise, max, min, etc.) | Understanding how attribute values (e.g., phases, status) flow through the network during traces |

### User Question → Section Mapping

| User Asks About | Fetch Section |
|-----------------|---------------|
| "What types of transformers exist?" | `asset_types` (filter by source) |
| "What tiers/voltages does this network have?" | `domain_networks` |
| "What attributes can I use in a trace function?" | `network_attributes` |
| "How many terminals does this device type have?" | `terminal_configurations` |
| "What counts as a protective device?" | `categories` |
| "Why can't this device connect to that line?" | `topology_rules` |
| "How do phases propagate through the network?" | `propagators` |
| "What load attribute should I sum?" | `network_attributes` |
| "Is this network radial or meshed?" | `domain_networks` |
| "What's a subnetwork controller?" | `categories` |

---

## Three Levels of the Data Model

### 1. Layer (Network Source)

The utility network contains multiple layers/sources:
- **Junction sources:** Devices, Junctions, Assemblies
- **Edge sources:** Lines, SubnetworkLine
- **Junction-Edge sources:** (rare)

Each source has a unique `networkSourceId`. Use `network_get_metadata(section="asset_types")` to see all sources and their contents.

### 2. Asset Group

Within each source, features are organized by asset group (e.g., "Transformer", "Switch", "Service Point"). Asset groups have numeric codes that vary by deployment. Asset Groups are implemented as Subtypes in the geodatabase.

### 3. Asset Type

Within each asset group, features are further classified by asset type (e.g., under "Transformer": "Step Down", "Pad Mounted", "Single Phase"). Asset types also have deployment-specific numeric codes. These are implemented as coded value domains at the subtype (asset group) level.

### 4. Property Resolution

All network properties for an object are defined against the resolved asset group and asset type combination. Schema properties are discovered by probing the feature layer properties at the subtype level.

---

## Disambiguation Strategy

When a user references a network asset by common name:

### Step 1: Search Metadata

```
network_get_metadata(section="asset_types", domain_network="Electric", source_name="ElectricDevice")
```

> **Note:** Some utility networks have unnamed sources (empty `sourceName`). When `source_name` is provided, the tool also matches sources containing asset groups whose names include the filter term. If the filter returns empty results, omit `source_name` and browse the full results by `domain_network` only.

### Step 2: Match and Filter

Look for asset groups/types whose names contain or relate to the user's term.

### Step 3: Present Options

If multiple matches exist, present them to the user:

> "I found several transformer types in your network:
> - Asset Group 'Distribution Transformer' (code 4):
>   - Type 'Single Phase' (code 1)
>   - Type 'Three Phase' (code 2)
> - Asset Group 'Station Transformer' (code 5):
>   - Type 'Step Up' (code 1)
>   - Type 'Step Down' (code 2)
> Which one are you interested in?"

### Step 4: Use Codes in Filters

Once confirmed, use the numeric CODES (not descriptions) in all query filters:
```
query_feature_layer(parameters={"where": "assetgroup = 4 AND assettype = 1"})
```

---

## Common Term Hints (NOT Source of Truth)

These are HINTS to guide your metadata search. NEVER use them directly — always verify:

| Common Term | Likely Source | Search For |
|-------------|--------------|------------|
| transformer | ElectricDevice | "transformer" in asset group names |
| switch | ElectricDevice | "switch" in asset group names |
| fuse | ElectricDevice | "fuse" in asset group names |
| recloser | ElectricDevice | "recloser" in asset group/type names |
| pole | StructureJunction | "pole" or "structure" |
| conductor | ElectricLine | "conductor" or "line" in asset group names |
| service point | ElectricDevice or ElectricJunction | "service" in asset group names |
| meter | ElectricDevice | "meter" in asset group/type names |
| capacitor | ElectricDevice | "capacitor" in asset group names |
| regulator | ElectricDevice | "regulator" in asset group names |

---

## Data Quality Warnings

- Billing address ≠ service address — a customer's mailing address won't locate their service point.
- Customer records may be stale and lag behind network changes.
- A single premise may have multiple service points (multi-meter installations), and a single customer may have multiple premises.

---

## Subtype Domain Resolution

### Manual Resolution for Direct Queries

When using `query_feature_layer` directly on utility network layers, results contain raw coded values. To interpret these:

1. **Option A:** Call `network_resolve_coded_values` with the features and layer URL — returns features with coded fields replaced by `{"code": N, "label": "Human Name"}`.
2. **Option B:** Inspect the layer metadata via `get_service_or_layer_details` to see subtype definitions and domain mappings.

### How Subtypes Work

- Each layer has a `subtypeField` (e.g., `assetgroup`)
- Each subtype value maps to different domain assignments for different fields
- The same field code may mean different things for different subtypes
- Domain resolution must be subtype-aware

---

## Detailed Workflows

For step-by-step workflows (customer discovery, address resolution, trace interpretation), use the corresponding MCP prompts.
