## 1. Connections workspace (MCP and tools)

- [x] Browse / Connected (N) / Manage tabs with deep-linkable state, single search, server-side `access` and `state` filters.
- [x] Compact two-column catalogue rows (monogram tile, name, access badge, one-line description, primary action) grouped into Featured, Built-in sandbox tools and All catalogue with server pagination.
- [x] Connected table: status mark, name, scope (personal/organization/admin-public), access state, tool count, manage action; expandable tool list; activation and OAuth actions unchanged.
- [x] Manage tab: remote MCP server form, Afterglow MCP approval, sandbox selection summary and organization notes. Tools tab: custom HTTP tools list and add dialog.
- [x] Preserve existing permission, consent, activation-version, stale-response and sandbox-selection behavior and tests; nine locales.

## 2. Isometric grid view

- [ ] Shared engine under `frontend/src/lib/components/iso/` (projection, grid floor, block/platform/edge primitives, flow packets, pan/zoom, legend, keyboard focus, reduced motion).
- [ ] Network topology page: grid view as default, lane/canvas preserved; selection opens the existing detail panels.
- [x] Instance network section: grid view of ports, networks, floating IPs and security-group ingress/egress; list view keeps editing.
- [x] Waygate VPN: grid view of server, peers, tunnel and attached networks; list view keeps management.
- [ ] DESIGN.md and ARCHITECTURE.md updated; nine locales.

## 3. Verification

- [ ] Focused component tests, isolated `npm run test:gate`, desktop/mobile and dark/light browser proof.
