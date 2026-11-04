## ADDED Requirements

### Requirement: Native standard project authority
The four services SHALL authorize current project manager/member management and reader nonsecret reads without requiring dedicated service roles, while preserving ownership, target, credential attenuation and genuine human system administration boundaries.

#### Scenario: Core roles without service roles
- **WHEN** a current manager, member or reader calls the native service for an owned project resource
- **THEN** manager/member can perform allowed management, reader can perform nonsecret reads, and reader writes and foreign/private resources remain denied.

#### Scenario: Restricted credential preview
- **WHEN** Afterglow checks native policy with the original restricted project credential
- **THEN** the native capability endpoint returns the real permitted/denied result without administrator-token fallback or credential escalation.

### Requirement: Traceable compatible publication and rollout
Each service release SHALL have an immutable version, exact-SHA CI, published image identities, packaged Kolla roles and actual runtime evidence. Existing deployed repairs and datastore/key/config SHALL be preserved.

#### Scenario: Concurrent unrelated source work
- **WHEN** a shared checkout or newer dev contains unrelated unfinished/schema work
- **THEN** the release excludes that work without overwriting it and explicitly resolves release/integration compatibility rather than silently rolling back deployed repairs.

#### Scenario: Operational deployment acceptance
- **WHEN** canonical Kolla deployment completes
- **THEN** full recap and each controller digest/revision/readiness are recorded together with authenticated role acceptance, and missing evidence is reported as unverified rather than success.
