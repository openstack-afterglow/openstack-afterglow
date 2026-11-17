## Model registry and media
- [x] Keep embedding kind available in discovery/manual/kind-edit flows, with input-token pricing only and no hidden media/output draft.
- [x] Show precise execution blockers consistently in admin registry and image/audio studios.
- [x] Qualify and deploy the optional managed scanner; preserve existing storage and scan failures. (Production 2026-11-17: pinned ClamAV on all three controllers, PONG/VERSION 28186, loopback 3310 only; 1x1 PNG upload→scan→download on each API host.)
- [ ] Smoke registered, priced media/embedding routes within the approved 1 USD budget without inventing prices. (Blocked: production OpenAI account returns 429 `insufficient_quota`/`credit_balance_exhausted`; no embedding model is registered. Only the free scanner/asset path and one Gemini text run were exercised.)

## Chat work log and mutation consent
- [x] Preserve publicly surfaced work-log events and actual UTC timing through completion, reload and owned history forks.
- [x] Keep live/pending permissions actionable after dropped streams and on unpositioned temporary runs; complete logs collapse once and remain reopenable.
- [x] Require exact VM resource choices, existing project manage consent and native v2 human approval before cloud mutation.
- [x] Qualify and activate the same API/worker protocol-v2 cohort with original encrypted checkpoint store/key; create no live VM. (Production 2026-11-17: drained cohort, protocol 2 on all API/worker; native temp-completion run completed on worker .12 with one priced usage row and zero open reservations; no VM created.)

## MCP connections
- [x] Provide the full registry gallery, featured templates, personal/global/domain connection states and safe OAuth/secret editing.
- [x] Restrict organization mutation to exact-domain managers/human system administrators and keep ordinary member views secret-free.
- [x] Keep per-user activation and frozen-run authority/configuration fences; cover API-key/reduced/foreign-domain cases.
- [x] Seed the featured remote MCP templates idempotently after the matching service deployment. (Production: created 4, skipped 2 sandbox-managed, failed 0.)
- [ ] Inspect the existing Lumen cluster and qualify managed Playwright/Markitdown if its current isolation/runtime prerequisites permit it; provision no new VM or cluster and make no node changes without separate approval. (Partial: approved gVisor/RuntimeClass on the existing agent node, stable namespace, PID limit, CNI deny and NodePort reachability measured; production runtime stays off until the final pool/image digests and mTLS/run isolation are qualified.)

## System administrators
- [x] Read exact native system grants, using recent-grant hints for discovery only; keep last-admin and session guards.
- [x] Reject noncanonical subjects, remove missing hint-only candidates and isolate hint keys by native identity source.
- [x] Refresh grant/revoke results visibly and derive table/banner from one snapshot across token-only renewal.

## Integrated verification and delivery
- [x] Resolve scoped review findings and run the final repository gates, i18n, architecture checks and real local BFF/API acceptance.
- [x] Verify desktop/mobile states; preserve public summaries and exclude private reasoning/secrets.
- [x] Publish immutable qualified releases/images; keep the shared dirty Lumen sandbox branch untouched. (Afterglow 1.32.25, Lumen 0.6.17.)
- [x] Back up before schema/config changes; deploy approved cohort without modifying HAProxy/ProxySQL/keepalived and compare the full container census.
- [ ] Record actual deployment/smoke limits, integrate the Afterglow worktree to shared dev, and archive this change after its acceptance is complete.
