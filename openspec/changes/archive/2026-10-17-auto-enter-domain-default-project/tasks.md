## 1. Native Default lifecycle

- [x] 1.1 Bootstrap an absent Default during authenticated authorized login with in-lease membership/absence rechecks and an unchanged no-write fast path.
- [x] 1.2 Give every newly created Default a verified unique project_owner; grant manager only to an actual new-domain creator or explicit administrator bootstrap.
- [x] 1.3 Preserve direct project_reader for subsequent domain participants, idempotence, domain isolation, safe staging, exact-resource failure handling and no global role seeding.

## 2. Enrollment and session integration

- [x] 2.1 Add personal Default ownership through the existing durable enrollment grant journal and verify it before activation.
- [x] 2.2 Prepare and refresh Default selection consistently for password and configured-provider login, exchange the real final project scope, and fail closed without session issuance on failure.
- [x] 2.3 Verify existing project_owner member-role delegation and reader denial for the newly created Default without relaxing ownership-transfer, manager or last-owner policy. Actual compiled-browser precheck additionally reproduced the owner/admin checkbox bug; UI now consumes server-filtered grantable roles and is_owner, not the ownership-transfer flag.

## 3. Browser entry

- [x] 3.1 Route a fresh scoped password/provider login directly to its selected domain project even when other domains are available; retain explicit workspace switching and invitation/consent precedence.
- [x] 3.2 Do not publish a default-project hint as an active native scope; update affected consumer regressions.

## 4. Acceptance

- [x] 4.1 Run changed consumer suites and relevant auth/access targets, plus lint/type checks, and record exact results and unrelated pre-existing failures separately. Backend418passed/5DBskips plus personal-domain API15passed; DB functional159passed; focused frontend183 and full4277passed; changed16Python lint/format and i18n checks pass. Auth/access, unrelated contracts, the full gate and the existing PageState.instanceId type error remain non-green, with exact evidence in docs/testing.md and verification.json. The gate's obsolete personal enrollment grant-count assertion was removed in favor of native ownership/activation checks and its exact selector/file passed; the whole gate was not rerun.
- [x] 4.2 Run actual HTTP/runtime first-login, repeated participant, domain creation, role management and native-scope denial smoke with explicit real/synthetic boundaries. Loopback Uvicorn + real auth/JWT/session/ownership SQLite: first/participant login200, owner delegation200, reader/foreign403, owner removal409, domain create201/switch200, concurrent first-login2x200/one new Default/one owner. Native directory/IdP/Redis/quota effects are synthetic.
- [x] 4.3 Verify the compiled browser surface at desktop and mobile, update auth/IAM/operator documentation and changelog, and record scoped architecture review and runtime evidence. Canonical Compose compiled UI: selected-domain password/provider direct dashboard, owner admin delegation then reader restoration, reader editor denial, 1440/390px overflow0 and settled screenshots; Korean compiled guide plus four-locale docs regressions. Canonical backend/worker/frontend amd64+arm64 builds and image source parity/import/runtime checks are scoped in docs/testing.md. Final private working/staged architecture digest5c5ab416843a4333bd0206520e0e97c6f986a64ae73e49d9fdf5c2681c9700d9/3032files; no new schema, global role seeding, private config change or production rollout. Owned browser/runtime/frontend and functional datastores stopped; throwaway script/misleading captures removed.
