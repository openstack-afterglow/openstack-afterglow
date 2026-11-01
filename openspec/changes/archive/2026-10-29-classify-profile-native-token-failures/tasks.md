## Implementation

- [x] Reproduce recognized native404/service401 misclassification with actual installed native HTTP clients; preserve proxy404/mismatch/failure boundaries.
- [x] Normalize only exact invalid-subject404 to401; map service/other errors to503 and retain actual returned identity/home checks without auth_token echo.
- [x] Reproduce markerless mapped public recovery first-password bypass, then require native existing-only state/revision for all password proof issuance/completion; remove unconditional PATCH and reject legacy NULL proof.
- [x] Verify focused/domain regression and actual API/native HTTP smoke; update latest backend/worker source proof and docs/architecture, preserve prior receipt boundaries and archive.

## Verification boundary

- Token classification failing-before3failed/4passed; public first-password/legacy-proof bypass6failed. Corrected focused76passed; complete40-module auth1352passed; current target orchestration10passed. Removed metadata-only/echo pins, not security assertions.
- Actual Uvicorn + installed native client TCP: public markerless absent no mail/write, local existing conditional reset200, history-lost/legacyNULL410, recognized subject404401 and service401/403/proxy404503 before+after mail; pending proof/no-write. Native/provider/SMTP synthetic; SQLite journal and FakeRedis Lua semantics are disclosed.
- Fresh final canonical backend+worker builds/runtime both architectures and current19path source equality: `~/.local/share/afterglow-proofs/password-management-20261030/canonical/public-recovery-token-final/verification.json`. Previous image receipts are frozen history, not current source.
- Native extension/UI source unchanged. Prior128native tests per architecture and112UI/bounded4GiB frontend proof remain separately qualified; no rerun/fullgate/cloud/realmailbox/deploy/commit/push/index claim. All email password recovery now requires nativeAPIv2; current-password and explicitadminreset remain separate.
