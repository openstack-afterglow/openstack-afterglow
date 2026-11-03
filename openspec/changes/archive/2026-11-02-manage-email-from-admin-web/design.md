## Context

SMTP exists only in config and direct email_service; recovery/signup/admin password readiness reads it separately. There is no IMAP management or managed individual/announcement/notification email workflow. Existing RuntimeSetting, AEAD master key, announcements audience/scheduling, ActivityLog, profile identity and shared dispatcher provide the boring integration points. Source work must preserve unrelated concurrent Pi/chat edits.

## Goals / Non-Goals

**Goals:** All requested web workflows, encrypted runtime configuration and outgoing intent, canonical recipient/audience authorization, truthful test/send/receipt outcomes and existing recovery integration.

**Non-Goals:** No webmail reader, arbitrary mail relay for ordinary users, plaintext secrets or IdP password reset, automatic replay of unknown SMTP sends, real mail/production changes, publication or deployment.

## Decisions

- Preserve file defaults; private revisioned RuntimeSetting stores overrides and purpose-bound encrypted secrets. Mask reads; omitted secrets preserve, explicit clear removes. Settings reset retains revision tombstone. Configured DB outage fails closed. Existing mail/readiness consumers resolve the same effective settings.
- Interpret iamp as IMAP. Secure SMTP STARTTLS/implicit TLS and IMAP SSL/STARTTLS use certificate validation and bounded operations. Saved-settings checks are explicit. Test messages have stable Message-ID; IMAP performs read-only exact header search without bodies/seen flags. SMTP acceptance never means inbox receipt.
- Admin direct messages target immutable user IDs and server-resolved registered addresses. Announcement mail preserves all/project/user targeting, active/scheduled bounds and current membership. User notification preferences and global gates control automatic safe resource-failure alerts; new delivery runs as a shared dispatcher role, never a GET side effect. No historical error-mail blast.
- Durable additive delivery/preferences schema records operation dedup, exact recipient binding and encrypted payload. SQL CAS consumes pending state before SMTP. Failures and unknown/crashed dispatch stay visible and are never automatically resent. Current recipient/visibility is rechecked before delivery; no resource/native writes.
- Use existing settings/user/announcement/account surfaces and nine locales. Clear in-memory secret drafts on dispatch/scope/unmount, preserve owner/ABA fences, show partial outcomes and saved-setting semantics. Parent owns router/worker integration and final smoke proof.

## Risks / Trade-offs

- Mailbox credentials and outbound endpoint trust belong to fresh system administrators; secrets remain bound and encrypted and changing destination must not silently reuse an old credential.
- SMTP cannot guarantee exactly-once delivery or inbox placement; uncertain DATA completion is unknown, not safe retry. Read-only IMAP receipt only proves the configured mailbox's exact test-message observation.
- New additive schema requires schema-before-writer and coordinated API/worker qualification; source tests do not apply migrations to shared/production databases.
- Automatic alerts initially mean the existing safe resource-failure events and supported reminder producers, with explicit policy/preferences, not unrestricted copies of arbitrary logs.
