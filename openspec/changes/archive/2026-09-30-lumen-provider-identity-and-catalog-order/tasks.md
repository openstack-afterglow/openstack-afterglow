## Implementation Tasks

- [x] Map Lumen persistence/resolution/catalog and Afterglow consumer boundaries; preserve unrelated release/logging/CLI/cloud-shell work.
- [x] Support editing provider display names, including NVIDIA NIM to NVIDIA, without changing IDs, credentials or connection configuration.
- [x] Persist and edit `api_provider` independently from `provider_type`; migrate existing selectors and resolve public API requests using the new selector.
- [x] Filter registered models by provider independently from model discovery/creation, with filter-safe selection/deletion.
- [x] Persist administrator-controlled provider `sort_order` and apply it to picker navigation and groups.
- [x] Persist administrator-controlled model `sort_order` and apply it within each picker group without changing model selection identity.
- [x] Verify provider updates, selector routing, real migration/persistence and responsive UI behavior; run affected checks and report unexecuted boundaries.

## Verification evidence and boundaries

- Actual Vite admin and user chat surfaces exercised through the real authenticated Afterglow BFF and Lumen HTTP service with isolated MariaDB/Redis; only external identity authority and compatible-provider inference endpoints were synthetic.
- Persisted NVIDIA rename and independent `nvidia` selector retained `provider_type=openai`, base, ID and configured credential. Shared public model requests returned `OPENAI_ROUTE` and `NVIDIA_ROUTE` from their distinct loopback endpoints. Header/body conflict returned 400, member mutation and missing usage scope 403, invalid metadata 422 without changing stored values.
- Actual browser saved provider/model ranks, reloaded catalog order, filtered registered rows, cleared hidden bulk selection and deleted only a visible NVIDIA probe while preserving the hidden OpenAI probe. Picker filter survived display/selector rename and the current model remained selected after order changes.
- Provider metadata modal verified at 390, 767, 768, 1023, 1024 and 1440px in light/dark; registered list at 390, 768, 1024 and 1440px in light/dark; actual picker at all six widths. Screenshots and DOM checks found no horizontal overflow and retained actions.
- Focused admin/picker Vitest: 51 passed. `npm run check` returned zero errors/warnings and production build succeeded. `npm run test:lumen`: 41 backend and 134 frontend passed.
- `npm run test:gate` test layers passed: 3,307 backend unit, 1,706 frontend Vitest, 136 contract and 28 real datastore functional tests. The gate itself exited 1 only on existing formatting differences in `backend/app/main.py`, `backend/app/services/layer_build.py` and `backend/tests/test_logging_contract.py`; unrelated user edits were not reformatted.
- Lumen service contracts: 1,498 passed; SDK: 125 passed; real MariaDB legacy-migration regression: text/image cases both passed. A failing-before ORM/HTTP probe caught rank updates changing legacy manual pricing `updated_at`; the fix preserves the pricing clock and frozen execution hash for rank-only writes.
- Lumen implementation is isolated at `/Users/pieroot/code/lumen-provider-identity` (`feature/provider-identity-catalog-order`), based on current 0.4.0 source; the user's dirty release checkout is unchanged. Migration 021 requires coordinated Lumen API/worker rollout before the new frontend contract.
- No commit, push, image publication, production schema change/deployment, real NVIDIA account inference or live OpenStack verification performed.
