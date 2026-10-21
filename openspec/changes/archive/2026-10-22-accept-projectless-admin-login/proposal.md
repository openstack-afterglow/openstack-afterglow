# Accept projectless administrator login

## Why
Latest local-stack live logs show native password authentication and session publication returning 200, immediately followed by frontend session discard/logout. The Accounts operator has no personal project; the existing backend selects a visible non-account domain with no project for verified administrators. loginAuthState incorrectly rejects every foreign non-personal initial domain.

## Change
Accept a fresh server-reported system administrator's projectless context only when the selected working domain appears in available_domains. Preserve immutable identity, complete metadata, ordinary personal-only landing, and foreign project rejection. No backend/native authorization, IAM, schema, deployment or runtime changes.

## Acceptance
Regression fails before and passes after; both password and federated mappings accept visible projectless administrator contexts, reject non-admin/invisible/project-scoped foreign contexts, and reach the workspace chooser through the actual login UI with synthetic API responses. Existing auth/session tests remain green.
