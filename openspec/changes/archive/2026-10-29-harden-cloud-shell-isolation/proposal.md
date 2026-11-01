## Why

Actual Cloud Shell observations show no effective per-shell CPU quota, an excessive PID ceiling, writable rootfs, and reachable metadata. Current Afterglow source additionally leaves tickets and running relays independent of browser login-family revocation, while shell credentials are separately issued native tokens. Personal ownership controls already exist and must remain authoritative.

## What Changes

- Bind Cloud Shell tickets and active execution to the existing immutable login family, exact user/home/working-domain/project, current lifetime, blacklist state, and fresh native project-write authority. Reject issuance/consume/provision/bootstrap after revocation or scope change, survive ordinary refresh, and terminate the relay on lost authority.
- Keep a bounded durable cleanup receipt for every issued derived token before exposing a ticket. Explicitly revoke that exact token on abandoned issuance, expiry, revocation, disconnect, or reconciliation; retain failed cleanup until native expiry rather than relying on Keystone chain revocation. Preserve home volumes and signed exact-owner container cleanup.
- Add an exact-input, build-time native Zun Docker-driver integration for dedicated-service-project CPU CFS quota, memory/swap ceiling, PID512, read-only rootfs, bounded tmpfs/shm/logs, and pre-start metadata/operator CIDR denial. Recheck lifecycle paths and refuse unsupported isolation. No live source patching or host-wide Docker policy changes.
- Require native runtime readback evidence before authorizing the terminal. Reject ingress-capable/uncertain security groups; propagate mandatory metadata and operator management CIDRs across all configuration renderers.
- Suppress Cloud Shell ticket-bearing WebSocket access logs and redact query tickets in application log sanitization.

## Capabilities

### New Capabilities

- Checked native Cloud Shell runtime profile and backend admission.
- Derived-token cleanup receipts and login-family-bound terminal authority.

### Modified Capabilities

- Cloud Shell ticket issuance, terminal lifetime, native cleanup/reconciliation, security-group admission, config rendering, and ingress logging.

## Impact

No SQL migration, no user/role grants, no tenant home deletion, no production deployment, and no arbitrary user runtime options. Native Zun integration must be installed on every eligible compute before activating the stricter backend; unknown/unpatched runtimes fail closed. Existing signed ownership and user-wide singleton remain. Current concurrent work/index and operational configuration/keys are preserved. Source/local synthetic proof is separate from production all-writer/runtime/network qualification; no claim about deployed Keystone revocation-chain behavior is made.
