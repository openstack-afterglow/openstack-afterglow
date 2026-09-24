## Why

The reported Keystone token-authentication 404 is being flattened into a retryable refresh 503. Browser refresh failures are retained only inside the API coordinator; background refresh also ignores terminal results. The console therefore appears authenticated while protected actions cannot run. Explicit logout can itself abort when an already pending refresh rejects.

## What Changes

- Normalize Keystone's specific `Failed to validate token` and `Could not recognize Fernet token` NotFound responses at the service adapter to the existing Unauthorized contract. Unrelated endpoint/resource 404 and transport/server errors remain retryable failures, not proof of invalid credentials.
- Keep session credentials on genuine availability failures, but present a persistent blocking recovery dialog with retry and logout, rather than an invisible background failure. Preserve mounted page drafts and existing cooldown/coalescing.
- Route terminal background refresh results through existing clear-and-login recovery. Ensure explicit logout completes local cleanup even if pending refresh or remote revocation fails.
- Add regressions for invalid-token versus unavailable-service classification, background expiration, stale response fencing, retry recovery and logout during a failed pending refresh.

## Constraints and completion

Reuse current authentication, modal/button primitives and design tokens. No blanket logout on 503, bypass of backend authorization, new token TTL policy, real-user session deletion, secrets, unrelated changes, commit/push or production deployment. Verify deterministic reproductions, actual Chromium recovery UI, supported-architecture frontend/backend builds, canonical local deployment and required repository gates. Update architecture/security/auth documentation and archive only with accurate proof.
