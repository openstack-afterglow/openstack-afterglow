## Implementation Tasks

- [x] Inspect Glance hash projection, duplicate image screenshot, existing catalog and VM picker; fix current/latest and saving-image contract.
- [x] Resolve each repository/tag against unfiltered uploads by full Glance creation instant, preserve distinct UUID versions, and enable SHA-512/UUID search.
- [x] Present current tag and hash/UUID-distinguished previous uploads on user and admin surfaces without losing scoped management actions; keep VM boot selection unambiguous.
- [x] Add behavior regressions for duplicate tags, matching hashes, saving/no hash, fractional timestamp and filter boundaries; update API, architecture, design and changelog.
- [x] Run focused selectors and full gate; perform staged architecture check, both target architecture builds for frontend/backend/worker and local deployed browser/API smoke on duplicate uploads.
- [x] Archive the completed OpenSpec change.

## Verification evidence

- Focused frontend duplicate/history/picker selectors: 38 passed; administrator protected-history regression: 5 passed; backend admin-image module: 16 passed. Design target: 109 passed; frontend check: 0 errors and 0 warnings.
- Final `npm run test:gate` passed after the protected-image regression change, including real disposable functional datastores (28 passed) and backend lint/format checks. Output: session artifacts `artifact://354` / `artifact://358`.
- `python3 scripts/check_architecture.py --staged` passed against an isolated temporary Git index containing the working source snapshot: `7d4bad9987e7bf327ae5a36f7b6a68213d5048721470fc4eb7c184c35b0a0b73`, 2066 files. The user's real index was unchanged.
- Canonical `docker-compose.dev.yml` built and deployed arm64 frontend, backend and notion-worker; root Dockerfile targets also built for amd64. Runtime checks reported Node 20.20.2 on x64/arm64, OpenTofu 1.8.3 on linux_amd64/linux_arm64, and the protected field present in backend/worker models on both architectures. Frontend/backend health checks passed; the worker was running and passed its runtime import smoke (no Compose healthcheck).
- Three real Glance uploads with one repository/tag, two identical SHA-512 values and three distinct UUIDs verified one current version plus two previous versions, SHA/UUID filtering without relabeling an older result, disclosure history and current-only VM selection. Selecting the current UUID advanced the VM wizard to flavor selection; no VM was provisioned.
- Actual browser checks covered 390, 767, 768, 900, 1023, 1024 and 1280 px viewports without document-level horizontal overflow. The final deployed mobile admin cards preserved per-UUID actions; temporarily protecting the old fixture produced `protected=true` in the authenticated API and removed only its delete action.
- Test fixture UUIDs `4cc4012b-090f-40ad-9edc-d12b72ca9f1e`, `f7afa13e-8bc4-4fb2-b902-7c6a3ffb8254` and `d01d2f67-6aeb-4483-80f5-288f66f6d911` were deleted through the admin API; Glance confirmed 404 for all three. The managed browser tab was closed. Existing images, volumes and unrelated worktree changes were preserved.
- No commit, push or production deployment. Optional gbrain synchronization was unavailable because the CLI is not installed; no agent guidance files were changed.
