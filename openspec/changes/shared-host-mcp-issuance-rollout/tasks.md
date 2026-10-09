## Implementation Tasks

- [x] 1. Inspect current repository/release/controller/operator state and trace the recorded issuance failure without retrying it.
- [x] 2. Integrate the previously completed personal MCP setup/check feature on latest dev while preserving unrelated shared changes.
- [x] 3. Publish https://cloud.dmslab.re.kr/mcp across transport/OAuth, user UI/docs and canonical HAProxy/Helm/Kubernetes/Kolla configuration.
- [x] 4. Fix Keystone credential expiry serialization, retaining ownership, restriction, durable authority and safe failure behavior.
- [x] 5. Run exact regressions, required test:gate, actual MCP/HAProxy/browser smoke and supported architecture builds; update architecture/changelog.
- [ ] 6. Commit completed scope on isolated dev, normally push origin/dev and verify exact-SHA CI before immutable patch publication.
- [ ] 7. Preserve and verify recovery inputs, deploy published release through standard Kolla genconfig/pull/reconfigure, and verify production MCP discovery/authentication/key issuance and UI.
- [ ] 8. Record exact evidence/limits and archive only after acceptance.
- [x] 9. Review native user/project grades and actual service-credential directory reads; map legacy Waygate ownership and Drover execution authority against compatible published sibling contracts.
- [x] 10. Obtain explicit grade policy approval: preserve existing service grades, make no new ordinary-user grants, and do not infer promotion from core roles. User approved pieroot ownership of the single active Waygate `pieroot-macbook` and pieroot reauthorization of Drover `test-cluster`.
- [ ] 11. Apply only approved legacy owner/reauthorization under the real owner authority; qualify directory scope, all writers/recovery/migrations and guest rollout; deploy compatible published siblings before Afterglow.

## Verified evidence and boundaries

- Production issuance evidence is the original Keystone400 `Timestamp not in expected format`; no unfixed production retry was used to recreate it.
- Installed SDK expiry regression covers 8 offset/microsecond conditions. Combined targeted suite: 174 passed, including 38 actual native HAProxy HTTP routing conditions; no production cloud/tool/provider acceptance is implied.
- Read-only native inventory (2026-10-08T20:50:39Z): 44 projects, 64 users, 67 roles, 163 direct and 630 effective assignments. Reviewed ordinary memberships: 93, with service grades only on pieroot's existing SYSTEM/DMSLAB memberships. Preserve ungraded memberships; do not automatically grant service roles.
- Actual current Waygate/Drover credentials, checked through installed SDK discovery at 2026-10-09T03:11Z: users/projects/roles/effective assignments and role-inference reads all HTTP200. An initial manually composed, unversioned endpoint probe returned404; it was not an authorization failure and was replaced with native SDK discovery.
- Legacy source schema/state: Waygate0.3.1 migrations1–4 has one active `pieroot-macbook` profile without owner provenance; Drover0.4.3 migrations1–3 has one active `test-cluster`, creator pieroot, and 5 manager credential rows. Empty active-job query is not an all-writer quiescence or recovery receipt.
- Publication, production changes, real-owner reauthorization and guest rollout remain unchecked until their actual receipts exist. Shared unresolved index and architecture review block remain preserved.
