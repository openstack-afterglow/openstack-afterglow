## Implementation Tasks

- [x] Add validated auth provider registry and common/canonical-domain selectors to Settings and TOML loading; preserve environment precedence and reject unknown provider references.
- [x] Preserve auth structure in K8s/Helm runtime TOML and inject client secrets exclusively through nested Secret environment variables consumed by API and worker.
- [x] Merge file-selected and SQL login providers in domain resolution, and enforce exact domain membership and configuration revision through authorize/callback/refresh.
- [x] Add consumer regression coverage for selection/isolation, secret redaction/deployment round-trip and provider state/session invalidation.
- [x] Run focused auth/config checks and actual HTTP plus responsive browser smoke with explicit synthetic boundaries. Focused backend/config 281 passed; frontend 44 passed; real HTTP/Kustomize/Helm and compiled four-locale browser passed. Broader auth/config fixture failures are recorded in docs/testing.md, not hidden.
- [x] Update example configuration, authentication documentation, architecture and changelog; record evidence and archive the change. docs/testing.md records scoped passing evidence, broader fixture failures, absent live/rollout acceptance, isolated working/staged architecture receipt, and owned-resource cleanup.
