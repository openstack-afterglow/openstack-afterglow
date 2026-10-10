# Scoped service roles

## Purpose
Preserve existing project role identities while providing safe explicit area_grade service delegation and current-authority enforcement across Afterglow UI/BFF and independent native services.

## Requirements

### Requirement: Preserve roles and canonicalize managed names
Afterglow SHALL reuse existing unique global project_owner, project_admin, project_member, project_reader and native core role IDs, assignments and safe inference links. New or renamed custom roles SHALL use lower-case area_grade with exactly one underscore. Whitespace runs in each component, including boundary whitespace, SHALL become hyphens; each component SHALL contain only ASCII letters, digits and hyphens and at least one letter or digit. Native protected role names remain exceptions. Metadata-only edits SHALL NOT silently rename unrelated legacy roles.

#### Scenario: Explicit role naming
- **WHEN** a system administrator creates an area or grade containing spaces
- **THEN** the UI previews and backend persists its canonical hyphenated area_grade name, subject to collision and component validation.

### Requirement: Explicit reusable service-grade presets
Afterglow SHALL provide read-only preset preview and explicit verified-system-admin idempotent application. Each service admin/editor/user/reader parent SHALL initially imply its lower grade and exact granular action leaves. Non-reader leaves SHALL initially imply their own service_reader discovery parent, never native membership or OpenStack admin/manager. Existing roles and links SHALL be preserved and reused. Application SHALL reject unsafe, ambiguous, domain-scoped or privileged graph bindings, report partial provider changes without deleting shared roles and SHALL NOT run during GET, login or startup.

#### Scenario: Idempotent reviewed cutover
- **WHEN** the administrator confirms preset application twice with existing underscore project roles and service roles
- **THEN** original IDs, assignments and unrelated links remain; only missing safe roles and edges are created and the second application creates none.

### Requirement: Current role graph is authoritative
Afterglow BFF and native Waygate, Lumen, Drover and Palimpsest SHALL derive action authority from current effective project assignments and the actual unique-global role-ID implication DAG. Static preset expansion, stale JWT labels, DB manager rows, plain member and project administrator roles SHALL NOT imply service entitlement. Non-reader leaves require effective native member; inventory leaves require effective reader or member. Unverified raw admin/manager SHALL fail closed. Unknown graph references, cycles, ambiguous bindings and directory failure SHALL grant no fallback authority. Native APIs SHALL independently retain project, ownership, key scope, credential grade and verified platform authority checks.

#### Scenario: Downgrade with retained parent
- **WHEN** the parent role remains assigned but its current edge to a service action is removed
- **THEN** the next authorized BFF/native request cannot execute that action and unrelated still-effective inventory remains available.

### Requirement: Project-scoped delegation preserves ownership
Project management SHALL use current Keystone owner/admin authority and safe current role graphs. Only an effective owner SHALL grant or revoke project_owner or project_admin; project admins may manage eligible ordinary project/service grants without OpenStack escalation. Member updates SHALL be original-project-bound, change managed direct assignments only, preserve unrelated and group grants and protect the last effective owner, including inherited/group-derived ownership. Invitations SHALL assign project_member/project_reader without service privileges. Legacy DB-manager conversion SHALL require explicit system-admin execution and a selected owner, never infer ownership from DB metadata.

#### Scenario: Last effective owner protection
- **WHEN** a role or membership mutation would remove the project's last effective owner
- **THEN** the mutation is denied before provider changes.

### Requirement: Service actions remain independently attenuated
Waygate SHALL separate nonsecret inventory, enabled caller-assigned profile use, editor metadata changes and administrator destructive/routing/security actions. Lumen SHALL independently check chat, images, audio and tools, distinguish editor configuration from destructive administration and intersect API key scopes with current owner authority before new I/O. Drover SHALL issue native user/editor restricted Kubernetes credentials without administrator fallback and reserve full certificates/deletion for distinct administrator leaves. Palimpsest SHALL separate metadata, byte download, publish and owned key actions while attenuating issuance and use to current owner authority. Global platform/builder policy and machine callbacks SHALL remain independently authenticated.

#### Scenario: Narrow user and editor grants
- **WHEN** a user receives only a specific service use/download leaf or editor receives create/update leaves without administrator leaves
- **THEN** authorized owned use or metadata editing succeeds while undelegated modalities, foreign secrets, deletion, credential administration and global authority remain denied.

### Requirement: UI refresh and disclosure lifecycle
UI controls SHALL use fresh explicit service capabilities, not native can_write or stored role labels. Permission refresh or lookup failure SHALL disable risky actions and mask retained same-actor private media and one-time secrets without treating unavailability as confirmed revocation. Confirmed required-leaf revocation, actor/project change or logout SHALL discard those private resources; regrant SHALL NOT resurrect them. Late secret-bearing responses SHALL recheck actor, project and requested grade before disclosure. Full Drover certificates SHALL use a separate explicit confirmation.

#### Scenario: Same-actor permission failure and definitive revocation
- **WHEN** current capability lookup fails during token renewal
- **THEN** existing private media/secret values are hidden, no new privileged I/O or late credential disclosure occurs, and the same values return only after authority is confirmed.
- **WHEN** authority is definitively revoked instead
- **THEN** retained private values are discarded and subsequent regrant does not restore them.
