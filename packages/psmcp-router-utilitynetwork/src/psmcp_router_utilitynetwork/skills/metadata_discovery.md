# Metadata Discovery Workflow

You are guiding the user through exploring utility network structure and metadata.

## Steps

1. **Orient to the network:**
   Call `network_get_metadata(section="domain_networks")` to discover:
   - Available domain networks (Electric, Gas, Water, etc.)
   - Tier hierarchy within each domain
   - Topology type (radial vs. mesh)

2. **Discover asset types (if needed):**
   Call `network_get_metadata(section="asset_types")` with optional filters:
   - `domain_network` — narrow to a specific domain (e.g., "Electric")
   - `source_name` — narrow to a specific source (e.g., "ElectricDevice")

3. **Discover network attributes (if the user asks about trace functions or propagators):**
   Call `network_get_metadata(section="network_attributes")` to see what attributes
   are available for trace functions (Sum, Count, Min, Max) and propagators.

4. **Discover categories (if identifying service points, protective devices, controllers):**
   Call `network_get_metadata(section="categories")` to see which asset types belong
   to categories like "Service Point", "Protective", "Subnetwork Controller".

5. **Discover terminal configurations (if working with multi-terminal devices):**
   Call `network_get_metadata(section="terminal_configurations")` for details on
   terminal traversability and directionality.

6. **Discover topology rules (if diagnosing connectivity issues):**
   Call `network_get_metadata(section="topology_rules")` to understand valid
   connection patterns between sources.

7. **Discover propagators (if understanding how values flow):**
   Call `network_get_metadata(section="propagators")` for attribute propagation
   configuration (phase propagation, status propagation, etc.).
