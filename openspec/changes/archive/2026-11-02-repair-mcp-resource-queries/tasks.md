## Implementation Tasks

- [x] Inspect actual deployed Afterglow and native provider logs for the observed storage and Waygate MCP failures; record exact release/source and distinguish root causes.
- [x] Measure current instance, volume, network, container and database query fields, limits and related-resource coverage using source plus read-only live MCP evidence.
- [x] Record current create/manage support and missing operations for the five required resource families; do not represent existing partial support as complete CRUD.
- [x] Fix confirmed storage inventory defects with strict project/parent ownership preserved and installed-SDK HTTP regressions.
- [x] Fix confirmed Waygate inventory defects or identify the exact native policy/config prerequisite without bypassing authority. Deployed0.3.5 exchanges delegated tokens; the existing sibling local WIP already uses original-token inspection and passed source qualification. Preserve WIP and deployed-line ancestry before any future release.
- [x] Run focused regression selectors, related MCP targets and real changed-path HTTP/SDK smoke; separate synthetic native boundaries from live deployment acceptance. Storage105, MCP597/125deselected + frontend167, nativeWaygate22 and standalone TCP/SDK smoke passed.
- [x] Update existing architecture, API/testing docs and changelog with the exact query contract, failure causes and evidence.
- [x] Complete architecture checks and archive this repair only after its source deliverables and scoped verification are finished; record any unperformed production rollout explicitly. Working source9f4149e5/3942files, untouched staged guard, full supported-Python gate exit0 (backend12440/94skip, frontend6446/502files, contract183, realDB167) passed. Source-only archive; publication/rollout remain excluded by explicit user choice.

## Scope decision and remaining boundaries

The user explicitly selected source fixes/verification only; production publication/rollout, native policy/DB/key/grant changes and cloud resource mutations are excluded. Existing storage filter failures are repaired in source, not on the live server. Cinder default-policy backup-owner omission remains fail-closed. Existing Waygate inspection WIP is not an ancestry-compatible released candidate. The five-resource full-CRUD goal is not met by this repair: network/container/database create and richer read fields/cursors remain absent and are explicitly inventoried in docs/api/auth.md.
