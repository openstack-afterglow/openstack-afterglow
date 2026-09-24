## Context

Afterglow already has caller authentication, project rescope, Redis sessions, raw Zun adapters, xterm.js, global authenticated chrome, Cinder access, and Kolla/Kubernetes delivery paths. It does not have a safe global terminal. Tenant-project Zun containers or Cinder homes would be visible to other project members; browser-delivered Keystone or Zun proxy credentials would also cross the wrong trust boundary.

The approved design therefore separates two scopes. A dedicated `afterglow-cloud-shell` service project owns every container, network attachment, security group attachment, and persistent home volume. The current user's explicitly rescoped selected-project token is used only inside the shell for OpenStack CLI calls. Redis coordinates short-lived tickets, active users, heartbeats, and locks; OpenStack remains authoritative for containers and volumes. No Afterglow database schema is added.

## Goals / Non-Goals

**Goals:**
- Require explicit approval before each session and never remember consent.
- Provide one active session per user globally while preserving one 5 GiB home per user × selected project.
- Keep target Keystone and Zun proxy credentials out of browser responses, DOM, logs, Zun create fields, labels, URLs, and persistent home data.
- Delete ephemeral containers on every termination path while preserving homes until explicit, verified reset.
- Maintain a binary browser terminal relay, bounded control protocol, responsive accessible dock, and route-independent frontend lifetime.
- Reconcile orphaned managed containers after backend failure without deleting unknown resources or homes.
- Ship a non-root OpenStack CLI image and complete config/Kolla/CI/live contracts.

**Non-Goals:**
- Tenant-owned shell resources, password/application-credential storage, direct browser-to-Zun access, session restoration, multiple concurrent terminals, collaborative shells, arbitrary image/network/resource selection, privileged containers, Docker socket, SSH daemon, inbound public ports, home GC, or Compose-managed Zun/Kuryr/Cinder.

## Decisions

### Dedicated lifecycle scope and persistent home

`get_cloud_shell_project_connection()` uses the configured Afterglow service credentials scoped only to `cloud_shell.service_project_id`. The service project must differ from the general Afterglow service project. All lifecycle calls use this connection; caller connections never create or delete shell resources.

A workspace fingerprint is `sha256("cloud-shell-v1\0" + user_id + "\0" + target_project_id)`. Its volume name contains the first 16 hex characters; exact metadata contains managed owner, purpose, schema, the full fingerprint, and an HMAC signature. A distributed workspace lock protects discovery/create/reset. Zero exact matches creates a home and polls to `available`; one reuses it; duplicates, name-only mismatches, attachments, or unknown state fail closed. Explicit reset deletes only this exact volume and returns success only after bounded absence verification; absent is idempotent success. No automatic home GC exists.

Alternative: tenant-project homes. Rejected because project peers could inspect or delete another user's home through Cinder.

### Ephemeral container and service-owned network

Each approved session creates a new service-project Zun container from a digest-pinned image with fixed CPU/memory, non-privileged flags, one configured network, one configured egress-only security group, and one Cinder mount at `/home/cloudshell`. Labels contain only managed purpose, workspace fingerprint, session ID, and absolute expiry. Raw user IDs, usernames, target token, proxy token, and target project IDs are excluded. Container create/run and bounded `Running` polling are strict; any failure cleans only the exact session container and keeps the home.

Alternative: reusable containers. Rejected because token files and process state could cross sessions.

### Target-token bootstrap

Ticket issuance revalidates/rescopes the session Keystone token to the logical selected project, verifies user/project equality, and requires at least 120 seconds remaining. The token snapshot stays in Redis for a 60-second ticket TTL. The browser receives only an opaque 256-bit ticket and a fixed WebSocket path.

After the service-project container reaches `Running`, the backend creates an interactive exec for `/usr/local/bin/afterglow-cloud-shell-bootstrap`. It validates the Zun proxy URL scheme, configured origin, path, exact query keys, and response `uuid`/`exec_id`, then connects server-side. The bootstrap disables PTY echo, emits a fixed ready marker, accepts one bounded URL-safe-base64 JSON line, atomically writes 0600 JSON-as-YAML configuration under `/dev/shm/afterglow` tmpfs, drops to UID/GID 1000 with empty supplementary groups/capabilities and `no-new-privileges`, emits an OK marker, then execs login bash. The setuid helper is the only root transition. The browser sees neither pre-marker output nor credential bytes.

Alternative: token environment or browser transfer. Rejected because both leak credentials through inspectable process/browser surfaces.

### Atomic user-wide exclusivity

Redis keys use SHA-256 fingerprints, never raw user/project IDs. Ticket creation rate limits at 5/minute and atomically reserves the user globally for 60 seconds. WebSocket consumption uses one Lua transition: get/delete ticket, verify reservation ownership, and create the active user/session key. Active conflict returns 409/4410. Heartbeat TTL is 90 seconds and refreshes every 30 seconds. Cleanup uses compare-and-delete so a stale session cannot release a replacement session.

Redis failure rejects ticketing, provisioning, reset, and reconciliation. It never causes resource deletion.

### Browser protocol and time bounds

Browser terminal bytes use binary frames in both directions. Text frames are control only; the client sends bounded `resize`, and the server sends `status`, `warning`, `ready`, `exit`, or `error`. Binary input is at most 64 KiB, control JSON at most 2 KiB, columns are 20–500, and rows are 5–200. Close codes are fixed: 4401 ticket, 4403 origin/authorization, 4408 idle, 4410 active conflict, 4419 token/max lifetime, and 4500 provisioning/upstream failure.

Idle activity is terminal input/output only; ping and resize do not extend it. Cleanup closes the exec socket, stops/deletes the exact container, polls home back to `available`, and compare-deletes active/heartbeat keys. The deadline is the earliest of 20-minute idle, 60-minute maximum, or 60 seconds before Keystone expiry.

### Reconciliation

One replica holds a reconcile lock. It lists service-project containers and examines only resources with every exact managed label. Missing heartbeat past creation grace or absolute expiry triggers container cleanup. Redis read uncertainty causes a no-op. Duplicate or unknown resources produce warnings only. Reconciliation never deletes home volumes.

### Global frontend

A singleton `cloudShell.svelte.ts` controller owns `closed → consent → ticketing → provisioning → authorizing → ready → ending → closed`, error transitions, dock mode, socket, project binding, and terminal state. The root layout mounts the trigger, authorize dialog, and dock once, before the theme action. Auth loss/project change closes local state immediately; logout closes before Keystone logout/`clearAuth`. Reload does not restore a session.

Mobile uses a full-width bottom sheet capped at 88dvh without drag resize. Tablet/desktop use a non-modal dock to the right of the 15rem sidebar, with keyboard/pointer height resizing, 44px minimized bar, and maximization below the app header. Existing UI primitives/tokens own status, actions, alerts, modal focus, confirmation, layers, and reduced motion. Tutorial mode advertises `cloud_shell=false` and never fakes resource success.

### Image and delivery

The new Python 3.12 slim target contains OpenStackClient/openstacksdk and Zun, Manila, Magnum, Trove, Barbican, Octavia, Heat, Designate, and Swift plugins plus bounded operator utilities. It runs UID/GID 1000, has no sudo/daemon/compiler/Docker tools, and owns only the bootstrap/profile scripts. Pseudo-TTY tests prove marker order, token non-echo, ephemeral file mode/path, privilege drop, plugin discovery, and home persistence across two real container runs.

Config is synchronized across `backend/app/config.py`, `afterglow.conf.example`, `generate_k8s.py`, site config, and Kolla. Production requires an image digest, trusted HTTPS Keystone v3 URL, and WSS Zun origin; development HTTP/WS is loopback only. Kolla resolves exactly one dedicated project and verifies stock Zun/Kuryr/etcd/Cinder integration, network/SG ownership, no SG ingress, authenticated Zun/Cinder access, image availability, and live outbound access without creating those resources implicitly.

## Risks / Trade-offs

- [Zun interactive exec/proxy behavior varies] → Validate exact API/proxy contracts and fail closed; no command-emulation fallback.
- [Service credentials can manipulate dedicated resources] → Scope only to the dedicated project, use exact signed metadata/labels, and never inject the service token into the shell.
- [Cinder duplicate or attached homes] → Refuse adoption/reset and require operator diagnosis; never choose or delete arbitrarily.
- [Redis loss leaves orphan containers] → Stop provisioning/deletion and reconcile only after Redis certainty returns; label expiry enables later safe cleanup.
- [Browser disconnect is not a trustworthy close] → Heartbeat expiry plus bounded idle/max/token deadlines clean server resources.
- [Home persists user files] → Consent/reset copy states persistence and destructive scope explicitly; credentials live only under tmpfs `/run/afterglow`.
- [Image/plugin supply-chain weight] → Lock dependencies, publish immutable digests, smoke command discovery, and precheck compute-node access.

## Migration Plan

1. Build, test, publish, and digest-pin the Cloud Shell image.
2. Operator explicitly creates the dedicated project, network/router, egress-only security group, quotas, and service-account role assignment.
3. Deploy disabled config; run Kolla/Kubernetes prechecks and authenticated dedicated-scope Zun/Cinder probes.
4. Enable the feature and run the live dedicated smoke user flow: approve, CLI commands, close/container absence/home presence, reopen/sentinel persistence, reset/volume absence.
5. Rollback disables new tickets, waits or explicitly closes active sessions, verifies container absence, and removes only operator-created infrastructure after retained homes are handled explicitly.

## Open Questions

None. Cloud image digest, dedicated resource IDs, endpoint origins, quota sizing, and live credentials are required operator inputs.
