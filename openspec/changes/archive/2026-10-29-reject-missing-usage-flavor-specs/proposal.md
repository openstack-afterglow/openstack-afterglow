## Why

Installed OpenStack SDK flavor decoding uses a default empty extra-spec mapping when a native HTTP200 body omits the extra_specs envelope. This can make unreadable GPU/additive scheduling classification look like an ordinary CPU flavor. The source-only usage feature must distinguish authoritative empty specs from missing authority before allocation or enrollment.

## What Changes

Add a shared strict raw GET decoder requiring an explicit string-map extra_specs envelope and 2xx status. Reuse valid inline native maps, including empty maps, without extra requests. Use the decoder for normal/catalog/managed consumer admission, scheduler catalog, managed annotation preservation and the additive administrator editor. Preserve no-redirect/no-reauth/no-retry transport. Missing or malformed authority fails closed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Instance usage schedule classification and additive flavor annotation authority.

## Impact

Backend read/admission and tests only; no schema/config or deployment change. Follow-up to archive/2026-10-29-manage-instance-usage-schedules. Real loopback native HTTP and installed SDK proof plus existing targeted regressions. No live cloud resources.
