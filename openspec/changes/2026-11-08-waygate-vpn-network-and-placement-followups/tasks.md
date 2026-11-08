# Tasks: waygate-vpn-network-and-placement-followups

- [x] Write deadline: proxy upstream read 55 s for Waygate writes, client `timeoutMs` 58 s, timeout/502/503/504 -> "unconfirmed" + list refresh (tests: `test_waygate_proxy_deadline.py`, `contracts/test_waygate_proxy.py`, `WaygateWorkspace.test.ts`).
- [x] Root cause of dead gateway agent established read-only: image `waygate-gateway:0.1.4` oneshot agent + prebuilt cloud-init that writes no agent files; HTTPS callback and security group are fine.
- [x] Waygate (separate repo, branch `feat/agent-diagnostics-0.3.8`, commits `7b73cb2`, `ff3eaee` on 0.3.7): prebuilt mode installs the current agent and removes the stale timer; server-side telemetry + `GET /v1/servers/{id}/diagnostics`; agent failure diagnostics; per-attachment `allowed_ips` (+ migration 008 backfill `[cidr]`, PATCH route, `waygate:network:update`); shared/external attach; `expected_clients` + flavor tiers (`waygate.flavor_large`). Full suite 1,619 passed.
- [x] Afterglow: agent diagnostics panel + VM console log; provider/shared network attach; AllowedIPs input/edit; owner default empty with self-registration and claim-then-download; expected-client field; in-app guide (9 locales).
- [x] Afterglow: Waygate-managed gateway/security-group lock (REST + MCP + UI), `waygate_managed` payload field (option 2 of the placement decision).
- [x] Afterglow: per-domain VPN reserved ranges (migration 109, manager + admin routes, enforcement on tenant/admin/MCP network and subnet creation, UI).
- [x] Docs: ARCHITECTURE.md, CHANGELOG.md, docs/testing.md, docs/api, architecture stamp.
- [ ] NOT DONE: tag/release/deploy Waygate 0.3.8 (apply migration 008 first; optionally set `waygate.flavor_large`; add `waygate:network:update` to operator policy files), then deploy Afterglow. Afterglow must follow Waygate because the UI always sends `expected_clients`.
- [ ] NOT DONE: recreate `dsa` (or build a 0.3.x gateway image); existing VMs keep the stale agent.
- [ ] NOT DONE: live verification (client becomes a WireGuard peer, diagnostics verdict ok, provider network attach, reserved range refusal) and browser verification of the new UI.
- [ ] NOT DONE: option 1 (central `waygate-service` project in the Default domain with cross-project attach), server-side claim-on-download for members without client-edit permission, usage-scheduler/project-cleanup lock review, `npm run test:gate`, commit, archive.
