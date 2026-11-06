## Why
MCP lists currently filter by the selected issuance project, hiding a user's existing connections when navigating to another project/domain. Account settings should expose the user's own connection inventory without expanding delegated cloud authority.

## What Changes
- List personal API keys and OAuth grants by exact authenticated user across issuance projects/domains.
- Preserve and show saved issuance-project origin and immutable approved projects.
- Resolve original stored ownership for revocation rather than trusting the current workspace.
- Separate account-list availability from project-scoped issuance and permission preview.
- Preserve single-working-domain, multiple-project OAuth consent and current execution checks.

## Capabilities
### New Capabilities
- `account-mcp-inventory`: Account-owned connection inventory and origin-safe revocation independent of selected workspace.
### Modified Capabilities
None; existing OAuth domain/runtime restrictions remain unchanged.

## Impact
Backend identity MCP routes/authority projections, frontend account MCP scope/route handling, behavioral regressions and user/API/security documentation. No schema migration, credential reissuance, native permission expansion or production rollout.
