## Why

Public login exposes an internal identity-domain implementation detail. The requested user contract is verified-email signup with unique identifiers and automatic OIDC association to an existing Accounts human using the provider-verified email, including production deployment paths.

## What Changes

- Remove the login identifier domain/help paragraph and retired translation keys in all nine locales.
- Enforce and qualify delivered, one-use email proof before public account creation; reject duplicate normalized username/email including concurrent attempts without resetting an existing account.
- Automatically associate a freshly verified OIDC identity with one enabled exact Accounts email owner under the identity graph lease; retain stable issuer/subject and native canonical-token readback. No password, UUID, home, grant or resource migration.
- Keep ambiguous Accounts matches and externally owned native bindings fail-closed. Legacy non-Accounts canonical identities retain their explicit ownership-proof path; no automatic native tuple takeover.
- Synchronize source defaults, deployment guidance and configuration-generation paths so association is not a local-only flag. SMTP remains required for email signup and no bypass is introduced.

## Capabilities

### New Capabilities
- `verified-account-entry`: Domain-free login copy, verified-email unique signup and automatic verified OIDC Accounts association with preserved canonical identity.

### Modified Capabilities

None; existing personal provisioning, organization admission and native-service authority requirements remain in force.

## Impact

Frontend LoginPage and nine locale catalogs; public enrollment and canonical federation services/tests; auth/security/deployment documentation and OpenSpec. No operational deployment, account migration, native credential/grant changes or datastore mutation is authorized. Reuse existing SQL journals and schema where possible.
