## 1. Backend foundation

- [x] 1.1 Add Cloud Shell configuration parsing, validation, example values, and public capability
- [x] 1.2 Add shared atomic Redis WebSocket ticket issue and consume service
- [x] 1.3 Add strict Zun endpoint, lifecycle, metadata, wait, and interactive-exec helpers
- [x] 1.4 Add dedicated Cloud Shell service-project Keystone connection
- [x] 1.5 Implement persistent Cinder homes, user-wide sessions, lifecycle cleanup, and reconciliation
- [x] 1.6 Add workspace/ticket HTTP and binary terminal WebSocket routes
- [x] 1.7 Wire router mount, audit prefix, startup reconciliation, and interval cleanup
- [x] 1.8 Migrate container exec tickets to the atomic shared ticket service
- [x] 1.9 Add backend config, home, concurrency, security, protocol, and cleanup tests

## 2. Bootstrap image and CI

- [x] 2.1 Add credential-free non-root Cloud Shell image, bootstrap helper, and OpenStack plugins
- [x] 2.2 Add pseudo-TTY tests, Docker smoke, workflow target, and multi-architecture publication
- [x] 2.3 Add focused Cloud Shell image, backend, and live test targets to package scripts

## 3. Deployment integration

- [x] 3.1 Render complete Cloud Shell configuration through Kubernetes generation paths
- [x] 3.2 Add Kolla defaults, templates, project resolution, role assignment, and prerequisite prechecks
- [x] 3.3 Add Kolla, Kubernetes, workflow, and live contract tests

## 4. Frontend implementation

- [x] 4.1 Add site-config types and mock capability data
- [x] 4.2 Implement singleton Cloud Shell consent/session state machine and project fencing
- [x] 4.3 Build trigger, approval dialog, responsive dock, and binary xterm terminal
- [x] 4.4 Mount the global shell in root layout and close before project switch/logout
- [x] 4.5 Extract token-based xterm theme handling and migrate existing terminal components
- [x] 4.6 Add responsive shell geometry/styles and document the design contract
- [x] 4.7 Add frontend consent, controller, protocol, cleanup, reset, and responsive tests

## 5. Documentation and verification

- [x] 5.1 Document Cloud Shell API, architecture, security, dedicated deployment, quotas, and rollback
- [x] 5.2 Update changelog, architecture review text, and OpenSpec checkboxes
- [x] 5.3 Run focused backend, frontend, deployment, workflow, and image smoke checks
- [x] 5.4 Verify actual responsive UI at 390, 767, 768, 1023, 1024, and 1440 pixels
- [x] 5.5 Attempt the live target; it skipped before destructive work because `services.cloud_shell=false`, so live Zun/Cinder verification remains an explicit gap
- [x] 5.6 Run full gate, stamp architecture, validate the complete working snapshot in an isolated index, and pass staged guard
- [x] 5.7 Archive the completed OpenSpec change
