## Why

The reported HTTPS request to `/api/v1/admin/version/` receives a Starlette slash-normalization redirect to HTTP. Running Kolla backends use Uvicorn's loopback-only proxy trust default although HAProxy connects from controller API addresses. An in-container middleware probe confirmed that HTTPS forwarding is ignored for all three controller peers.

## What Changes

- Render explicit Uvicorn proxy-header support and a bounded trusted-peer list from the canonical HAProxy inventory's API addresses, including loopback. Permit an operator override for different trusted ingress topology; never default to `*` on host networking.
- Check Compose, Kubernetes/Helm and explicit OAuth/public URL generation for the same scheme-loss mechanism. Keep genuine internal HTTP and configured public HTTPS origins distinct; do not disable slash redirects or rewrite every Location header.
- Add consumer-visible regression coverage for HTTPS redirects, HTTP preservation, query/method retention and forged headers from untrusted peers.
- Publish a patch release after local gates and exact-commit GitHub Actions, then replace the Afterglow Kolla role through the standard inventory and service-scoped lifecycle.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Reverse-proxy request scheme recognition and absolute redirect URL generation in Kolla.

## Impact

Deployment launch configuration only unless the audit proves another faulty scheme boundary. Authentication, API paths, datastore schema, image behavior and unrelated services are unchanged. Preserve the shared dirty checkout, operator secrets, existing volumes and rollback configuration. Completion requires actual running-container settings plus public HTTPS redirect and authentication-boundary verification.
