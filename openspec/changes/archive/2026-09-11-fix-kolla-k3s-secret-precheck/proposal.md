## Why

The scoped Kolla deployment reached the container restart phase before discovering that an existing operator secrets file lacked the newly required K3s GPU admission and provisioning tokens. The unresolved variables caused every controller restart task to fail after configuration and bootstrap work had already completed.

## What Changes

- Define empty role defaults for both operator-owned K3s internal API credentials so Ansible can evaluate the service environment safely.
- Fail both Kolla prechecks and deployment preconditions before restart when K3s is enabled and either credential is shorter than 32 characters.
- Add contract coverage for the fail-closed validation.
- Generate missing production credentials atomically in the operator secrets file, without exposing their values.

## Impact

No architecture change. This moves an existing secret requirement to the preflight boundary and preserves fail-closed K3s authentication.
