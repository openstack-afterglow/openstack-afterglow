# Lumen built-in MCP invalid credential visibility

## Why

A stored Lumen MCP grant can remain enabled after Keystone rejects its application credential. Tool execution preserves its generic failure contract, but the dashboard currently presents the connection as active and gives no recovery guidance.

## What changes

- Distinguish application-credential authentication HTTP 401/404, including missing-role 404, from transport, server and service-resource failures.
- During real Lumen execution, record a bounded structured warning and a best-effort seven-day Redis observation keyed by grant ID.
- Project that observation as `credential_state: invalid|ok` from the existing cloud-tools catalogue without probing Keystone or changing enabled authority.
- Show a warning pill and localized disable-then-enable guidance in the built-in MCP row. Recovery remains an explicit action through the user's session.

## Scope and constraints

No DB migration, new native authority, automatic revoke/reissue, execute status/body change, Lumen repository change, release or deployment. Source/local tests only. Work remains in `feat/dead-grant-ux` when shared dirty documentation prevents safe integration.
