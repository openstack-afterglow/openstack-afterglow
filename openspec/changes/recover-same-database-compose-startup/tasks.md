## Implementation Tasks

- [x] Preserve exact direct-Compose environment and current failure/container evidence; inspect all Galera members without writes.
- [x] Obtain explicit controller1 normal-rejoin approval; preserve configuration and cold datadir, then stop/start only its native MariaDB service.
- [x] Observe controller1 Primary/Synced in the original cluster and verify same-endpoint application schema reads; preserve controller2/3 processes.
- [x] Inspect exact candidate-image ORM/manifests and current shared schemas; identify obsolete Lumen0.6.9 pin and missing Afterglow SQL103 column.
- [x] Preserve old source snapshot and change only approved LUMEN_BUILD_CONTEXT to exact deployed Lumen0.6.12; build and execute canonical arm64/amd64 images.
- [x] Compare effective keys/config and writer census; restore a protected consistent snapshot and qualify SQL103 without changing shared schema.
- [ ] Apply SQL103 with required quiescence. **Blocked by latest explicit user decision: “키·운영 앱은 변경하지 않음”.** Production keys/apps/schema remain unchanged; isolated qualification is not live application.
- [ ] Start canonical local Compose and verify authenticated GET paths. **Blocked by the same decision:** Afterglow/Waygate/Drover encryption-key mismatch and missing SQL103 cannot be bypassed. No partial writer startup or migration replay.
- [x] Record operational evidence and remaining risks in existing architecture/deployment/testing docs. Keep this change unarchived while full-startup acceptance is blocked.
