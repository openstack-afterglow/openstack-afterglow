## Diagnosis

- [x] Trace the reported local migration failure to the exact historical media migration ledger identity and current canonical checksum.
- [x] Trace missing image/audio navigation to the actual Sidebar while confirming the existing Studio routes and palette entries.

## Implementation

- [x] Safely adopt the exact historical media migration without rerunning DDL or changing immutable SQL/history; cover migration boundaries with isolated regressions.
- [x] Expose image/audio Studio in the actual sidebar and preserve service visibility and unambiguous active-route behavior.

## Verification

- [x] Build affected images on supported architectures, resume the canonical local stack without data deletion, and exercise migration/readiness and native media catalogs.
- [x] Observe actual image/audio Studio navigation and page controls across mobile/tablet/desktop cutovers; run relevant checks and record limits.
- [x] Update affected architecture and detailed docs with evidence, preserve unrelated work and archive this repair.

## Verification evidence and limits

- Root build contract remains `docker-compose.dev.yml` with Lumen context `../lumen`; the runner fix and isolated MariaDB regression live in that canonical sibling checkout, not the provider-identity worktree. Immutable migration SQL/manifest were not changed.
- Nine isolated real-MariaDB media-history regressions and 13 migration runner/manifest contracts passed. The initial JSON-drift fixture attempted to drop the MariaDB auto-JSON check by name and failed; replacing the JSON column with nullable plain LONGTEXT produces the intended schema corruption and all nine scenarios pass. Focused Ruff checks passed.
- Sidebar/AdminSidebar: 12 tests passed. `npm run test:lumen`: backend 41 and frontend 142 passed. `npm run check`: 2,115 files, zero errors/warnings. Production frontend, Lumen API and worker built on linux/arm64 and linux/amd64.
- Existing `afterglow-local-services` data and encryption/config mounts were retained. `lumen-migrate` exited 0, a second one-shot migrate run exited 0, and dry-run returned `pending=[]`, `unready_histories=0`. The original `019-media-model-registry` row (2026-09-28) remains with exact SHA-256; canonical `020-media-model-registry` was added with the same hash. Lumen `/v1/ready` reports database/plugins/checkpointer true; Lumen API, Afterglow backend and frontend report healthy.
- A throwaway process inside the actual Lumen API image exercised native image/tts/stt catalogs against the real migrated local DB with only `models:read` principal overridden; all return HTTP 200 and empty arrays, while unauthenticated catalog returns 401. The DB has zero providers/models/conversations/messages/API keys. No credentials or paid provider requests were added.
- Actual production frontend Chromium smoke used a synthetic browser identity and intercepted empty catalog reads with all mutations blocked. At 390/767/768/1023/1024/1440px, real sidebar links reach both Studio pages, only the matching item is active, mobile drawer closes, image edit exposes the file input, TTS/STT forms remain present and page-level horizontal overflow is absent. Screenshots were observed. This is UI proof, not real OpenStack login or media inference proof.
- Full working-tree architecture checks in both repositories remain stale because pre-existing unrelated source changes are present. Only this repair's reviewed files are included in a temporary-index architecture stamp/check; the user's actual index is not changed. Full `npm run test:gate`/live OpenStack and paid provider acceptance are not claimed. Optional gbrain sync is unavailable (`gbrain` CLI and its detector are not installed).
