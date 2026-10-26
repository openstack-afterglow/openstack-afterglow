## Why

Impeccable init found no PRODUCT.md. The user confirmed broad cloud consumers as the primary audience, a cloud-and-AI integrated workspace as the core value, image-first landing/showcase creation, and an explicit development-only localhost:8400 CSP allowance for future live editing.

## What Changes

- Record confirmed durable product context in root PRODUCT.md without replacing DESIGN.md or defining a surface strategy.
- Store buildPath=comp in root .impeccable/config.json and configure the SvelteKit live entry at frontend/.impeccable/live/config.json.
- Allow exactly http://localhost:8400 in development script-src and connect-src, including runtime hook composition, without altering production CSP or existing resource origins.
- Verify development/production boundaries, existing hook behavior and actual served development headers. Do not start live injection, change application visuals, private settings, runtime deployments or authentication.

## Capabilities

### New Capabilities
- Persistent user-approved product record and future visual-work workflow defaults.

### Modified Capabilities
- Development-only CSP accommodation for the local Impeccable picker; production source restrictions and nonce/hash handling remain unchanged.

## Impact

Documentation and Impeccable configuration plus a bounded frontend CSP change. No backend/API/data/schema/service topology changes. Existing dirty work and production/local deployed services are preserved.
