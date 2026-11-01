## Why

Late review, checked against current source, confirms post-commit shell cleanup failures can hide successful refresh/scope rotation and account-session revocation; legacy sessions can evade blacklist when their family pointer is absent; consume-time revocation is misreported as Redis failure; malformed receipts stop unrelated cleanup; unresolved native resources can outlive the expiring singleton key and admit another shell.

## What Changes

- Preserve committed browser-authority transitions for best-effort cleanup callers, while retaining explicit cleanup-pending signaling and strict native-revocation failures.
- Restore exact legacy requested-session blacklist fallback without reviving old rotated credentials.
- Preserve consume-time authority errors and retire the exact unexposed credential on failed promotion.
- Isolate malformed receipt processing so healthy receipts and signed orphan cleanup still run, without discarding uncertain ownership.
- Fence singleton admission atomically on persistent unresolved resource ownership, not liveness TTL alone; only exact verified cleanup releases that owner.

## Impact

No production deployment, native source change, role grant, schema migration or user-home deletion. Scope is the existing Cloud Shell/Redis/session authority boundary, regression tests, actual isolated execution, matching current-source image builds and documentation. Prior hardening evidence remains historical; follow-up source evidence is separate.
