## Tasks

- [x] Capture actual local image/config/DB/key/mount identities and exact same-executor Compose render without secret disclosure.
- [x] Inspect actual Kolla0.6.9 source and shared DB read-only; prove the legacy/new credential-storage incompatibility and preserve current development source.
- [x] Build and execute the already-fixed development API/worker on both architectures to isolate the PID1 bug; do not mistake this for legacy compatibility.
- [x] Select the exact existing Kolla-compatible revision (`6ca10eed`) and source-build it through the canonical Dockerfile without switching the user's checkout; arm64 and amd64 API/worker images built.
- [x] Provide canonical `LUMEN_BUILD_CONTEXT` selection and native-contract gating (`selection_policy`) with legacy provider-level auth UI; behavior regressions added and mutation-checked.
- [x] Capture a protected shared-DB backup, prove restore on matching MariaDB, rehearse the bounded repair and verify preservation; the legacy `0.6.9` ORM and legacy auth-attempt INSERT were exercised against the repaired copy.
- [x] Stop only the six Kolla and two local Lumen writers with explicit user authorization, take a post-drain backup proven by fresh restore, apply the three guarded statements, restart the same containers and verify identical IDs/images and health.
- [x] Deploy local Lumen API/worker and the previously created Afterglow backend/frontend with `--no-deps` and no migration job; verify health, no backend SQL/ERROR lines, and identical decryption of the five existing provider API keys locally and in production.
- [x] Run the unchanged canonical gate (backend 8972/95 skipped, frontend 4958/432 files, contracts 181, DB 166/33 deselected, Ruff clean), working/isolated-staged architecture parity, docs, changelog and archive.

## Not verified (explicit limits)

- Any live provider call, OAuth or subscription flow, and any logged-in administrator screen; no real password was used.
- Promotion to the account runtime. That needs its own drain and reconciliation of the two credential copies.
- Concurrent Kolla requests during the window: production had no chat run since 2026-10-14, which is an observation and not a fence.
