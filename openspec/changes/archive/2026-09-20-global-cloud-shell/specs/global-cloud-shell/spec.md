## ADDED Requirements

### Requirement: Cloud Shell is explicitly configured and gated
The system SHALL expose Cloud Shell only when `services.cloud_shell` and Zun are enabled and every required dedicated-project, image, network, security-group, Keystone, and Zun WebSocket setting validates. Public site configuration SHALL reveal only the `services.cloud_shell` boolean.

#### Scenario: Invalid enabled configuration
- **WHEN** Cloud Shell is enabled with a missing prerequisite, shared general service project, mutable production image, untrusted endpoint, or out-of-range resource limit
- **THEN** configuration fails closed before routes or UI are exposed

### Requirement: Approval creates only a bounded ticket
Every new session SHALL require an explicit approval dialog. Approval SHALL revalidate and rescope the current Keystone token to the selected logical project, require at least 120 seconds remaining, reserve the user globally, and return only an opaque ticket, fixed WebSocket path, and expiry.

#### Scenario: Approval accepted
- **WHEN** an authenticated user approves Cloud Shell for the selected project
- **THEN** the server creates no OpenStack resource, stores a 60-second server-side token snapshot/reservation, and returns no Keystone/Zun/service credential

#### Scenario: User already active
- **WHEN** the same user has an active or reserved shell in any project
- **THEN** ticket creation fails with 409 and identifies an active-session conflict without leaking resource IDs

### Requirement: One active shell exists per user globally
The system SHALL allow at most one active Cloud Shell per user across every project. Ticket consume, reservation ownership, and active-session creation SHALL occur atomically, and cleanup SHALL compare values before release.

#### Scenario: Two tickets race
- **WHEN** concurrent WebSockets race for the same user
- **THEN** exactly one becomes active and the other closes with 4410 or 4401

#### Scenario: Stale cleanup
- **WHEN** cleanup from an older session runs after a replacement exists
- **THEN** compare-and-delete preserves the replacement active and heartbeat keys

### Requirement: Persistent home is isolated by user and target project
The system SHALL derive a SHA-256 workspace fingerprint from user ID and selected project ID and SHALL maintain exactly one default 5 GiB Cinder home in the dedicated Cloud Shell service project with exact managed metadata.

#### Scenario: First workspace use
- **WHEN** no exact metadata match exists under the workspace lock
- **THEN** the service creates one volume, waits boundedly for `available`, and mounts it at `/home/cloudshell`

#### Scenario: Existing workspace reuse
- **WHEN** exactly one matching available home exists
- **THEN** later ephemeral sessions reuse it without shrinking, replacing, or recursively changing its contents

#### Scenario: Ambiguous workspace
- **WHEN** duplicate metadata matches, a name-only collision, attachment, error, or unknown state exists
- **THEN** the service refuses adoption, deletion, and success claims

### Requirement: Workspace reset is explicit and verified
`DELETE /api/v1/cloud-shell/workspace` SHALL target only the current user × selected-project fingerprint. It SHALL reject active sessions, ambiguity, attachments, and unknown Cinder state and SHALL return success only after polling verified Cinder absence. An already absent home SHALL return idempotent 204.

#### Scenario: Confirmed reset
- **WHEN** the exact home is unattached and deletion reaches Cinder absence
- **THEN** the API returns 204 and audit records contain only user/project/action/result

#### Scenario: Reset uncertainty
- **WHEN** deletion, attachment, discovery, or absence cannot be proven
- **THEN** the API returns 409 or 503 and the frontend does not show success

### Requirement: Every session uses an ephemeral hardened Zun container
After valid ticket consumption, the system SHALL create a new container only in the dedicated service project with a digest-pinned image, fixed resources, configured dedicated network and egress security group, persistent home mount, no privilege/host mount/Docker socket, and labels without raw identity or credentials.

#### Scenario: Successful provisioning
- **WHEN** home discovery succeeds and the container reaches `Running`
- **THEN** the server advances through workspace/container/terminal/authorizing/ready status events

#### Scenario: Provisioning failure
- **WHEN** image pull, quota, network, attach, or running-state polling fails
- **THEN** only the exact session container is cleaned, the home is preserved, and the socket closes with 4500

### Requirement: Target credentials are injected only through bootstrap
The system SHALL create an interactive exec for the fixed bootstrap path, validate the proxy URL against the configured WSS origin and exact query/identity contract, wait for the fixed ready marker, send one bounded URL-safe-base64 JSON token payload with echo disabled, and release browser bytes only after the fixed OK marker.

#### Scenario: Bootstrap succeeds
- **WHEN** the helper validates payload and writes 0600 JSON-as-YAML files under `/dev/shm/afterglow` tmpfs
- **THEN** it drops to UID/GID 1000 with no-new-privileges/empty capabilities, starts login bash, and the browser receives only post-ACK terminal bytes

#### Scenario: Credential leakage attempt
- **WHEN** pre-ready/pre-ACK output, malformed proxy URL, unexpected query keys, marker mismatch, or echoed token bytes occur
- **THEN** the server discards output, closes the session, cleans the container, and never forwards credential-bearing bytes

### Requirement: Browser WebSocket separates binary terminal data and text control
Terminal input/output SHALL use binary frames. Text frames SHALL be bounded control JSON; resize columns SHALL be 20–500 and rows 5–200. Unknown, oversized, or malformed frames SHALL close as protocol errors. Resize and ping SHALL NOT count as terminal activity.

#### Scenario: Ready interactive terminal
- **WHEN** bootstrap ACK succeeds
- **THEN** the server emits `ready`, forwards binary bytes bidirectionally, and debounces valid resize calls to Zun

#### Scenario: Invalid frame
- **WHEN** binary input exceeds 64 KiB or control text exceeds 2 KiB or violates schema
- **THEN** the connection closes without forwarding the invalid frame upstream

### Requirement: Session deadlines and cleanup are fail closed
The server SHALL terminate at the earliest of 20-minute input/output idle, configured maximum 60 minutes, or 60 seconds before Keystone expiry. Normal close, disconnect, timeout, project switch, logout, and error SHALL share cleanup that closes exec, deletes the exact container, waits for home `available`, and compare-deletes Redis state.

#### Scenario: Idle timeout
- **WHEN** no terminal input/output occurs for the configured idle period
- **THEN** the WebSocket closes with 4408 and cleanup preserves the home

#### Scenario: Token or maximum lifetime
- **WHEN** token safety margin or maximum duration is reached
- **THEN** the WebSocket closes with 4419 and cleanup preserves the home

### Requirement: Reconciliation removes only proven orphan containers
A periodic single-replica reconciler SHALL inspect only service-project containers with every exact managed label. It SHALL delete containers with missing heartbeat beyond grace or expired absolute lifetime, SHALL never delete homes, and SHALL perform no deletion when Redis state is uncertain.

#### Scenario: Proven orphan
- **WHEN** an exactly managed container lacks heartbeat beyond creation grace
- **THEN** the reconciler deletes that container and records safe diagnostics

#### Scenario: Unknown resource or Redis failure
- **WHEN** labels are incomplete/duplicated or Redis cannot prove heartbeat state
- **THEN** reconciliation logs a warning and changes no resource

### Requirement: Existing container exec tickets are atomic
The existing `/api/v1/containers/{id}/exec-ticket` contract SHALL use the shared purpose-tagged atomic consume helper while retaining its route and TTL.

#### Scenario: Ticket replay
- **WHEN** a consumed container exec ticket is presented again
- **THEN** the second connection is rejected before command execution

### Requirement: Global frontend preserves consent and scope
The authenticated root layout SHALL mount one trigger, approval dialog, singleton controller, and terminal dock across route navigation. It SHALL close local shell state immediately on auth loss/project change and before logout; reload SHALL not restore a session. Tutorial/mockup mode SHALL hide the feature.

#### Scenario: New session
- **WHEN** no active minimized session exists and the trigger is activated
- **THEN** the approval dialog explains current project authority, ephemeral token files, persistent 5 GiB home, and timeout behavior before any API call

#### Scenario: Minimized session
- **WHEN** a session is minimized and the trigger is activated
- **THEN** the existing dock restores without another approval or ticket request

### Requirement: Dock is responsive, accessible, and token based
Mobile SHALL use a full-width bottom sheet up to 88dvh without drag resize. Tablet/desktop SHALL use a non-modal sidebar-offset bottom dock with bounded pointer/keyboard resizing, a 44px minimized bar, and maximization below the header. Status SHALL always include text, provisioning/errors SHALL be polite live regions, terminal Escape SHALL reach the shell, and reduced motion SHALL remove panel transitions.

#### Scenario: Responsive cutovers
- **WHEN** the viewport is 390, 767, 768, 1023, 1024, or 1440 pixels
- **THEN** navigation, project switch, trigger, terminal status/actions, consent, error/retry, and reset remain reachable without content remount or horizontal overflow

### Requirement: Cloud Shell image is non-root and credential free
The repository SHALL build a locked Python 3.12 slim image with OpenStackClient/openstacksdk and Zun, Manila, Magnum, Trove, Barbican, Octavia, Heat, Designate, and Swift plugins plus required shell utilities. It SHALL use UID/GID 1000 and contain no sudo, Docker socket/client, compiler, daemon, or credential.

#### Scenario: Pseudo-TTY and Docker smoke
- **WHEN** tests execute the bootstrap in a real pseudo-TTY and reuse one mounted home across two containers
- **THEN** marker order, no token echo, ephemeral 0600 config, privilege drop, plugin discovery, and sentinel persistence all pass

### Requirement: Deployment validates dedicated prerequisites
Kubernetes and Kolla SHALL render the same Cloud Shell settings. Production SHALL require an immutable image digest, trusted HTTPS Keystone v3 URL, WSS Zun origin, distinct dedicated project, owned network/security group with no ingress, stock Zun/Kuryr/etcd/Cinder integration, authenticated Zun/Cinder access, image availability, and outbound DNS/catalog access. Deployment SHALL not implicitly create or delete those resources.

#### Scenario: Failed precheck
- **WHEN** any dedicated ownership, image, endpoint, inventory, integration, or authenticated access prerequisite fails
- **THEN** deployment stops before changing the running Afterglow service

#### Scenario: Disabled deployment
- **WHEN** Cloud Shell is disabled
- **THEN** Compose remains unchanged and existing Afterglow/Zun behavior is preserved
