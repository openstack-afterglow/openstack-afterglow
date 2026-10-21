# operator-shared-domains Specification

## Purpose
TBD - created by archiving change bind-operator-accounts-personal. Update Purpose after archive.
## Requirements
### Requirement: Resolve operator-owned shared domains
Enrollment MUST place new identities in the enabled native Accounts domain and personal projects in the enabled native Personal domain. It MUST NOT use display labels to resolve them or automatically create shared domains. Missing kind metadata MUST be allowed; explicit conflicting kinds MUST be rejected. Existing historical bindings MUST NOT be rewritten.

#### Scenario: Operator domains have no Afterglow metadata
- **WHEN** enabled native Accounts and Personal exist without Afterglow metadata
- **THEN** enrollment reuses their exact UUIDs without creating or mutating domains

#### Scenario: Native domain unavailable or ambiguous
- **WHEN** a required native domain is absent, disabled, has a conflicting kind, or its name has ambiguous case variants
- **THEN** enrollment fails before creating a user or personal project

#### Scenario: Web organization display names collide
- **WHEN** users create organizations with equal display names
- **THEN** their opaque native names and UUID boundaries remain separate and neither is adopted as a shared domain

### Requirement: Password login uses Accounts only
The public password login MUST resolve username/email within native Accounts only and MUST authenticate once with its exact UUID. It MUST NOT fall back to another domain or allow the client to override the identity domain. Explicit account-link proof MUST retain its existing canonical-home boundary.

#### Scenario: An organization contains the same username
- **WHEN** Accounts and another domain contain matching login aliases
- **THEN** only the Accounts user is selected for the native credential proof

#### Scenario: User exists only outside Accounts
- **WHEN** the submitted username/email exists only in another native domain
- **THEN** public password login is denied without a native credential attempt

