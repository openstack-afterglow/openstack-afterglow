## Why

The operator wants the standard Kolla-Ansible 2025.2 `pull` and subsequent deployment to follow the newest published application images without editing version numbers. All five projects already publish `latest`; the current sample pins versions, and the extracted roles reject unresolved `latest` references. Removing those validators alone would allow controllers to resolve different images during a rolling deployment.

## What Changes

- Select the existing `latest` channel in the Afterglow integration sample for Afterglow, Drover, Waygate, Lumen, and Palimpsest; retain explicit version/digest overrides for rollback.
- Before the selected custom service role's precheck/pull/deploy/reconfigure/upgrade, resolve its enabled moving image references to registry manifest digests once on the first targeted controller. Reuse the same immutable references through every serial batch in that invocation; resolve afresh in the next invocation.
- Use the Docker Engine distribution descriptor API and the existing Docker SDK/registry credentials rather than requiring Buildx, new registry credentials, or source builds. The helper is read-only: `pull` remains responsible for downloading layers and deployment actions for replacing containers.
- Existing sibling immutable-reference validators continue to validate the resolved digests. Preserve `--tags`, `--limit`, disabled components, source-build mode, explicit image refs, Cloud Shell digest policy, and datastore pins.
- Fail before registry lookup or role dispatch when targeted controllers have different component enable flags; use explicit `--limit` groups with matching flags rather than silently omitting later-enabled components.
- Keep existing tested image publishers, immutable root-role Git pins, and promotion boundaries unchanged. `stable` is accepted when an operator supplies a published alias; it is not a fallback for a missing `latest` image.

## Capabilities

### New Capabilities

- Per-invocation, serial-safe image channel resolution for the standard five-service Kolla integration.

### Modified Capabilities

- The sample's application image selection follows `latest` instead of hardcoded versions.
- Version synchronization checks distinguish the automatic image channel from release version pins.

## Impact

The change is scoped to Afterglow's Kolla composition, resolver/helper behavior tests, configuration examples, and deployment documentation. Service runtime source and existing CI publication semantics do not change. Operator role packages remain independently versioned and reviewed; image updates are not a claim of arbitrary future API/schema compatibility. No production reconfigure, pull, restart, registry publication, or datastore change is authorized by this implementation. The previously observed OpenSearch/RBD fault remains an independent production rollout prerequisite.
