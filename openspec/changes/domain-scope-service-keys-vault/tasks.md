## 1. Provider → model selection

- [x] Shared `ProviderModelSelect` in chat, regeneration, agents and all Studios; exact row identity and `chat:lastModelId` with unique-only legacy migration.
- [x] Requests send `model_row_id`; BFF forwards and validates where it parses bodies.

## 2. Installer URL

- [x] Startup-rendered `/install/lumen.sh` and `/install/lumen.ps1` from `lumen_external_url`; no URL arguments; failing script and hidden UI when unconfigured; Compose/K8s/Helm/Kolla wiring.

## 3. Domain-wide history and tools

- [x] Domain-keyed view lifetime for chat history, agents, memory and connections; selected project still used for runs, usage and cloud tools.
- [x] Archived duplicate connection/tool list and restore (organization items gated by Lumen manager authority).

## 4. Keys, service keys and domain credit pool

- [ ] Personal keys without project selector; service keys for domain managers; domain pool card (balance, reserved, monthly used, manager limit, admin ceiling).
- [ ] System-admin pool top-up/ceiling and service-key inventory pages; BFF routes with pytest.

## 5. Vault memory

- [ ] Vault UI in chat settings (kinds, search, revisions, hash-guarded edits, append-only kinds, secret refusal, memory.md) with domain-keyed lifetime; BFF routes with pytest.

## 6. Integration and verification

- [ ] Lumen 0.6.21 integrated (scope, billing, keys, models, vault) with schema snapshot, reviews and gate; agent-vault SQL backends reviewed.
- [ ] Afterglow experience catalog regenerated, ARCHITECTURE stamped, isolated `npm run test:gate`, browser proof.
- [ ] Owner-approved domain pool opening top-ups, Lumen then Afterglow rollout, production verification.
