## Implementation Tasks

- [x] Record sanitized, bounded client observations only for authenticated successful MCP initialization, with deterministic clientInfo/User-Agent inference and current-grant/epoch revalidation.
- [x] Add nullable grant JSON storage and idempotent additive migration 087/manifest, preserving existing grants and limiting retained observations to ten.
- [x] Expose observations through owner/project-scoped OAuth/PAT list response models with no-store, without credential/internal signature leakage.
- [x] Render all observed identities, versions and first/last confirmation times with inferred/not-online disclosure and unknown handling in all four locales.
- [x] Make client removal explicitly revoke the entire OAuth grant/API key, preserving existing authoritative invalidation, cleanup, audit and stale confirmation fences.
- [x] Keep OAuth/PAT load errors independent, show failed counts as unknown rather than zero, and preserve issuance/project-authority failure guards.
- [x] Add meaningful identity/storage/transport/API/revocation regressions and exercise native local MCP connect/list/revoke plus compiled responsive/theme/locale surfaces.
