## Why

Administrators currently configure SMTP only in files, cannot verify SMTP/IMAP or test delivery from the web, and cannot send individual, announcement or notification mail through a managed UI. The user explicitly requests all these web capabilities alongside SSO password recovery.

## What Changes

- Add system-administrator web management of SMTP and IMAP settings, preserving file defaults and storing runtime overrides with encrypted secrets, masked reads and revision-fenced writes.
- Add saved-setting SMTP/IMAP connection checks and explicit test mail; distinguish SMTP acceptance from read-only IMAP Message-ID receipt confirmation.
- Add registered-user individual mail, announcement email delivery respecting existing audience and scheduling, and configurable email delivery of existing safe notification events with user preferences.
- Persist outgoing intent and dispatch state, protect against duplicate submissions, expose truthful pending/accepted/failed/unknown results and never automatically replay uncertain SMTP sends.
- Apply effective SMTP settings to existing recovery, signup/invitation and administrator-password mail/readiness, not only the new composer.

## Capabilities

### New Capabilities

- `web-email-administration`: Secure runtime mail settings, web diagnostics/test receipt, user/announcement/notification delivery and visible outcomes.

### Modified Capabilities

None.

## Impact

Existing administrator settings/user/announcement/account UI, mail and event services, persistent settings/outgoing delivery/preferences, API/worker role wiring, config examples and both Kubernetes producers where settings are generated. Use existing encryption/master key and authentication. Add only necessary additive migration(s); no production DB/schema/service, real mailbox, provider, publication or deployment changes without separate approval. Preserve unrelated Pi/chat/frontend work and index; the earlier SSO gate's unrelated proxy-format failure remains recorded, not silently repaired.
