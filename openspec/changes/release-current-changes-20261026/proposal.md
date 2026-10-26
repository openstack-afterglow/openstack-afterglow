# Release current source and deploy approved service fleet

## Why
The user explicitly requests committing all current changes, pushing, and completing production deployment. Existing a7cae667 is a local checkpoint; completed domain-manager workspace changes remain uncommitted.

## Scope and constraints
- Integrate current completed Afterglow public changes into local dev without resetting concurrent work or including secrets. Follow current project gate, architecture and source-review requirements.
- Prepare the next available patch release after 1.30.26, push local dev normally, qualify the exact SHA in CI, then create a new immutable tag and verify published multi-architecture images and latest/stable aliases.
- Identify exact native Lumen/Palimpsest API/CLI prerequisites before deploying dependent dashboard paths. Related completed source may need its own qualified immutable release; unrelated sibling WIP is not implicitly part of this release.
- Preserve main PR/merge ownership, native reviewer approvals, all datastores/keys/IAM/config/volumes and unrelated stock infrastructure. No force pushes, tag moves, broad dependency upgrades, destructive cleanup, IAM role expansion or uncertainty replay.
- Establish current operator image/config/schema baseline, drain writers when compatibility requires it, prove protected backup/restore, then use canonical Kolla genconfig/pull/prechecks/reconfigure from /etc/kolla against complete /etc/kolla/multinode with reviewed service/skip tags and no controller-loop substitution.
- Verify exact revisions, readiness, key/config/data preservation and actual public surface/authentication boundaries. Local and synthetic proof are not production acceptance.

## Completion
Committed and published exact qualified source, immutable releases/images, safe standard fleet rollout and recorded production acceptance; any unreachable prerequisite is reported exactly with completed reachable work, never represented as deployment success.
