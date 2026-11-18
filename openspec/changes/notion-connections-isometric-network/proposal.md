## Why

The Lumen chat settings MCP and tools tabs stack a gallery, sandbox tools, three connection groups, an 896-entry catalogue and two forms on one long page, so users cannot quickly see what is connected or find a service. Network information for instances, the project topology and the Waygate VPN is shown as tables or flat lanes, which makes reachability, security-group exposure and tunnel paths hard to read.

## What Changes

- Reorganize the MCP and tools settings into a connections workspace modeled on familiar app-connection settings: "Browse", "Connected (N)" and "Manage" tabs, one search field, server-side type/state filters, compact two-column catalogue rows with monogram tiles, and a separate connected table with explicit status marks and a manage action. Existing permissions, OAuth consent, activation versioning, organization authority and sandbox tool selection stay unchanged.
- Add an isometric grid view (third-person, grid floor, block nodes, network platforms, routed links with flow packets) as the default view for the instance network/security-group section, the network topology page and the Waygate VPN workspace. Existing list/lane/canvas views remain one toggle away and keep all mutating controls.
- The visual language follows Afterglow semantic and topology tokens in dark and light themes; it is an original design, not a copy of any reference site.
- Let admins recover ERROR instances whose live migration failed and was verifiably rolled back to the source host (production `librechat`): a `live_migration_rolled_back` scenario gated by fail-closed Nova, Placement, Neutron binding and Cinder attachment evidence; a server-generated plan fingerprint bound to the confirmation; a per-server Redis lease; one HARD reboot from ERROR for stopped guests or a state reset only for running guests; Nova re-read before every write; no replay of ambiguous writes; and an observed final state rather than request acceptance.

## Non-goals

- No Lumen, schema, configuration or permission change. The only backend change is the admin instance recovery scenario and its existing admin-only endpoints. Catalogue categories/icons are not invented; filters use the server's existing `access` and `state` parameters.
- No editing in the isometric view; cable/link creation stays in the canvas view and port/security-group edits stay in the instance list view.
