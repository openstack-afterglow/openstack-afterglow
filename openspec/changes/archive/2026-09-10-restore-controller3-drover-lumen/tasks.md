# Tasks

- [x] Inspect controller 3 and identify missing runtime/configuration/ingress.
- [x] Inspect operator inventory, variables, role packages, and immutable image references.
- [x] Pass scoped Kolla prechecks and verify actual Ansible target hostname.
- [x] Independently review recovery and satisfy delegated-bootstrap/PostgreSQL prerequisites.
- [x] Reproduce deploy blocker: toolbox Docker access denied without `--become` (20 ok, zero changed, one failed). Privileged Ansible Docker queries already pass; retry standard deploy with `--become`.
- [x] Restore Drover and Lumen using scoped Kolla deployment (`--become`; 105 ok, 24 changed, zero failed/unreachable).
- [x] Verify migrations, API dependencies, worker stability, and HAProxy/VIP paths.
- [x] Record outcome, obtain independent final approval, and prepare completed operational change for archive.
