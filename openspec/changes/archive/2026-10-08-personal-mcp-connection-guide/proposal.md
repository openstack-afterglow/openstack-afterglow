## Why

Afterglow already issues user/project-bound MCP personal tokens and serves a fail-closed Streamable HTTP transport, but the account UI exposes only the raw token and no client configuration or authenticated connection check. Public user documentation does not explain this inbound connector. An explicitly configured MCP origin is currently rewritten to `/api/v1/mcp`, preventing the requested root-resource configuration.

## What Changes

- Reuse existing personal-token issuance, expiry, owner isolation and revocation; no shared/admin credentials or second credential store.
- Treat an explicit `mcp.public_url` as the exact resource, including a bare origin served at `/`; retain `/api/v1/mcp` only when no public MCP URL is set. Keep backend/frontend/deployment derivation consistent.
- Add a same-site browser-only `POST /api/v1/auth/mcp-tokens/verify` with `{token}`. Verify the personal token belongs to the authenticated user/current project before making bounded, TLS-verified, no-redirect HTTP calls to the operator-configured MCP resource. Prove `initialize`, initialized notification and `tools/list`; never execute mutation tools. Return endpoint, negotiated protocol, server name/version and tool count, never credentials or upstream raw errors.
- In the existing account section, show a placeholder HTTP `mcpServers` configuration, docs link, and a password-input verification flow for saved tokens. In the one-time issuance dialog, offer JSON with the actual Bearer credential, separate token/config copy actions and connection verification. Clear secrets/config/results on dismissal, project/auth changes and unmount; fence late responses by owner and secret identity.
- Add `/docs/mcp` through the existing typed, localized public documentation catalog. Explain inbound access versus Lumen outbound server registration, personal key creation, header-auth connector formats, OAuth-only clients, verification, expiry/revocation and safe troubleshooting.

## Capabilities

### New Capabilities

Personal MCP connector setup and an authenticated read-only connectivity check, plus a public user guide accessible from the dashboard.

### Modified Capabilities

Exact configured MCP resource derivation supports origin-root endpoints. Default `/api/v1/mcp`, personal-token ownership, grant permissions, OAuth and Lumen delegation remain authoritative.

## Impact

Backend MCP authority/connection verification, public URL derivation and its consumer configuration paths; frontend account UI and four account message catalogs; existing public docs catalog and four document languages; relevant security/protocol regression tests, architecture and changelog. No production enablement, deployment, live-user credential creation, role changes or cloud mutation. The shared dev checkout has pre-existing edits and unresolved merges; preserve them and report integration limits. An anonymous public probe of `https://mcp.cloud.dmslab.re.kr` on 2026-10-08 failed DNS resolution, so local proof must not be presented as production connectivity.
