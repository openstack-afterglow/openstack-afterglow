# Dedicated automatic-backup system account

## Why

Scheduled Cinder recovery points require a genuinely target-project-scoped token: Cinder assigns ownership and quotas from that token. The fixed Afterglow operator has no tenant role and must not gain broad tenant privileges. Backup capacity must consistently equal three times the global volume capacity quota.

## What Changes

Create one system-owned `afterglow-auto-backup` user in the configured operator user domain. Grant only stock `member`, and only while a backup/snapshot policy record (including paused policies) or active operation journal needs it. Keep all other operator connection callers and Trove unchanged. Protect this principal throughout Afterglow identity, credentials, login and member APIs; label it in all user interfaces. Derive global `backup_gigabytes = 3 * gigabytes`, preserving unlimited `-1`, typed quotas and backup count.

## Impact and acceptance

Activation is opt-in and separate from deployment. Read-only reports enumerate intended native writes without generating passwords or changing Redis/native state. Local fake/provider, API, unit, browser and isolated canonical-gate evidence must precede a branch-only commit. No production writes, push, tag, merge or deployment occur in this change.
