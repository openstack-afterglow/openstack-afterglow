## 1. Connections workspace (MCP and tools)

- [ ] Browse / Connected (N) / Manage tabs with deep-linkable state, single search, server-side `access` and `state` filters.
- [ ] Compact two-column catalogue rows (monogram tile, name, access badge, one-line description, primary action) grouped into Featured, Built-in sandbox tools and All catalogue with server pagination.
- [ ] Connected table: status mark, name, scope (personal/organization/admin-public), access state, tool count, manage action; expandable tool list; activation and OAuth actions unchanged.
- [ ] Manage tab: remote MCP server form, custom HTTP tools list/add dialog, Afterglow MCP approval card.
- [ ] Preserve existing permission, consent, activation-version, stale-response and sandbox-selection behavior and tests; nine locales.

## 2. Isometric grid view

- [x] Shared engine under `frontend/src/lib/components/iso/` (projection, grid floor, block/platform/edge primitives, flow packets, pan/zoom, legend, keyboard focus, reduced motion).
- [x] Network topology page: grid view as default, lane/canvas preserved; selection opens the existing detail panels.
- [ ] Instance network section: grid view of ports, networks, floating IPs and security-group ingress/egress; list view keeps editing.
- [ ] Waygate VPN: grid view of server, peers, tunnel and attached networks; list view keeps management.
- [ ] DESIGN.md and ARCHITECTURE.md updated; nine locales.

## 3. Verification

- [ ] Focused component tests, isolated `npm run test:gate`, desktop/mobile and dark/light browser proof.
