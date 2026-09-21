## Why

Afterglow lacks a route-independent OpenStack shell that preserves user project scope without exposing Keystone credentials to the browser or other tenant members. A managed Cloud Shell can provide passwordless CLI access while isolating lifecycle resources in a dedicated service project and preserving each user's home data across ephemeral sessions.

## What Changes

- Add an opt-in global Cloud Shell available from every authenticated route after explicit approval for each new session.
- Create every ephemeral Zun container and persistent 5 GiB Cinder home in a dedicated `afterglow-cloud-shell` service project; bind homes to user × selected-project fingerprints.
- Rescope the current user's Keystone token to the selected project and inject it only through the backend-controlled interactive exec bootstrap, never through browser payloads, Zun container fields, or persistent storage.
- Enforce one active Cloud Shell per user across projects with atomic Redis tickets, reservations, active markers, heartbeats, locks, and fail-closed reconciliation.
- Add workspace inspect/reset HTTP APIs and a binary terminal WebSocket relay with bounded text control frames, resize validation, fixed close codes, and idle/max/token-expiry cleanup.
- Add a non-root Cloud Shell image with OpenStackClient and the supported service plugins, plus bootstrap pseudo-TTY tests and Docker smoke validation.
- Add a singleton Svelte controller, approval dialog, responsive terminal dock, persistent route-level mount, project/logout cleanup, and shared token-based xterm theming.
- Add Kubernetes/Kolla configuration, production digest/HTTPS/WSS validation, dedicated project/network/security-group prechecks, test targets, live checks, and deployment documentation.
- Migrate the existing container exec ticket endpoint to the same purpose-tagged atomic ticket helper without changing its external route or TTL.

## Capabilities

### New Capabilities
- `global-cloud-shell`: Dedicated-project Zun session lifecycle, persistent Cinder home ownership, server-side target-token bootstrap, atomic Redis/WebSocket protocol, global responsive UI, image, deployment, reconciliation, and reset requirements.

### Modified Capabilities

None.

## Impact

- Backend: configuration, site projection, Keystone/Zun/Cinder adapters, new Cloud Shell/ticket services and router, startup lifecycle, audit and security tests.
- Frontend: site-config/mock contract, root layout, singleton controller, Cloud Shell components, shared terminal theme, responsive styles and tests.
- Delivery: `cloud-shell/`, root Dockerfile/workflow, package/test targets, Kubernetes generator, Kolla role/templates/prechecks, live tests.
- Documentation: root architecture/design/changelog and API, deployment, security, index, and Kolla guides.
- External prerequisites: Redis, Keystone, Zun/Kuryr/Cinder, a dedicated service project/network/egress-only security group, and an immutable Cloud Shell image digest.
