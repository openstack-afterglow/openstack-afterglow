## Implementation Tasks

- [x] Implement process-owned native HTTP pools with request-local auth/session/cookie/header/discovery state, TLS/proxy isolation and unchanged retry/timeout behavior.
- [x] Integrate all native Keystone/SDK/MCP factories and drain-before-close API/worker lifecycle cleanup.
- [x] Add behavior regressions for connection reuse, fresh auth and credential/cookie isolation, concurrency, TLS partitioning, errors/no mutation replay and shutdown ownership.
- [x] Run real installed SDK HTTP smoke and exact selectors followed by auth/access/worker targets; record full-gate scope honestly.
- [x] Update architecture, authentication/testing docs and changelog; verify architecture guard without changing shared index; archive completed change.
