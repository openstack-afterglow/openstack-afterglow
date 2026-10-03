## Implementation Tasks

- [x] Verify supplied/generated references, existing UI/API contracts and shared implementation boundaries.
- [x] Recompose image generation/editing around a central prompt composer, functional style thumbnails and real owned results.
  - Option row (readable select minimum, at most three per row below `lg`) precedes the attach/mode/submit action row; style text is appended to the submitted prompt and included in the idempotency fingerprint.
- [x] Recompose TTS around a text editor and actual model/voice/format settings with working playback/download.
  - Browser exposed a real defect: CSP had no `media-src`, so object-URL audio failed (`MediaError` 4). Fixed with `media-src 'self' blob:`; regression in `frontend/src/hooks.server.test.ts` failed before and passed after.
- [x] Extend native Lumen STT capabilities/admission/provider/durable result with real segment timing and fail-closed unsupported or invalid requests.
- [x] Add STT upload/source preview, timed transcript display, TXT/SRT download and scope cleanup.
- [x] Exercise image generation/edit, TTS playback/download and STT timed display/download through the actual browser, across theme/responsive boundaries; run affected tests/check/build.
  - Real headless Chromium against the rebuilt local Compose frontend with a synthetic identity and route fixtures (catch-all blocks unmocked API, external HTTPS blocked); binary media served by in-run request interception. Submitted bodies, Blob decode, download bytes (SHA-256), CSP header, 390/767/768/1023/1024/1280/1440px overflow and dark/light were observed.
  - Afterglow: ImageStudio 11, AudioStudio 11, transcript parser 18, hooks 24; Svelte check 0/0; `test:all` passed (backend 3,307, frontend 1,745, contract 136, functional 28, JS 102/26/13+15 skipped, scripts 9); `ruff check` passed; `ruff format --check` fails only on pre-existing `backend/app/main.py`, `backend/app/services/layer_build.py`, `backend/tests/test_logging_contract.py`.
  - Lumen: transport/compat 63, MariaDB durable audio integration 9, Ruff passed; contract layer 1,613 passed and 2 failed in `tests/test_chat_worker.py`/`tests/test_request_logging.py`, files modified by unrelated in-progress work.
  - Images: API/worker/frontend arm64 rebuilt and redeployed into the existing stack without dependency or volume changes (config hashes unchanged, migration exit 0, ready OK, changed source and style assets SHA-256 match); amd64 images built and executed under emulation.
- [x] Update affected detailed docs and repair-scoped architecture reviews without staging unrelated work, record evidence limits and archive.
  - Afterglow: ARCHITECTURE status/code map, DESIGN Media Studios (stale two-card audio paragraph removed), `docs/api/chat.md`, `docs/security.md`, CHANGELOG. Scoped temporary-index stamp of HEAD plus this change's 17 source/test/asset files passed `--staged`; real index untouched.
  - Lumen: ARCHITECTURE/API reference/CHANGELOG already describe the timing contract. Its guard was not stamped: the timing hunks in `durable_runs/audio.py`, `audio_transport.py` and `run_store.py` are interleaved with uncommitted multimodal usage-settlement work, so any snapshot would certify unrelated changes. The owner must review and stamp the combined Lumen change before commit.
  - Not verified: provider-real inference/pricing/scanner, authenticated OpenStack login, production deployment. No commit or push.
