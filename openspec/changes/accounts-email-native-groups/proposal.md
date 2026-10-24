## Why
Afterglow requires a separate subject-only native mapping and refuses existing Accounts users selected by verified email with organization group rules.

## What Changes
Accept a local Accounts username/email mapping and conditional existing groups in the selected organization for operator-managed OIDC providers. Keep canonical ID/home/email readback, issuer/subject association ownership and all password/link/admission protections. Native Keystone synchronizes signed group claims onto the same Accounts identity. No app schema or data backfill is introduced.

## Scope
Remove the stable-sub-only requirement for this deployment. Preserve other providers, local passwords, Personal provisioning and manual memberships. Do not deploy unrelated pending SQL102 source without qualification.

## Current status
The production goal is complete through the separately qualified 1.30.24 operator policy in `../afterglow-email-groups-runtime-20261024`. This checkout is an optional upstream port on fetched dev `6d57ab65`; its 267 auth tests passed. Its additional SQL102/source is not deployed, and no commit/push/upstream release is requested or performed. Further upstream integration has its own full-gate/release work and is outside the completed site configuration change.
