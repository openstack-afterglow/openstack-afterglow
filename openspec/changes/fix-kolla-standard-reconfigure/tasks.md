## 1. Implementation

- [x] 1.1 Prepare shared toolbox authentication before Cloud Shell and Manila checks without requiring Manila.
- [x] 1.2 Exercise a fresh-toolbox authenticated check and relevant Kolla contracts; update architecture and deployment guidance. (Actual isolated toolbox and Ansible: fresh creation, repeat idempotence, and authenticated cloud discovery.)

## 2. Production acceptance

- [ ] 2.1 Reconcile application channels and installed role versions while preserving datastore pins and operator settings.
- [ ] 2.2 Verify Lumen 028 recovery, actual DB classification, and writer boundaries before cutover.
- [ ] 2.3 Run exactly `kolla-ansible reconfigure -i multinode` from `/etc/kolla` and verify all selected services, image identities and public UI.
