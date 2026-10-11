## Implementation Tasks

- [x] Confirm the reported preset-name rejection and downstream membership authority effect with failing endpoint regressions; preserve unrelated shared changes.
- [x] Fix identity graph and project managed-role validation to allow explicit global custom descendants while preserving recognized core/project/service bounds, canonical IDs, cycles, domain and owner-workflow restrictions.
- [x] Verify successful project_reader -> audit, additive preset preservation, usable project membership afterward and unchanged ordinary-reader/system-admin and transitive escalation boundaries.
- [x] Exercise production routers with actual loopback HTTP/native SDK identity traffic; run relevant target and isolated complete gate, record synthetic/live and DB/schema limits.
- [x] Update role API/security/architecture/changelog evidence and archive the completed change.

## Verification and boundaries

- Two new endpoint regressions reproduced the reported409 and downstream project-management503 before the fix. After the fix, exact10 and both role/membership files110 passed; the actual shared source also passed110 without modifying private configuration. Canonical access target: backend285, frontend2files15.
- Actual Uvicorn production-router HTTP with installed openstacksdk/python-keystoneclient issued209 loopback Keystone fixture requests in both isolated and shared-source runs. Linking/inheritance, additive preset preservation, project management/membership, ordinary-reader403, independent custom delegation422, transitive core/member/managed-write409 and fresh-graph revocation passed. Synthetic identity/auth/session and FakeRedis; no production Keystone acceptance or writes. Initial fixture teardown error was corrected and both complete runs exited0.
- Integrated isolated dev gate passed: orchestration175, Kolla27, CLI19/PowerShell36skip, backend4411, frontend334files2569 plus runner9, contract174, functional35/9deselected, Ruff561files. Working and disposable-index staged architecture verified the same `source_sha256=0bb847f540722c9904bab68466af4a42075fe05b1690db4b864a49163c330c77`/2532files; real indexes/shared review marker were preserved.
- Existing validators/tests and API/security/architecture/changelog evidence were updated. No router/wire contract, ORM/SQL/schema, native policy, production DB/role write or deployment change. Custom-label policy safety requires administrator review. Shared migration084 and unrelated WIP were preserved and excluded from the integrated full-gate qualification.
