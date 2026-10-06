## Why

The project-package BFF requires an explicitly trusted Hub URL. Kolla's Hub public endpoint currently needs a separately duplicated HAProxy hostname and is not projected into Afterglow's generated services configuration. Setting the endpoint must connect both boundaries without discovery or authentication fallback.

## What Changes

- Derive the Palimpsest HAProxy public hostname from `palimpsest_public_endpoint_url`; keep the explicit exposure toggle and existing hostname consistency validation.
- Add `afterglow_service_palimpsest_internal_url`, defaulting to an explicitly configured `palimpsest_public_endpoint_url`, and render nonempty values in both Kolla-generated Afterglow configuration layers.
- Preserve detailed operator TOML when no Kolla endpoint is selected; retain the existing Hub HTTPS-origin validation and package TLS verification.
- Exercise real Ansible rendering, stock HAProxy configuration and local HTTP routing, including endpoint precedence and rejected origins.

## Capabilities

### New Capabilities
- Unified operator endpoint input for Hub HAProxy routing and the Afterglow package transport.

### Modified Capabilities
- Existing Kolla configuration and independently packaged Palimpsest role defaults; no service credential or package protocol changes.

## Impact

Afterglow Kolla defaults, generated templates, sample and deployment documentation; sibling Palimpsest HAProxy hostname default and documentation. No production rollout, image publication, registry/schema migration, native KVM execution or data-volume mutation. The reported 404 from the old Hub package API remains a separate image compatibility issue.
