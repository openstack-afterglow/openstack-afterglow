## 1. Contract

- [x] 1.1 Inspect config SMTP/readiness, secret encryption, runtime settings, registered identities, announcements, safe notifications and worker/UI conventions; preserve shared work/index.
- [x] 1.2 Specify source-only web settings/diagnostics/delivery/preferences, API interfaces and slice ownership.

## 2. Mail configuration and diagnostics

- [x] 2.1 Implement web SMTP/IMAP override persistence, secret masking/encryption, revision save/reset and config example/K8s paths.
- [x] 2.2 Apply effective settings to all existing mail and recovery/signup/provider/admin-password readiness paths.
- [x] 2.3 Implement web SMTP/IMAP saved-setting connection checks, test-message intent and read-only receipt verification with truthful statuses.

## 3. User delivery

- [x] 3.1 Implement durable registered-user individual mail with operation dedup, encrypted payload and visible per-recipient states.
- [x] 3.2 Implement explicit announcement email preserving all/project/user targeting and scheduling/current authority.
- [x] 3.3 Implement global and per-user notification preferences and supported event email delivery without GET side effects/history blast.
- [x] 3.4 Register router/model/schema and existing API/Notion dispatcher email-delivery role; preserve cancellation/unknown safety.

## 4. Web and verification

- [x] 4.1 Add administrator email settings/diagnostics/test/history, individual composer, announcement controls and account preferences in all9locales.
- [x] 4.2 Run focused endpoint/security/consumer tests and isolated real SMTP/IMAP/TCP+SQL execution; no live mail or shared DB writes. Initial943/after-fix144 backend, actual TLS SMTP/IMAP acceptance/receipt/absence/auth failure, web→TCP→SQL outbox→SMTP individual/announcement/4notification paths; canonical amd64 API/worker transport/crypto and raw105 MariaDB10.11.19 CAS/dispatch replay checks passed. Native/auth fixtures remain synthetic.
- [x] 4.3 Exercise actual compiled web workflows including auth/owner/secret/error states and responsive controls. UI161passed; corrected deletion+email60passed; typecheck0errors/17existingwarnings, build, i18n0errors/45existingwarnings and detector[] passed. Actual measured22responsive rows (all9locale×2theme390px,3other390px,settings1440px) had overflow0 and no rendered secret.
- [x] 4.4 Review/update existing architecture/API/security/config/deployment/testing/changelog, run applicable full gate and schema compatibility checks, preserve evidence and archive. Final supported-Python gate exit0: backend12702/94skip,frontend6547/508files,contract183,realDB167/37deselected,Ruff833. RawSQL105 owned MariaDB10.11.19 and canonical amd64 three-image smoke passed; production snapshot/native/mailbox/deployment not applied. Final scoped freshness and archive retain exact source-only boundaries; all owned scaffolds/runtimes removed.
