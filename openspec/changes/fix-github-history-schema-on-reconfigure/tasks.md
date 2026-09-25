# Tasks

## Production incident recovery

- [x] Inspect live 503 log and prove missing `vm_github_ssh_users` (MariaDB 1146), with normal DB connectivity and `auto_create_tables=false`.
- [x] Apply checksum `939571b00400bf050b9107f8e5b5a7187ae6482e88d1bfc0003af932713ef913` migration 080 only to the empty table slot; verify expected columns.
- [x] Verify real `jung-geun` GitHub profile/public-key resolution plus isolated history write/read and delete only the disposable smoke row.

## Prevent repeat on image rollout

- [x] Run existing schema bootstrap before seed/start in Kolla reconfigure and upgrade lifecycles.
- [x] Update Kolla and deployment architecture documentation with new-table vs existing-table migration limits.
- [x] Run targeted Kolla (26), YAML ordering, architecture checks and canonical `test:gate` (backend 2951, frontend 1444/248, contract 132, functional 27), preserving concurrent user work.
- [ ] Verify canonical container build architectures and safe Kolla lifecycle rollout or record the precise unmerged/authorization blocker.
- [ ] Obtain owner review/merge and verify production backend health and authenticated lookup after role rollout, then archive change.
