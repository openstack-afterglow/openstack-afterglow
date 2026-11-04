## Why

Operators need to schedule an earlier shutdown and govern extension requests without granting unrestricted extensions or requiring approval in every domain.

## What Changes

- Allow moving an active expiry earlier, safely fencing in-flight native lifecycle work.
- Limit each extension to one calendar month, require a reason, and explain that administrators may follow up on unsuitable reasons.
- Default to automatic extension approval; allow domain managers to require review by authorized domain managers or project administrators.
- Expose request, review, status, and domain policy in the console with native authority checks and durable, race-safe handling.
- Assess operational scheduler activation against the existing production safety prerequisites; do not silently alter schedules or cloud resources.

## Capabilities

### New Capabilities
- `instance-usage-extension-governance`: Domain-scoped extension approval policy and request lifecycle.

### Modified Capabilities
- None; existing schedule behavior is covered by the new governance capability.
## Impact

Instance usage API, native schedule metadata, domain policy and authorization, approval persistence, console, tests, and deployment guidance.
