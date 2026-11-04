## Implementation

- [x] Build an installable root distribution with versioned Kolla role, aggregate playbook and integration tools; name the distribution exactly `afterglow-kolla` and retain `share/afterglow/kolla`.
- [x] Migrate installer and uninstaller safely from legacy checkout links; preserve unknown paths and operator state, support separate exact role/site legacy targets, and refuse installed retired `openstack-afterglow` metadata.
- [x] Document explicit pip/uv installation, unpublished-package boundaries, retired-distribution removal/reinstall order, upgrade/migration and stock Kolla wiring.
- [x] Verify isolated real wheel install, synthetic-version upgrade, legacy migration and actual Ansible role loading; run isolated Kolla CLI runtime fixtures.
- [x] Match the operator's Python 3.11 floor and verify a real isolated Git-source uv lock/sync and installed helpers on Python 3.11.
- [x] Requalify renamed `afterglow-kolla` wheel, retired-metadata refusal, pip upgrade and mixed-checkout target migration in isolated Python3.11 fixtures.
- [ ] Publish a reviewed release and promote its immutable artifact into the operator dependency lock; current release tag does not contain this distribution.
- [ ] Qualify canonical Kolla deployment and multi-architecture image operation on an authorized isolated target.
