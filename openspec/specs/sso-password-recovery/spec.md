# sso-password-recovery Specification

## Purpose
TBD - created by archiving change enable-sso-password-recovery. Update Purpose after archive.
## Requirements
### Requirement: SSO users can create a local password using their registered mailbox

The system SHALL retain the authenticated profile creation workflow and SHALL permit an eligible SSO user's unique canonical email to initiate that same workflow through password recovery when a fresh native credential snapshot proves absence. Redemption SHALL require both the delivered one-hour one-use proof and a fresh same-account SSO session after issuance. The system SHALL preserve the exact native user UUID, identity home and federation associations and SHALL warn that a local password bypasses IdP MFA/deactivation.

#### Scenario: Profile creation by an SSO user
- **WHEN** an enabled eligible SSO user has no native password and requests creation from their profile
- **THEN** a proof is delivered only to their unique registered address and creation requires the same-user fresh provider session and native create-only identity-revision guard

#### Scenario: Password recovery starts first creation
- **WHEN** a password recovery request identifies one eligible SSO user whose native state is absent
- **THEN** the response remains accepted202 and the delivered proof enters password_create rather than attempting stock PATCH or existing-only reset

#### Scenario: Existing credential recovers by mailbox
- **WHEN** an eligible SSO user's native state is existing, regardless of stale local metadata
- **THEN** email recovery uses the conditional existing-password reset and preserves the original native identity

#### Scenario: Proof cannot bypass owner or state transitions
- **WHEN** the provider session belongs to another user, precedes proof issuance, or the email/native identity revision changes
- **THEN** first creation is refused without overwriting a credential or replaying the proof

### Requirement: Administrators can initialize or reset SSO credentials without metadata-based denial

Fresh system administrators SHALL be able to initialize an absent SSO local password or reset an existing one through native conditional endpoints and send the generated password only to the unique registered mailbox. Native capability, state and identity binding SHALL be validated before dispatch; unsupported native SHALL refuse before native writes, audit dispatch fence or session revocation. The existing confirmation, TLS mail, rate limits, service-identity exclusion, audit journal and outcome-unknown protections SHALL remain in force. Before confirmation, all supported UI locales SHALL explain that the operation initializes a password if absent or replaces an existing one, and that an SSO local password can bypass IdP MFA and IdP account deactivation. The generated-password email SHALL retain the same conditional risk advice and mailbox exposure warning without asserting forced expiry.

#### Scenario: Administrator initializes an SSO credential
- **WHEN** fresh authorized administrator confirmation targets an eligible native-absent SSO user
- **THEN** one native create-only request uses exact user/home/email/revision and successful completion mails the generated password and revokes target sessions

#### Scenario: Administrator resets a stale-marker SSO credential
- **WHEN** an eligible SSO user has actual existing native history but absent or false local metadata
- **THEN** one conditional reset is used rather than rejecting metadata or attempting first creation

#### Scenario: Native support or binding is unavailable
- **WHEN** capability is missing or native state/revision is invalid or changed before dispatch
- **THEN** the operation is rejected before credential mutation and never falls back to stock PATCH for SSO

#### Scenario: Delivery or native completion fails
- **WHEN** native completion is unknown or successful mutation is followed by mail/session/audit failure
- **THEN** the operation reports the distinct known/unknown effects, never automatically retries the write and never exposes the password outside native setter and registered-mail delivery

#### Scenario: Initial local password is explicitly explained before submission
- **WHEN** an administrator opens the password confirmation in any supported locale
- **THEN** the warning describes both absent/existing behavior and IdP MFA/deactivation bypass before any credential mutation and never relies on SSO metadata as proof of absence
