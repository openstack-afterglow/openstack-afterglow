## Why

OpenStack clients already reuse freshly validated AccessInfo within one API request, but new authentication operations and SDK connections construct independent HTTP pools. Reuse transport connections across requests without caching caller authority or extending login/native token lifetimes.

## What Changes

- Share only process-owned HTTP connection pools through a Keystoneauth TCPKeepAliveAdapter. Each Keystoneauth/requests Session, auth plugin, cookie jar, headers, catalog/discovery state and SDK Connection remains operation-local.
- Preserve installed Requests TLS/CA/client-certificate/proxy pool partitioning, existing timeouts, redirects and retry behavior. Serialize proxy-manager creation, not network calls. Bound idle pools using library defaults.
- Attach the transport to native Keystone, SDK and MCP connection factories, preserving authentication/scoping and routing contracts.
- API/standalone worker shutdown closes pools after draining work; individual operation/session closure must not close other requests' transport.
- Prove real HTTP reuse after closing an earlier client, fresh native authentication across requests, caller/cookie isolation, concurrency, TLS trust separation, denial/error propagation, no mutation replay and shutdown cleanup.

## Capabilities

### New Capabilities

- Process-local OpenStack HTTP transport reuse without shared credentials or authority snapshots.

### Modified Capabilities

- Native connection resource ownership: request-local client state and process-local socket pools have separate lifetimes. Existing fresh native authorization checks remain unchanged.

## Impact

Backend native client factories and API/worker cleanup only. No endpoint, wire contract, DB/schema, browser session lifetime, deployment configuration, IAM changes, rollout, commit or push. Requests 2.33.1 / Keystoneauth 5.13.1 are installed; the implementation preserves their TLS-keyed pool and keepalive behavior. Current SDK Connection.close() does not directly close its HTTP session; this change must not rely on it to dispose process-owned pools. Existing concurrent working-tree changes and index remain untouched.
