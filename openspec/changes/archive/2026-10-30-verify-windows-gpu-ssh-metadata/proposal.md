## Why

The scheduled GPU Windows password-creation regression no longer checks that Nova receives no GitHub SSH-access markers. These markers are exposed as the instance's SSH access mode and login, so an incorrect marker would claim access that was not configured.

## What Changes

Restore a behavioral assertion at the Nova CREATE boundary for both native GitHub SSH markers while continuing to allow the required usage-schedule metadata. Preserve the existing Linux-userdata and Windows-password assertions. Do not restrict unrelated metadata or change application behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None; this strengthens the existing Windows GPU creation regression.

## Impact

The existing parameterized backend test and verification record only. No API, schema, runtime configuration, cloud resources or deployment change.
