## Why

The public cloud MCP is working, but Lumen's cloud bindings require a manually selected personal key. External grants are fixed to one issuance project and OAuth displays only the client's requested access. Users need built-in authenticated resource tools and explicit least-privilege access/project consent.

## What Changes

- Make cloud resource inspection and monitoring available as built-in Lumen tools using each authenticated user's current project, without a shared user secret or manually created key.
- Let personal tokens and OAuth approvals select read/manage access and all currently accessible projects or an explicit subset.
- Persist exact delegated per-project credentials and enforce project selection and scope on every dispatch. Existing grants retain their single project; all-project selection is a frozen issuance snapshot, not a grant to future projects.
- Preserve PKCE, exact resource audience, one-time codes, refresh attenuation, revocation, per-call mutation approval and idempotency.

## Capabilities

### New Capabilities
- `lumen-cloud-tools`: Built-in, user/project-bound cloud inspection through the existing MCP registry and bridge.
- `mcp-project-consent`: Personal and OAuth access-level/project selection with server-enforced delegation.

### Modified Capabilities

None; this change adds explicit selection to the existing MCP control plane.

## Impact

Afterglow MCP models/additive migration, credential issuance/authentication/dispatch, browser management and OAuth consent, authenticated Lumen BFF and existing tool menu. Reuse the installed Lumen Afterglow MCP bridge/plugin; no sibling implementation import, production IAM mutation or deployment.
