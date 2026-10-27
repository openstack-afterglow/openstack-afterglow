## 1. Implementation

- [x] 1.1 Prepare shared toolbox authentication before Cloud Shell and Manila checks without requiring Manila.
- [x] 1.2 Exercise a fresh-toolbox authenticated check and relevant Kolla contracts; update architecture and deployment guidance. (Actual isolated toolbox and Ansible: fresh creation, repeat idempotence, and authenticated cloud discovery.)

## 2. Production acceptance

- [ ] 2.1 Reconcile application channels and installed role versions while preserving datastore pins and operator settings. Controller application channels switched; dedicated Palimpsest build worker remains quarantined on its separate pin and is not included by the aggregate play.
- [x] 2.2 Verify Lumen 028 recovery, actual DB classification, and writer boundaries before cutover. Final encrypted backup `lumen-final-control-5dfwj9fw` restored 66 MariaDB and 4 PostgreSQL tables in isolated containers; 028 apply and repeat passed. Local shared-DB API and worker drained; production 028 ledger is present with matching checksum.
- [ ] 2.3 Run exactly `kolla-ansible reconfigure -i multinode` from `/etc/kolla` and verify all selected services, image identities and public UI. Untagged attempt timed out after 3600 s in stock Designate; user then authorized `--limit` and `--tags`. `--limit compute` succeeded for 12 nodes; `--limit control --tags afterglow,lumen,waygate,drover,palimpsest` succeeded for all three controllers, all API/frontend containers healthy and workers running. Public Afterglow 200, Lumen and Palimpsest readiness 200; authenticated login and build worker remain unverified.
