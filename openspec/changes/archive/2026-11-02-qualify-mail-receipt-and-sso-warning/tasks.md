## 1. Accurate administrator warning

- [x] 1.1 Correct all9locale administrator initial-or-reset confirmation and generated-mail risk advice without changing authority/API/schema.
- [x] 1.2 Verify actual9locale confirmation and unavailable-native mapping with existing behavioral regressions; do not re-pin literal wording tests. Actual Vite/Chromium9locales warning-beforePOST and current unavailable mapping passed; backend191/UI70/i18n0errors passed. Removed one obsolete phrase-only assertion, retained dispatch/recipient/secret/owner behavioral checks.

## 2. Independent receipt qualification

- [x] 2.1 Run pinned authenticated GreenMail2.1.15 with purpose-generated trusted TLS, isolated network/dummy users and no real mail.
- [x] 2.2 Exercise actual application saved-settings connection, test-send/outbox and receipt routes over TCP for implicitTLS, exact ID/substring collision/missing mail/incorrect auth and readonly flags. GreenMail does not advertise STARTTLS; actual mode refusal was verified, not reclassified as positive interop. Final real-server probe bg62 passed both intended outcomes; no product protocol changes were needed.

## 3. Final evidence

- [x] 3.1 Update existing docs/changelog/architecture with precise old synthetic vs independent-server evidence, run affected verification and final source guard, archive and remove owned fixtures. Final post-warning gate exit0 (backend12702/frontend6547/contracts183/realDB167/Ruff833); canonical final3amd64images+actual API/worker/frontend smoke passed. Independent GreenMail TLS exact/collision/flags/dedup/auth passed; unsupported STARTTLS safely refused without positive-interop claim. Owned UI/GreenMail/network/keys/fixtures/QA tags removed; no real mailbox/native/shared DB or deployment.
