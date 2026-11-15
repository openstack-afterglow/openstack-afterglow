# Creation-stage recovery design

## State machine and safety order

The existing system-admin detail pipeline owns the change. `creating` and `downloading` automatically load the same Cinder/Nova dependency and optional Ceph diagnostics as error states. Attachments (volume, Cinder and Nova), snapshots, backups, clones, groups/migration and unknown dependency queries remain blocking and precede creation classification. Cinder messages, backend-host presence, age and an allowlisted owner-service name are read-only evidence, never evidence of safety. Metadata values are not disclosed. `palimpsest_instance_id` identifies Palimpsest; existing `afterglow_build_id`/`afterglow_consume_id`/`afterglow_import_id` markers identify Afterglow's build/consume paths. No owner service is called.

Use module constants, not configuration: `creating` must be inactive for at least **30 minutes**; `downloading` for at least **6 hours**. Age uses `updated_at`, falling back to `created_at` only when absent. Missing/malformed timestamps and future times cannot establish staleness. Thirty minutes gives ordinary volume allocation more room than the existing 15-minute deleting grace period while allowing an administrator to recover hour/day-old stuck allocation records. Six hours deliberately allows much longer image-copy work. Neither threshold is a provider SLA, progress timeout, nor proof of death: Cinder need not update `updated_at` during creation, and a large or slow image copy can exceed either threshold.

A present RBD watcher is stronger liveness evidence than age and blocks BOTH modes with `creation_active_watcher`. Watcher details are reduced to a fixed safe state, not client addresses. Unknown watcher/backend inspection blocks; absent is not inferred from failed queries. Fully unconfigured Ceph retains the explicit age-gated, **backend-unverified** path, with the same client confirmation, warning and no claim of physical deletion. A proven absent backend needs no watcher because no image exists. Reuse the existing consistent/absent/name-mapping-missing classification branches rather than a separate creation backend policy; recoverable creation results receive `creation_stalled`, while `backend.classification` preserves the exact classification.

1. Diagnose. Fresh/unprovable age -> `creation_in_progress`; blocked dependencies/backend/watchers -> existing blocking diagnosis or `creation_active_watcher`.
2. Validate exact `confirm_volume_id` and observed `expected_status` against the live creation-stage diagnosis in the service for BOTH modes. No native writes on mismatch.
3. Under the existing per-volume Redis lock, repeat full diagnosis, age/dependency/backend/watcher safety; re-read live volume status and attachments immediately before reset. State drift -> safe conflict, no reset.
4. `recover`: call Cinder `os-reset_status` with `status=error` only (do not falsify attach status), repeat diagnosis and verify `error` plus safety, then return `state_reset` and refreshed diagnostic. Do not restore RBD mappings, delete, change quota, or cancel owner jobs. Already `error` is an idempotent no-write recovery result after diagnosis/recheck.
5. `force_delete`: perform the same confirmed reset and verification for creation, then reuse existing optional name-mapping restore/verify, Cinder `os-force_delete`, Cinder absence/all-project list, Ceph backend and quota verification. Repeat full dependency/backend/watcher diagnosis immediately before the destructive call and require `error`; creation-origin calls never reset attach status as a workaround. Existing old-error no-body calls retain their existing pipeline, including their narrowly scoped attached-400 retry.
6. Refresh list/detail after either mode and preserve timeline. Only verified `deleted`/`already_deleted` closes the detail. `state_reset`, failures, pending deletion, residue and unverified backend remain visible.

## Request compatibility and failure matrix

Optional JSON body: `mode` is `recover|force_delete` (default force-delete), `confirm_volume_id`, `expected_status`. No-body old-error calls retain legacy behavior. Explicit force-delete bodies require well-formed confirmation fields at schema validation; creation recovery keeps fields schema-optional so the service can issue the fixed safe conflict. Both dashboard modes send exact id/status for creation.

| Condition | Result | Native writes / retained state |
| --- | --- | --- |
| Missing/invalid explicit force-delete fields | HTTP 422 | None; schema refuses request |
| Missing/mismatched recover creation confirmation; well-formed force-delete mismatch | HTTP 409, fixed safe message | None |
| Live creation status changes before reset | HTTP 409 | None; refresh/reconfirm |
| Fresh creation, dependencies, active/unknown watcher or unsafe backend | Blocked diagnosis/result | None |
| Redis lock busy/unavailable | HTTP 409/503 | None |
| Reset rejected or returned status not error | `failed`, steps retained | No delete; observed current state reported |
| Reset succeeds; safety changes or force-delete fails | `failed`, successful reset and failure steps retained | Volume is normally left `error`, safe for explicit retry; provider can independently change state |
| Reset succeeds, recover mode | `state_reset`, final `error` | State reset only; no delete/mapping/quota writes |
| Cinder delete accepted, record remains `deleting` | `delete_submitted` | Never claim deletion complete |
| Creation-origin force-delete returns a present non-deleting state, especially `available` | `failed`; `creation_delete_state_changed:<status>` step and refreshed diagnostic | No automatic re-reset or further mutation. Incomplete data may now be usable. Check owning service, wait for watcher disappearance, re-diagnose; ordinary admin delete is possible when `available`. |
| Cinder absent, Ceph residue/unknown/unconfigured | `backend_residue`/`backend_unverified` | No direct image/header/data/trash removal |
| Cinder and configured Ceph absent | Existing `deleted` | Quota result reported separately |

Fresh system-admin authorization, lock release, `volume.recover_delete` audit (mode, previous/final status, safe checks/steps) and cache invalidation apply to both modes and partial mutated failures. No database/schema/setting changes; existing deployment schemas and old readers are unchanged.

## Upstream source-read and bounded production read observation

Repository notes still mention stock Kolla2025.2 pins and also document toolbox authentication on2026.1+. The coordinator supplied a **read-only production observation on2026-11-15**, using `docker inspect` and `pip show` inside controller1's running container: image `quay.io/openstack.kolla/cinder-volume:2026.1-ubuntu-noble`, build-date label `20261110`, Cinder package `28.0.1.dev16` (2026.1 series). The installed `manager.py` contains the `except exception.VolumeIsBusy:` handler at line1014 (also3991); the installed RBD driver contains `ImageBusy` handling. This proves the code path exists in that development snapshot, not that any busy deletion or reset-to-available outcome occurred in production. No further production access or write was performed for this change.

Read both upstream branches on 2026-11-15:

- Primary deployed-series reference: [Cinder stable/2026.1 RBD driver, lines1492–1510](https://github.com/openstack/cinder/blob/stable/2026.1/cinder/volume/drivers/rbd.py#L1492-L1510); secondary [stable/2025.2, same lines](https://github.com/openstack/cinder/blob/stable/2025.2/cinder/volume/drivers/rbd.py#L1492-L1510). Both directly remove, handle `ImageBusy`, try child flattening/removal retries, then translate persistent `rbd.ImageBusy` to `exception.VolumeIsBusy`.
- Primary [Cinder stable/2026.1 manager, lines1017–1023](https://github.com/openstack/cinder/blob/stable/2026.1/cinder/volume/manager.py#L1017-L1023); secondary [stable/2025.2, same lines](https://github.com/openstack/cinder/blob/stable/2025.2/cinder/volume/manager.py#L1017-L1023). Both invoke `_clear_db(volume, 'available')` on `VolumeIsBusy` and return skipped deletion. Installed development-snapshot line numbers differ from these branch references.

Thus deleting a busy, potentially half-written image is not a reliable fail-safe: Cinder can restore `available`. A reset can also race with the creator's independent completion update. The new creation watcher gates and repeated checks reduce this risk; they do not create a transaction with Cinder/c-vol or cancel its work. Watcher absence is a point-in-time observation, not a future guarantee.

Out-of-scope follow-up: the existing **error-state** consistent-backend recovery branch does not block present watchers. This change deliberately does not alter that older policy. Production owner-service/build state, actual Ceph credentials, real copying workload behavior and real residue/quota release remain unverified by local fakes or browser fixtures.
