## Why

MCP can create an image-backed VM but cannot discover selectable flavors, images or caller-owned SSH key names. This blocks MCP-only provisioning. Existing network list/get and VM network attach already exist and must remain the single implementation.

## What Changes

- Add read-only flavor list/get, active boot-image list/get and caller-owned SSH keypair list/get tools to the canonical MCP/Lumen registry.
- Add bounded catalog page scanning with continuation markers, limit default50/max100, exact CPU/RAM and image-name discovery filters and explicit project authority. Reuse Nova's native project-filtered catalog for non-admin tokens; independently check target private-flavor ACL only for a validated currently issued native admin role (the ACL API is admin-only). Check accepted shared-image membership. Return only safe boot-selection fields, GPU/schedule indicators and key name/type/fingerprint; never private/public key material, native control markers, endpoints or arbitrary properties.
- Preserve existing network list/get and `afterglow_vm_network_attach` write/idempotency/ownership/final dispatch behavior and verify it through the same MCP transport.
- Keep issued-role/current-role intersection, grant target ceilings, reader attenuation, exact caller identity, SDK deadlines/drain and no-admin-fallback behavior unchanged.

## Capabilities

### New Capabilities
- MCP-only safe discovery of VM provisioning selections with explicit availability limits and opaque provider resource markers.

### Modified Capabilities
- Canonical consumer registry compute inventory and version; existing network discovery/connection verified without duplicate tools or aliases.

## Impact

Backend adapters/registry, consumer-visible authority/redaction regressions, existing API/security/testing/architecture/changelog documentation. No SQL/config/dependency/native policy changes. No operational deployment, live resource mutation or guest SSH execution. Actual SDK over isolated HTTP plus MCP transport smoke does not prove deployed provider compatibility or successful guest login.
