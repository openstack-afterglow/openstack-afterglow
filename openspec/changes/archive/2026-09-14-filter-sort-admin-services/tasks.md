## Implementation Tasks

- [x] Review existing services page loading graph, filter patterns, and design primitives
- [x] Add shared service list state, filter/sort helpers, and UTC timestamp parsing
- [x] Add ServiceListControls and ServiceSortHeader using shared primitives
- [x] Wire per-tab view state into ServiceTabPanel, ServiceTable, NetworkAgentTable, EndpointsTable, StoragePoolsList
- [x] Add unit/component regressions for combined filters, sorting, refresh preservation, and empty-state distinction
- [x] Verify in the real Vite-served admin services route across 390/767/768/1023/1024/1510px and light/dark
- [x] Update ARCHITECTURE.md, docs/api/admin.md, CHANGELOG.md, and stamp architecture review
- [x] Run final targeted tests, svelte-check, and architecture guard
- [x] Verify the Docker-served UI against authenticated live services: 51 Network rows, down-only filtering, Host sort, tab-switch and refresh persistence
- [x] Run the complete test gate: backend 2729, frontend 1301, contracts 124, functional 24; backend lint/format passed
