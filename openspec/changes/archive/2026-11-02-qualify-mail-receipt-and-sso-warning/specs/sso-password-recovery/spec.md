## MODIFIED Requirements

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
