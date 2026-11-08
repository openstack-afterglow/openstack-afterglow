## Why

Neutron returns `tags` metadata on security group rules, which the Cloud Shell validator currently rejects even when the rule otherwise meets its egress-only policy. Production also selects a default group with ingress rules; that separate configuration issue must not be bypassed.

## What Changes

- Accept the native rule `tags` metadata without relaxing ingress, ownership, lateral rule, or unknown-field checks.
- Add a regression covering native SDK-shaped tagged rules and unsafe rules.
- Document the metadata contract and the independent deployment prerequisites.

## Capabilities

### New Capabilities

- `cloud-shell-tagged-egress`: Permit native tagged egress rules while retaining fail-closed network isolation checks.

### Modified Capabilities

None.

## Impact

Cloud Shell security group admission and its documentation. No automatic changes to OpenStack resources, credentials, deployment or existing default groups.
