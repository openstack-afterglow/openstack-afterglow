## Implementation
- [x] Install pinned Manila CLI plugin when the toolbox image lacks it.
- [x] Reproduce missing toolbox cloud profile.
- [x] Provision cloud profile before Manila checks with restricted permissions and no_log.
- [x] Fail on lookup/authentication errors instead of treating them as absent shares.
- [x] Validate YAML and exercise authenticated live share lookup and creation.
- [x] Record deployment result and remaining infrastructure blocker.
- [x] Join controller3 RabbitMQ after explicit approval and verify all six Manila pools.
- [x] Correct the CephX default to a bare user ID accepted by Manila.
- [x] Elevate the configuration project lookup for access to controller3's Docker socket.
- [x] Complete deployment after RabbitMQ cluster recovery and verify shares/access rules.
- [x] Archive change after successful deployment validation.

## Live validation (2026-09-09)
- Toolbox cloud authentication and Manila CLI now work; the deployment reached share creation.
- Created share `717d9b27-2934-4a99-a16b-aba67afaabd1` (`layer-store-rw`) entered `error`, with no assigned host or export locations. It has been preserved.
- Manila message `e090f243-887d-4ecb-b94e-0f8650909ce6` reports that the capabilities filter found no eligible storage.
- A direct RPC query to controller3's scheduler, pinned to controller3's RabbitMQ, returned only two NFS pools and no native CEPHFS pools. RabbitMQ controller3 is still a separate cluster from controllers1/2.
- The deployment was interrupted after confirming this terminal failure. The updated role now stops waiting on terminal share errors and reports failure explicitly.
- RabbitMQ cluster join was subsequently explicitly approved and completed. All three nodes report three running members, no alarms and no partitions. Controller3 scheduler now sees all six pools after restarting it.
- The original unallocated failed share was deleted and the retry created `3aa6e112-1a69-433b-84eb-b5c1240a5556` successfully (`available`). Access creation exposed an invalid `client.afterglow` default: Manila rejects periods in CephX IDs. Corrected it to `afterglow`.

## Final result
- `kolla-ansible deploy -i /etc/kolla/multinode --tags afterglow` exited 0. All hosts report `failed=0` and `unreachable=0`; log: `/tmp/kolla-afterglow-final-20260909.log`.
- `layer-store-rw`, `layer-store-ro`, `manifest-store`, and `metadata-store` are all `available`. Each has an `active` CephX rule for `afterglow`; only `layer-store-ro` has `ro`, the other three have `rw`.
- Afterglow backend and frontend containers are healthy on all three controllers.
- Keystone had already been deployed successfully, with controller3 API HTTP 200 verified.
- Role YAML parsing and `git diff --check` passed. No application endpoint changes; no commit or push performed.
