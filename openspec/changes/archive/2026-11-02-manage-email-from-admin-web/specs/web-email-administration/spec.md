## ADDED Requirements

### Requirement: Administrators manage effective SMTP and IMAP settings on the web

The system SHALL expose fresh system-admin-only SMTP/IMAP forms with explicit revision-fenced save/reset, config defaults, encrypted purpose-bound secrets and masked reads. Runtime settings SHALL affect existing recovery/signup/invitation/admin password mail and readiness, not only new messages. Configured storage failures SHALL NOT silently bypass overrides. Secret validation/logging SHALL not expose credentials.

#### Scenario: Save and preserve existing credentials
- **WHEN** an administrator changes non-secret settings or explicitly sets/clears a password
- **THEN** omitted passwords are retained safely, secrets are encrypted and never returned, stale revisions conflict and reset restores file values without revision ABA

#### Scenario: Readiness follows the web override
- **WHEN** SMTP is enabled or disabled through the web
- **THEN** all mail consumers and recovery/signup capability/readiness use the effective saved settings

### Requirement: Web diagnostics distinguish connectivity, acceptance and receipt

The system SHALL provide bounded SMTP/IMAP saved-configuration connection checks, explicit test-email submission and read-only IMAP Message-ID receipt verification. SMTP acceptance SHALL not be displayed as inbox delivery. Ordinary users SHALL not obtain mail-server probe or test-relay authority.

#### Scenario: Test mail is accepted and then observed
- **WHEN** a saved SMTP configuration accepts a test message and the configured IMAP mailbox contains its exact Message-ID
- **THEN** the web shows SMTP acceptance separately from confirmed receipt without reading mail bodies or marking messages seen

#### Scenario: Mail transport or recipient fails
- **WHEN** connection/authentication/recipient/DATA or IMAP verification fails or times out
- **THEN** sanitized failed/pending/unknown states are shown without leaking secrets or automatically replaying an uncertain send

### Requirement: Administrators send individual and announcement mail to authorized registered recipients

The system SHALL allow explicit individual-user mail and announcement mail through the web. Individual recipients SHALL be resolved from native IDs to current canonical registered addresses. Announcement mail SHALL preserve existing all/project/user audience, active status and scheduling and SHALL revalidate current membership. Durable operation identifiers SHALL prevent duplicate submissions and conflicting payload reuse.

#### Scenario: Individual registered-user message
- **WHEN** an authorized administrator submits a subject/body for a selected enabled human
- **THEN** a durable single-dispatch message targets only that user's verified canonical address and status is visible on the web

#### Scenario: Scheduled targeted announcement
- **WHEN** announcement email is explicitly requested
- **THEN** its outgoing intent is durable and eligible current recipients receive it only during the active schedule, without a silently truncated recipient set or cross-project disclosure

### Requirement: Existing user notifications can be delivered by email

The system SHALL provide global notification-mail settings and per-user preferences and SHALL deliver supported current safe notification events through the shared background runtime. It SHALL not send mail as a side effect of read-only dashboard GETs, blast historical logs, include arbitrary secret-bearing error prose or mail users whose scope was revoked.

#### Scenario: Opted-in resource notification
- **WHEN** a new supported resource-failure/reminder event occurs with global and recipient preferences enabled
- **THEN** the existing authorized audience receives one durable email notification with only safe event fields

#### Scenario: Delivery restarts or authority changes
- **WHEN** a process restarts after dispatch or a recipient's identity/email/project visibility changes
- **THEN** uncertain sends are not replayed and ineligible queued messages are cancelled rather than leaking content
