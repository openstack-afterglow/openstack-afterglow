## Context

Afterglow authenticates browser sessions and forwards them to the separately deployed Lumen service. Local Compose must give every Lumen process the same Keystone authority configuration, while the BFF must distinguish the token's connection project from an administrator-selected logical target project.

## Goals / Non-Goals

**Goals:**

- Make local Lumen authentication configuration explicit and fail closed.
- Keep migrate, API, and worker settings identical.
- Preserve trusted connection and target project scopes through the BFF.
- Verify the documented Compose invocation against running containers.

**Non-Goals:**

- Moving authentication ownership from Lumen to Afterglow.
- Forwarding browser-supplied target-project headers.
- Adding localhost or development authentication fallbacks.

## Decisions

1. Each Lumen service loads `.env` and receives explicit `KEYSTONE_*` mappings. `LUMEN_KEYSTONE_*` wins; existing `OS_*` values remain the compatibility fallback. This avoids divergent configuration among migrate, API, and worker.
2. Operators invoke Compose with `.env` followed by `docker-compose.services.env`, so separated-service image and endpoint overrides have deterministic precedence.
3. Afterglow generates `X-Project-Id` from the verified token connection scope and emits `X-Target-Project-Id` only for an authorized delegated target. Browser-provided target headers are never forwarded.
4. Missing authority configuration remains an authentication failure. No localhost default is introduced.

## Risks / Trade-offs

- **Operator invocation drift** → Keep the exact dual env-file command in the Compose file and enforce it in contract tests.
- **Partial service configuration** → Assert identical mappings for migrate, API, and worker.
- **Delegation confusion** → Keep connection and logical target scopes in separate headers and regression tests.
