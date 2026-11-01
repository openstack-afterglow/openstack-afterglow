## Why

Late review confirmed profile first-password proof uses exact native token GET but still treats revoked/expired TokenNotFound404 as availability503 and service-auth401 as user-invalid401. AccessInfo.auth_token is caller-supplied echo, not returned-token authority. Existing keystone._NATIVE_INVALID_TOKEN_MESSAGES defines exact native404 semantics.

## What Changes

- Reuse exact native invalid-token message allowlist: recognized TokenNotFound404 ->401 password_create_session_invalid; service auth401/403, generic/proxy404 and transport/parse failures ->503 password_create_session_unavailable.
- Keep exact returned user/home identity checks and native GET (no extra token mint); remove echoed token comparison and mock-only substitution test.
- Prove failing-before and passing-after through actual installed Keystoneclient/Keystoneauth HTTP plus focused/domain regression and actual Uvicorn scenario. Update source-local image, docs/architecture and archive.
- Close confirmed public recovery gap: missing federation/marker metadata is not local-password authority. All password recovery proofs require observed native existing history and revision; consume only through atomic existing-only reset. Reject legacy NULL-revision password proofs, remove unconditional local admin-PATCH recovery fallback. Native guard unavailable keeps non-enumerating202 and administrator recovery alternative.
- Keep user's existing atomic conditional create/no-overwrite policy. No stock PATCH/metadata fallback, native extension/UI/schema/config/dependency/production changes.

## Impact

backend/app/services/account_recovery.py, profile proof regressions, canonical backend/worker images and affected docs. No deployment, IAM/mailbox write, commit/push or shared index mutation.
