## Specification Tasks

- [x] 1. Map current dirty-tree refs, native Hub versus Docker transport, screenshot route/data sources, project/JWT forwarding and existing key issuance gaps without cloud or secret access.
- [x] 2. Write the project namespace/package/tag API, member-scoped key lifecycle, admin/service denial, package/cache separation and Afterglow integration contract in Palimpsest `docs/project-package-registry.md` (`palimpsest.project-packages.v1`).
- [x] 3. Validate the written contract for security/protocol/consumer gaps, resolve review findings and record actual checks. This is a spec review, not runtime acceptance.

## Implementation Tasks — implemented in local dirty trees; rollout not authorized

- [x] 4. Fix Hub original-token validation without minting a re-scoped token; enforce matching original project/member and deny admin/service/default-project authority before writes. Use trusted immutable protected-principal/project IDs (exact opaque Keystone IDs); a known administrator remains forbidden with a member-only project token. Verify original token A/header B and system/service/admin credential rejection.
- [x] 5. Add Hub namespace/package/version/tag/key/upload bindings and forward-preserving migration/reference checks. Preserve existing artifact/CAS data; no implicit package/backfill or tenant reassignment.
- [x] 6. Implement secret-once hashed project/package key issuance, owner-only list/revoke, bounded expiry and membership/role/account validation including finalization-time revocation; no key-to-key issuance or OpenStack authority.
- [x] 7. Implement bounded OCI/runtime-bundle graph validation, staged/resumable owner-and-key-bound uploads, immutable version and compare-and-set tag publication, project-only inventory/download; isolate BuildKit cache scopes and update every obsolete unqualified write caller.
- [x] 8. Implement explicit native registry profile and helper-backed login/build/push/pull in Palimpsest. Native build exports locally then publishes; no Docker image load/admin token/type=registry fallback. Preserve actual OCI registry behavior and strict offline rules.
- [x] 9. Add Afterglow member package/key read-control routers mounted only under `/api/v1`, use validated JWT project/original caller identity, and add resource audit mapping. Do not use admin library artifact rows as registry inventory.
- [x] 10. Add allowlisted package-key gateway to the trusted Hub. Validate credential-type ambiguity, stream transfer without buffering the whole package, preserve offsets/errors/no-store, and prohibit broad admin/build/export proxy or credential injection.
- [x] 11. Add `/palimpsest/packages` and navigation/admin-page cross-link using existing DESIGN.md tokens/responsive rules. Show exact namespace/package/tag/digest/platform/private project status and key scope/expiry/revoke; discard once-only secret and stale responses on project switch.
- [x] 12. Update affected architecture/docs/changelog after source review; synchronize new settings with Kolla rendering. Palimpsest `ARCHITECTURE.md` is updated but not stamped (unreviewed foreign working-tree changes).

## Verification and Rollout Gates

- [x] 13. Focused Hub/Afterglow behavior tests: ordinary member success, foreign-project and forged header denial, exact-package/reader permissions, admin/service exclusion including a protected owner with member-only scope, expiry/revocation/membership removal during upload, valid equal-byte cross-project publication without private-name leak, atomic tag conflict and shared CAS safety.
- [x] 14. Local actual end-to-end ordinary-member build → key login → native push → selected-project API/browser row → pull/exact root equality; cache-only upload does not count as a package. Native API and BFF gateway proven without double `/v1` or credential fallback (proof `pkg-d642b179`, 2026-10-02).
- [x] 15. Browser proof: selected project inventory/key lifecycle, once-only secret, project switch fencing and 390–1920 px layouts on a production frontend build. Deep-link and admin cross-link are source/unit-test covered only.
- [x] 16. Named/full test gates after integration (Palimpsest Hub 208, portable 6112; Afterglow unit 3455, contracts 135, frontend 1893, svelte-check clean). Architecture guard remains stale pending a reviewed stamp.
- [ ] 17. Obtain separate exact-ref/project/non-admin-user/key/migration/deployment approval. Verify HTTPS trusted endpoint and bounded token-validation read permissions; rollout Hub before clients/Afterglow and exercise actual cloud.dmslab.re.kr build/push/inventory only in approved resources.
- [ ] 18. Archive only after all implemented behavior and evidence gates pass. On failure disable publication, retain metadata/CAS and show explicit unavailable UI; never roll back to default-project/admin upload auth or destructive down-migration.

## Current evidence

2026-10-02: implemented in both local dirty trees (uncommitted). Local proof `pkg-d642b179` used an isolated genuine Keystone, MariaDB, Redis, source Hub, Afterglow BFF/TLS gateway and production frontend build; see Palimpsest `docs/development-handoff.md` (Project-scoped package registry — 2026-10-02) for checks, fixes found by the proof, and an incident where an unscoped backend `pytest` collected `tests/integration/` against the configured cloud Keystone. No production authentication, upload or deployment is authorized by this change. Astra role is unavailable in this host; do not claim an Astra approval or source-review stamp.

Historical planning record:

Spec review resolved the public-key-ID wire lookup, UUID fallback namespace reservation, protected admin/service owner with member-only scope, current-project-only context/explicit namespace registration, mandatory exact-key/same-scope cache API, browser/native path mapping and untrusted provenance boundaries. The online build example explicitly requests cache and package actions; no implicit cache authority is added.

Checks: the three fenced JSON examples parsed; all six relative link targets across the contract and registry guide existed. `openspec new change project-scoped-palimpsest-packages --schema rapid --json` initialized the workflow; `openspec status --change project-scoped-palimpsest-packages --json` recognized `rapid` and both planning artifacts. Its `isComplete` refers to artifact presence, not unchecked implementation/evidence tasks. Generic `openspec validate ... --type change --strict --json --no-interactive` failed because it requires a specs delta; this repository expressly has no specs layer (`docs/agent-development-guide.md:123-128`), so no artificial delta was added to bypass that mismatch. No runtime package/API/browser acceptance was exercised and the change is not archived.
