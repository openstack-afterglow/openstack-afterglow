## ADDED Requirements

### Requirement: Signup link visibility is independent from enrollment authority
The system SHALL persist strict boolean `public_signup_button_visible` in the revisioned system-administrator enrollment policy. Only an absent policy row MAY use `[auth].public_signup_button_visible=true`; a saved row SHALL override configuration. Public `signup_button_visible` SHALL combine this display choice with public-email admission and SMTP readiness. Hiding the link SHALL NOT disable delivered-email verification, direct signup, permitted external enrollment, or existing recovery. A domain manager SHALL NOT change this global policy. Migration101 SHALL add only the non-null true-default column before changed readers and writers, preserving existing policy fields, quotas, revision, rows, identities, grants and absent-row fallback.

#### Scenario: Administrator hides the link but permits email and OIDC
- **GIVEN** public-email signup and SMTP are ready and the current administrator saves display visibility false
- **WHEN** an unauthenticated user opens login or directly opens signup
- **THEN** login omits the signup link while direct email signup, permitted SSO selection and recovery remain available under their existing admission and verification guards

#### Scenario: Display visibility does not enable admission
- **GIVEN** stored display visibility true but public-email admission is disabled or SMTP is not ready
- **WHEN** login discovers current signup options
- **THEN** the link remains hidden and visibility does not authorize an otherwise rejected signup request

### Requirement: Saved manager admission narrows new organization autojoin
New external organization admission SHALL satisfy operator-managed provider autojoin rules and, when a domain policy row is configured, that exact domain's saved signup opt-in and email-host restrictions. A manager SHALL NOT expand operator provider trust or public account authority. Existing members SHALL NOT be rejected solely by new-member signup settings, while existing login policies and canonical identity/federation ownership remain authoritative. An absent manager row SHALL preserve the approved operator baseline rather than create a policy or imply an explicit denial.

#### Scenario: A saved manager policy rejects an otherwise allowed new member
- **GIVEN** operator provider rules allow the email but the configured organization policy disables signup or excludes its host
- **WHEN** a nonmember completes provider authorization, including an already bound canonical subject
- **THEN** organization admission fails before reader grants, native provisioning or final session exchange and existing accounts and federation tuples remain unchanged

#### Scenario: A current member signs in after new admission closes
- **GIVEN** a canonical user already has verified organization membership and satisfies current login policy
- **WHEN** signup admission is disabled for new members
- **THEN** that signup setting does not revoke the existing membership or independently block its login

### Requirement: Native administrator executor honors optional legacy marker semantics
After fresh native system-administrator caller verification, the fixed configured administrator executor SHALL require an authenticated project-scoped native token, a native project ID and admin role, and native SDK administrator-project semantics. An omitted legacy `is_admin_project` field MAY use the SDK's true default. Explicit false, null, non-boolean markers and invalid scopes SHALL fail closed. Logical workspace, actor and immutable identity home SHALL remain separate from the executor, with no human admin grant, arbitrary requested-project rescope or system-token fallback for project-only providers.

#### Scenario: Valid Keystone token omits the legacy marker
- **GIVEN** fresh caller system authority and a configured executor token with native project scope and admin role
- **WHEN** Keystone omits the legacy marker while its native SDK meaning is true
- **THEN** the executor is accepted and native provider policy still authorizes every downstream request

#### Scenario: Native scope is explicitly invalid
- **WHEN** the token explicitly denies administrator-project status, has malformed marker type, lacks admin role/project scope, or caller authority was revoked
- **THEN** execution is rejected without native resource mutation or fallback authority
