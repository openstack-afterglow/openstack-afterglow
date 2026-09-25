# Fix GitHub SSH history schema on Kolla reconfigure

## Problem

On 2026-09-25, `POST /api/v1/instances/github-users/lookup` returned 503 while the GitHub profile and public-key resolution succeeded. The backend failed closed at `_upsert_history`: its production MariaDB schema lacked `vm_github_ssh_users` (error 1146). Production sets `auto_create_tables=false`. Kolla deploy runs `bootstrap_service.yml`, but reconfigure and upgrade pull/start a backend image without running it.

## Change

- Apply the existing checksum-pinned `080_vm_github_ssh_users.sql` to the production Afterglow database without changing user data; verify columns and an isolated resolver/history write, then remove that temporary history record.
- Include the existing idempotent `bootstrap_service.yml` after configuration and before backend start/policy seeding during Kolla reconfigure; include it after image pull and before start/policy seeding during upgrade. Do not change the API, error mapping, or the fail-closed SSH admission rule.
- Document the ordering and the boundary: `create_tables` creates missing tables; schema alterations to existing tables still need reviewed SQL migrations before rollout.

## Constraints

- Work on dev, preserve concurrent instance-resize edits and production volumes.
- No rollback/destructive schema action, no secrets in logs, no unreviewed image tags, and no production application deployment before owner-reviewed main merge.
- Review checksum and actual DB schema before/after the one-table migration; inspect controller health and exercise the failing persistence boundary.

## Completion

- Production `vm_github_ssh_users` exists with the expected columns, GitHub resolver+history succeeds, and the temporary smoke row is removed.
- Kolla reconfigure and upgrade tasks run bootstrap before a new backend process can accept requests; focused Kolla contracts, architecture guard, and project gate pass.
- Owner reviews and merges source fix; tagged production role rollout, backend health, and authenticated lookup are verified separately before archiving this change.
