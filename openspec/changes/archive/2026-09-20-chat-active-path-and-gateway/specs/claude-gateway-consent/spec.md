## ADDED Requirements

### Requirement: Gateway use requires explicit current tenant consent
Claude Gateway access SHALL require a non-revoked consent record for the authenticated user and active project at the configured terms version. Administrative provider/model enablement SHALL NOT create or imply that consent.

#### Scenario: Enabled model without consent
- **WHEN** an administrator enables a Claude-capable model but the tenant user has not accepted current Gateway terms
- **THEN** device approval and Gateway compatibility access remain denied

#### Scenario: Terms version changes
- **WHEN** the configured terms version advances
- **THEN** earlier consent no longer authorizes new approvals or compatibility requests until the user accepts the new version

### Requirement: Afterglow presents meaningful consent before approval
The tenant settings UI SHALL identify the project, Gateway purpose, data/API behavior, credential lifetime/revocation implications, current terms version, and the exact action being authorized before it enables acceptance or device-code approval.

#### Scenario: User reviews pending device code
- **WHEN** a user opens the verification URI with a live user code
- **THEN** the UI shows the code, current project, consent state, terms summary, and separate accept/approve actions

### Requirement: Consent is revocable and audited
The user SHALL be able to revoke project-scoped consent. Lumen SHALL record accepted version/time and revoked time and SHALL revoke all Gateway credentials for that user/project in the same transaction.

#### Scenario: Revoke from settings
- **WHEN** a consenting user revokes Gateway access
- **THEN** the UI reports the revoked state and existing Gateway tokens stop authenticating

### Requirement: Authorization recovery is actionable
When a code expires, consent is absent, the project is wrong, or a credential expires/revokes, the API and UI SHALL return safe reason codes and concrete steps to restart login in the correct project.

#### Scenario: Expired user code
- **WHEN** a user opens an expired verification code
- **THEN** the UI says the code expired and instructs the user to rerun `lumen-chat login` rather than presenting an approval action
