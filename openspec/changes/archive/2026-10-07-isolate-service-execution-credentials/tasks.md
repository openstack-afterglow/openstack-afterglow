## Implementation Tasks

- [x] Map current tenant execution credentials across Drover, Waygate, Lumen and Palimpsest; confirm the user's choice of resource-lifetime continuous delegation with reauthorization.
- [x] Convert Drover request/worker/callback tenant execution to bounded user-authorized delegation; remove project manager creation/password execution paths and migrate all callers.
- [x] Implement Drover continuous resource credentials, current-authority checks, real guest credential replacement and currently authorized user reauthorization/delete, including explicit handling of legacy resources.
- [x] Convert Waygate create/delete jobs and network attach/detach to bounded delegation; add additive durable grant storage, current-authority validation and credential cleanup without a tenant-service-password fallback.
- [x] Implement Waygate member-compatible volume-backed boot for zero-disk flavors and retain safe delete/rollback behavior.
- [x] Remove Lumen's tenant-admin escape hatch and verify caller, API-key, durable provider and operator infrastructure authority remain separated.
- [x] Convert Palimpsest deferred Glance exports to bounded delegation while preserving original-token package authority, local KVM/build and native package key isolation.
- [x] Migrate affected Afterglow forwarding contracts (retire the K3s provisioning-intent API/token/Kolla surface, allow Drover authorization routes, surface reauthorization and Stampede refusals), update each repository's relevant architecture/config/docs, and exercise revocation, cross-project rejection, durable cleanup, retry fencing and real SDK/HTTP runtime paths.
- [x] Run scoped service regression checks and applicable architecture/OpenSpec validation; report exact verification and remaining operational prerequisites without claiming deployment.

## Evidence (2026-10-07, local and synthetic only)

- Waygate: `uv run --frozen pytest tests -n 4 --dist worksteal` 628 passed/3 skipped; ruff passed; 12 native keystoneauth1/keystoneclient/openstacksdk delegation cases passed on SQLite and on disposable MariaDB 11.4 built from migrations 001–006 (006 re-ran idempotently; unique/foreign keys enforced). The native run found and fixed a string Trust expiry and an `openstack.connect(session=...)` call that ignored the guarded session.
- Drover: `pytest tests --ignore=tests/integration` 1123 passed/1 skipped; SDK 114; native loopback Trust create/auth/delete/revocation 2; disposable MariaDB 11.4 ledger 001–004 with idempotent 004 rerun.
- Lumen: focused 317, contract 3049, Docker integration 284 and system 31 passed in disposable compose projects.
- Palimpsest: Hub lane 285, native delegation 28, Kolla contracts 45, lanes manifest and OpenSpec validation passed.
- Afterglow: canonical backend unit selection 4111 passed (76 warnings); Drover gate/proxy tests 132 and intent-retirement selection 84 passed; complete Kolla contract command passed (27 Node + 11 image-ref tests); reauthorization notice component 7 passed. Related frontend selection: 315 passed, 4 existing `K3sRotateProgressModal.test.ts` accessibility failures; wider i18n selection also reports pre-existing hard-coded Korean findings outside owned files. Owned backend Ruff passed; scoped Svelte diagnostics had no findings, not a clean full-tree claim. Synthetic Chromium QA exercised missing authority, Stampede refusal, reauthorize → in progress → active and own-only retirement at 1440px and 390px without horizontal overflow. QA browser/services and scratch files were removed.
- Not exercised: live Keystone trust/app-credential policy, OpenStack/K3s/Glance/Cinder resources, image builds, deployment, removal of existing tenant grants or manager users. Operational order: drain old jobs, migrate sibling schemas, upgrade Drover before Afterglow, reauthorize legacy Drover clusters, then retire legacy tenant assignments only with separate approval.
- Afterglow architecture guard passed against an isolated temporary index (`HEAD` + 28 explicit file snapshots), digest `4f831dc8da84c8ad73f21b45f4fada610a6a1769ebaaf5c220e70e431430a3e3`, 2377 files. The temporary index was removed; this does not approve the shared unresolved index or global working-tree freshness. Sibling architecture stamps and change validations passed as recorded in their local evidence. gbrain sync was unavailable (CLI/detection helper absent).

