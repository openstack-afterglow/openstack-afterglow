## Implementation Tasks

- [x] 1. Inspect current repository/release/controller/operator state and trace the recorded issuance failure without retrying it.
- [x] 2. Integrate the previously completed personal MCP setup/check feature on latest dev while preserving unrelated shared changes.
- [x] 3. Publish https://cloud.dmslab.re.kr/mcp across transport/OAuth, user UI/docs and canonical HAProxy/Helm/Kubernetes/Kolla configuration.
- [x] 4. Fix Keystone credential expiry serialization, retaining ownership, restriction, durable authority and safe failure behavior.
- [x] 5. Run exact regressions, required test:gate, actual MCP/HAProxy/browser smoke and supported architecture builds; update architecture/changelog.
- [x] 6. Commit completed scope on isolated dev, normally push origin/dev and verify exact-SHA CI before immutable patch publication.
- [x] 7. Preserve and verify recovery inputs, deploy published release through standard Kolla genconfig/pull/reconfigure, and verify production MCP discovery/authentication/key issuance and UI.
- [x] 8. Record exact evidence/limits and archive only after acceptance.
- [x] 9. Review native user/project grades and actual service-credential directory reads; map legacy Waygate ownership and Drover execution authority against compatible published sibling contracts.
- [x] 10. Obtain explicit grade policy approval: preserve existing service grades, make no new ordinary-user grants, and do not infer promotion from core roles. User approved pieroot ownership of the single active Waygate `pieroot-macbook` and pieroot reauthorization of Drover `test-cluster`.
- [x] 11. Apply only approved legacy owner/reauthorization under the real owner authority; qualify directory scope, all writers/recovery/migrations and guest rollout; deploy compatible published siblings before Afterglow.

## Verified evidence and boundaries

- Production issuance evidence is the original Keystone400 `Timestamp not in expected format`; no unfixed production retry was used to recreate it.
- Installed SDK expiry regression covers 8 offset/microsecond conditions. Combined targeted suite: 174 passed, including 38 actual native HAProxy HTTP routing conditions; no production cloud/tool/provider acceptance is implied.
- Read-only native inventory (2026-10-08T20:50:39Z): 44 projects, 64 users, 67 roles, 163 direct and 630 effective assignments. Reviewed ordinary memberships: 93, with service grades only on pieroot's existing SYSTEM/DMSLAB memberships. Preserve ungraded memberships; do not automatically grant service roles.
- Actual current Waygate/Drover credentials, checked through installed SDK discovery at 2026-10-09T03:11Z: users/projects/roles/effective assignments and role-inference reads all HTTP200. An initial manually composed, unversioned endpoint probe returned404; it was not an authorization failure and was replaced with native SDK discovery.
- Legacy source schema/state: Waygate0.3.1 migrations1–4 has one active `pieroot-macbook` profile without owner provenance; Drover0.4.3 migrations1–3 has one active `test-cluster`, creator pieroot, and 5 manager credential rows. Empty active-job query is not an all-writer quiescence or recovery receipt.
- Publication, production changes, real-owner reauthorization and guest rollout remain unchecked until their actual receipts exist. Shared unresolved index and architecture review block remain preserved.

## Production cutover receipts (2026-10-09)

- Core siblings: Lumen 0.6.6, Drover 0.4.5, Waygate 0.3.3 deployed via canonical Kolla across dms-controller1..3 (`kolla-core-siblings-resume.json`: passed). All 6 containers healthy/running with exact release revisions and verified authority hashes.
- Palimpsest: 0.3.2 release (`v0.3.2`, revision `1f12039`) published to PyPI and GitHub Release; Docker images verified and deployed on dms-controller1 with single-host CAS storage (`palimpsest_hub_storage`). Dedicated system reader authenticated live against Keystone, queried direct system assignments, and enforced system-admin vs project-admin boundaries (HTTP 200 vs 403 vs 401).
- Afterglow: v1.30.6 deployed across dms-controller1..3 via canonical Kolla (`kolla-afterglow.json`: passed). Backend, frontend and notion_worker containers healthy with exact revision `aab9a836`.
- MCP endpoint: `https://cloud.dmslab.re.kr/mcp` routed by HAProxy to Afterglow backend (uvicorn). RFC 9728 metadata at `/.well-known/oauth-protected-resource/mcp` returns HTTP 200.
- Live MCP token issuance: Real browser UI test in pieroot session issued personal token `Lumen` (`mcp-afgl-tGRZcuOb6mq`) without 500 error; active in UI. End-to-end API test verified issuance, `/verify` endpoint (28 tools, protocol 2025-11-25), and JSON-RPC `tools/list` against live MCP endpoint with Bearer authentication (HTTP 200, 28 tools). Temporary test key cleaned up.
