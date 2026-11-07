# Tasks: reduce-auth-chain-latency-and-fix-error-semantics

- [x] Quantify the fixed per-request auth cost from the live report (sequential, no concurrency) and reproduce it with a synthetic latency probe.
- [x] Prefetch independent project/domain reads concurrently in `_accessible_domains` without changing results or error order.
- [x] Measure on real sockets (real native_transport + keystoneclient vs loopback HTTP Keystone, modeled handshake): cap fan-out at 4 and size the shared pool to 32; cap/pool tests mutation-checked.
- [x] Prove the new concurrency test fails without the prefetch (peak in-flight 1) and passes with it.
- [x] Add `auth;dur=` to Server-Timing and test it with the real dependency and middleware.
- [x] Map object listing failures through `native_resource_read_failure` with a warning log; update the one incidental 500 assertion.
- [x] Harness: 401 guard (preflight, single-flight refresh, abort, INVALID rows, budget failure) with tests.
- [x] Scoped-credential negative tests, each mutation-checked (roles dropped from key; lifetime floor removed).
- [x] Correct the stale `user_inventory.py` comment; update ARCHITECTURE.md, CHANGELOG.md, docs/testing.md.
- [x] Run affected backend suites, `npm run lint:backend`, `npm run test:latency`, `npm run test:orchestration` (project Python on PATH).
- [ ] NOT DONE: `npm run test:gate`, live before/after re-measurement, deployment.
