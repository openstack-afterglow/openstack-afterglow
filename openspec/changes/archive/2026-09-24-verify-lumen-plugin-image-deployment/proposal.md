# Verify Lumen plugin image deployment

## Goal
Recover the reported local Compose lumen-migrate failure and verify current-source builds, migrations and deployment without deleting data or volumes.

## Scope
The migration failed before SQL execution because its built image lacked lumen-plugin-api. Current Lumen development includes workspace dependencies/copies and a refreshed lock; Lumen's fix-plugin-image-packaging change adds build-time guards. Rebuild through docker-compose.dev.yml, verify the affected Lumen shared-runtime targets on amd64/arm64, and deploy the existing afterglow-local-services project. Check all required one-off exits, service readiness and real authenticated Afterglow/Lumen/OpenStack reads. Do not enable unrelated controller/sandbox cloud resources, alter secrets, commit/push, deploy production, or claim paid provider inference.
