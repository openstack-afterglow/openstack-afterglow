## ADDED Requirements

### Requirement: CLI authorization follows OAuth device grant semantics
An enabled Claude Gateway SHALL let a public CLI request a bounded device code and user code without a client secret, display the configured verification URI, and poll the token endpoint at the server-specified interval.

#### Scenario: Begin login
- **WHEN** the CLI submits the supported public client ID and compatibility scopes
- **THEN** the server returns a high-entropy device code, human user code, verification URI, complete verification URI, expiry, and poll interval without issuing a credential

#### Scenario: Pending authorization
- **WHEN** the CLI polls before browser approval
- **THEN** the token endpoint returns `authorization_pending` and no credential

#### Scenario: Excessive polling
- **WHEN** the CLI polls faster than the allowed interval
- **THEN** the token endpoint returns `slow_down` and increases the effective interval

### Requirement: Browser approval is authenticated and one-time
Only a Keystone-authenticated user in the target project SHALL inspect, approve, or deny a user code. Approval SHALL bind the device authorization to that user/project, require current consent, and be consumed at most once.

#### Scenario: Wrong project approval
- **WHEN** a user tries to approve a code bound to another project context
- **THEN** the server rejects approval and preserves the pending authorization

#### Scenario: Successful approval and poll
- **WHEN** the consenting user approves a live code and the CLI next polls
- **THEN** the server atomically consumes the code and issues one access/refresh credential pair for that user/project

### Requirement: Credentials expire, rotate, and revoke
Gateway access credentials SHALL be short lived. Refresh credentials SHALL be longer lived, stored only as hashes, rotated on every successful refresh, and invalid after consent revocation, explicit credential revocation, terms-version change, or refresh expiry.

#### Scenario: Refresh rotation
- **WHEN** a client refreshes a valid credential
- **THEN** the server returns a new access/refresh pair and replay of the old refresh token fails

#### Scenario: Revoked authorization
- **WHEN** consent or a credential is revoked
- **THEN** subsequent compatibility authentication fails immediately even if the access token timestamp has not expired

### Requirement: Local credential storage is restrictive
The CLI SHALL write credentials atomically to the user configuration directory and SHALL apply owner-only file permissions on POSIX systems. It SHALL NOT log device codes, access tokens, or refresh tokens after the interactive flow.

#### Scenario: Credential file creation
- **WHEN** login succeeds on a POSIX host
- **THEN** the resulting credential file is mode `0600` and contains only the configured origin and current issued credentials
