## 1. Cross-service API contract
- [x] Add Lumen embedding model kind, OpenAI/Gemini-compatible APIs, native session route, and metering contract.
- [x] Add authenticated no-store Afterglow BFF mapping for `/api/v1/chat/embeddings`.

## 2. Dashboard
- [x] Add typed embedding client, readiness gates, response validation, vector calculations and cancellation.
- [x] Add responsive Embedding Studio, dashboard route and navigation entry.
- [x] Add translations for all nine locales and component/API tests.
## 3. Administrator model registry
- [x] Add embedding to model-kind filters and registration/review flows.
- [x] Show input-token pricing only; do not request output pricing, cache-write pricing, or media reservations.
- [x] Update design, API and architecture documentation.
## 4. Verification and integration
- [x] Run focused Lumen model, provider, API, billing and SDK compatibility tests.
- [x] Run focused Afterglow BFF/UI tests and i18n checks; inspect rendered desktop/mobile UI.
- [x] Run Lumen architecture stamp/guard and Afterglow architecture stamp/guard.
- [x] Run each repository's required canonical gate and record exact results/limits.
- [ ] Integrate worktrees into their `dev` checkouts only when conflict/dirty-path safety permits; archive changes after evidence is complete.
