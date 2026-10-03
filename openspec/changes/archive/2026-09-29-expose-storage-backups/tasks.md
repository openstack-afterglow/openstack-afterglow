## Implementation Tasks

- [x] Investigate existing beta preferences and Manila share-backup API/driver capability; identify Kolla target and image rollout prerequisites.
- [x] Promote volume backup route and inline actions, removing browser opt-out and stale beta wiring.
- [x] Promote database backup route, create/detail/admin/restore actions, removing browser opt-out and stale beta wiring.
- [x] Document the evidence-backed Manila backup repository/driver prerequisite without pretending snapshots are backups; do not expose a failing share-backup UI/API.
- [x] Verify focused behavior, frontend/backend gate, visual smoke, built amd64 images and deployment-readiness limitation caused by the older deployed Lumen image.
- [x] Update affected docs and architecture stamp; the operator explicitly excluded File Storage backup and deferred production Kolla deployment.
- [x] Archive this completed change after image verification; commit and push are tracked by the release workflow, and production rollout is deferred.
