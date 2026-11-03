## Why

The live 1.32.5 ORM selected SQL106 columns absent from afterglow_kolla. Both authenticated MCP account list endpoints returned MariaDB1054/HTTP500. Existing Kolla bootstrap did not apply or verify SQL106, and the API image omitted the migration files. The user approved direct production repair and release1.32.6.

## Change

- Preserve a protected MCP-table backup, then apply the immutable release-pinned SQL106 without extending consent, replacing credentials or deleting rows.
- Package the migration manifest/files in the API image. Replace Kolla's legacy opportunistic bootstrap with a config-only strict model-registration/create-all runner and SQL106-only application/verification before new services start.
- Verify manifest identity/checksums, MariaDB column/default/nullability/JSON/CHECK postconditions, and serialize canonical bootstrap on one MariaDB connection. Compatible schemas skip ALTER; partial SQL106 can resume. Historical migrations are not replayed; failures abort bootstrap.
- Publish immutable1.32.6 from verified dev source0334564dfb2fdb45bf55d617263ee973e785a45d, with exact-SHA CI, bilingual Release, image/latest digests and Helm.

## Acceptance and evidence

The direct DDL retained original grant5/token52 row hashes. Source regressions and real packaged MariaDB fresh/legacy/repeat/refusal smoke passed; the complete gate passed. A concurrent operator's successful addon rollout used this role and revision and ran SQL106 bootstrap. All3 live API/frontend/worker cohorts match1.32.6; effective DB/Redis/keys and sibling image IDs are preserved. Actual authenticated MCP list requests returned200.

## Explicit limits

Our foreground compute SSH ended255 without a final recap. The concurrent operator's separate full deploy ended2 and remains unresolved; it is not reported as an infrastructure-wide success. Current compute12 containers and native OVS15 agents are healthy/alive. No duplicate control rollout was started. Browser visual acceptance was unavailable because the relay extension is out of date. These limits are recorded in docs/testing.md and the private operational-acceptance receipt; they do not imply unfinished migration implementation or a successful full infrastructure deployment.
