## Implementation Tasks

- [x] Trace launcher absence to the active local configuration snapshot and establish dedicated-project ownership/local rollout choices.
- [x] Default Cloud Shell interface to public across backend, examples and generated deployment configuration.
- [x] Resolve a missing Cloud Shell network from the dedicated project's default network with project isolation and external connectivity.
- [x] Resolve the dedicated project's default security group without requiring a global egress-only group.
- [x] Update affected config/Kolla contracts and exercise provisioning success/failure boundaries.
- [x] Make Cloud Shell Zun calls stock-Zun compatible: `container 1.36` header, no `privileged` field, owner `stop=true` delete, `raise_exc=False` status mapping. Regression test fails on pre-fix code (406) and on the code without `raise_exc=False` (404).
- [x] Apply Cloud Shell-only local config, preserve all unrelated settings, build/restart backend/frontend (and notion-worker, approved) and observe actual capability/launcher behavior.
- [x] Live (approved): grant `member` on `cloud_shell`, set `nova.default_external_network=private_provider`, auto-provision the dedicated `Default` network/router, and verify Zun create acceptance, `stop=true` delete and 404 mapping as `member`.
- [x] After runtime proof, update affected documentation/architecture and archive this change, with verification limitations recorded.

## Verification Limitations

- The live container reached `Error`: zun-compute failed `mkfs -t ext4` on the Cinder RBD device for the home mount. Shell attach, bootstrap, token injection and CLI use were not verified live. This is a Zun compute Cinder/RBD host issue, not the request contract.
- Temporary 1 GiB verification volume `177b832b-7603-466a-8772-4fbadce3ee0c` (`afterglow-zun-compat-*`, project `cloud_shell`) remains. Two delete attempts went `deleting → available`, consistent with an RBD watcher left mapped on the zun-compute host after the failed mkfs. It needs `rbd unmap` on that host before `openstack volume delete`.
- Browser verification used the real served frontend, SSR config and backend `/api/v1/site-config`; only authenticated user endpoints were synthetic. No production deployment.
