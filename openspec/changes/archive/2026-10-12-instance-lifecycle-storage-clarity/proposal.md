## Why

The user reported inconsistent instance action styling, dangerous live-instance archive/delete/resize exposure, Windows SSH information, misleading file-storage attachment behavior, missing attached-volume expansion, and inaccurate Windows initialization timing. The existing detail/list/storage paths must reflect provider state and authorization instead of implying guest-side work occurred.

## What Changes

1. Compose the password and adjacent instance actions from the existing shared Button primitives with consistent sizing and semantics.
2. Expose archive only for SHUTOFF, with stop/stopped guidance that quotas and allocations remain; distinguish SHELVED from SHELVED_OFFLOADED, physical compute release from Nova quotas, and retained volume consumption.
3. Expose delete and resize together with archive only for SHUTOFF in consumer/admin detail and relevant instance list/bulk controls. Retain explicit VERIFY_RESIZE confirm/revert and archived restore actions. Do not change unrelated administrator recovery or native provider API capabilities.
4. Hide SSH/keypair information for metadata-confirmed Windows instances, including volume-backed boots; do not infer OS from instance/image/flavor names or password permission.
5. Make the existing instance file-storage connection an explicit Manila access-list grant: exact selected instance fixed IP for NFS, per-instance CephX identity for CephFS, protocol validation, project/write authorization and tracked access-rule ownership. Show provider rule state/export and manual guest connection requirements; never claim automatic mounting or expose generated Linux shell commands as Windows instructions. Revoke only rules associated with this instance/share, not unrelated or broad existing grants. Share networks provide export routing/isolation, not automatic guest attachment.
6. Reuse the existing volume extension modal from attached-volume rows. Expand only, never shrink, with stopped-attachment checks and explicit distinction between Cinder disk capacity and guest partition/filesystem expansion; do not promise that shutdown alone guarantees filesystem growth.
7. State approximately 20–30 minutes for Windows first initialization and that ACTIVE/API completion is not password/RDP readiness, in four locales and affected guides.

## Capabilities

### New Capabilities

- Attached-volume expansion directly from instance details.
- Explicit instance-specific file-storage access authorization with inspectable provider connection details.

### Modified Capabilities

- State-aware instance lifecycle controls and quota/resource guidance.
- Metadata-based Windows detail projection and first-boot guidance.

## Impact

Existing frontend instance detail/list/controller, storage authorization and volume APIs/components, four locale catalogs, behavior regressions and affected API/user/design/architecture/changelog documentation. Reuse provider APIs and current authorization patterns; no production mutation, schema migration, new external dependency, automatic guest mount/filesystem mutation, commit/push or deployment. Preserve shared work/index and private configuration. Verification will use current-source HTTP/native SDK loopback transport and compiled Chromium with synthetic identity/provider fixtures, separately from live OpenStack/guest acceptance.
