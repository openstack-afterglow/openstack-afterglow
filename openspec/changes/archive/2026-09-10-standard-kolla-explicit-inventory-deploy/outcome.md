# Standard Kolla deployment verification

## Implementation
- Custom service and HAProxy plays now declare `become: true`, including standalone compatibility playbooks. The native Kolla CLI, stock site import, inventory and globals.d loader remain authoritative.
- Four delegated Afterglow source stat/projection tasks explicitly keep `become: false`. Owner-only sanitized staging remains readable by Ansible's controller-side file lookup; privileged runtime writes retain sudo.
- Installer and operator lock align on verified `lumen-kolla==0.2.0`, SHA-256 `d55e2b0ace06d232452f9dd2892a88912755e9d00e99de0e59d6738c5a3b2474`. Lumen remains package-owned; no sibling Lumen source edits were needed.
- Operator instructions target the actual environment using `UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project`, then install the integration once. Ordinary invocation from `/etc/kolla` is `kolla-ansible deploy -i multinode`.

## Local verification
- `npm run test:kolla:contract`: 22/22 passed.
- `npm run test:kolla:runtime`: 7/7 passed. Executes native Kolla CLI/parser and real Ansible against harmless role/action fixtures: exact untagged command, optional tag isolation, absent disabled roles, standalone plays, four real operator task declarations, and negative controls for both missing privilege boundaries.
- Final `npm run test:gate`: exit 0, log `/tmp/afterglow-standard-kolla-gate-final.log`. Backend unit 2707 passed, frontend 1190 passed (212 files), contracts 112 passed, functional 24 passed; backend lint and format passed.
- Working architecture check passed. Required staged architecture check passed against a temporary task index (`5a8c5e589921bf0dfa4a4d88129de37b5330ddf625d9475c82b554f321b52b4d`); the user's actual index and working architecture were preserved.
- Independent deployment reviewer approved implementation, fixtures and operational patch; separately approved active-secret-preserving reconciliation.

## Operator preparation
Host `172.30.0.50`, checkout `/etc/kolla/plugins/openstack-afterglow`.
Backup: `/home/pieroot/kolla-standard-deploy-backup-20260910T155201Z` (0700 directory, saved files 0600).

Only service privilege declarations and installer version/help were changed on the installed integration; pre-existing dirty Afterglow role modifications were retained. The operator already had Lumen 0.2.0; its old installer expected 0.1.7 and was aligned. No Kolla or role package upgrade was performed.

The active regular `globals.d/91-openstack-afterglow-secrets.yml` contained all canonical keys with identical values plus two Lumen S3 keys. Both originals were backed up. Active bytes replaced canonical `config/afterglow/secrets.yml` atomically, and the active path became a symlink to canonical. Effective YAML equality was asserted; no credential value changed or was printed. Installer rerun succeeded.

Scoped prechecks without `--become`: 44 ok, 1 changed, 0 failed, 0 unreachable.

## Live deployment and health
Executed on the operator from `/etc/kolla`, using `/etc/kolla/.venv`, without `--become`, custom playbook or extra-vars overrides:

```sh
kolla-ansible deploy -i multinode --tags afterglow,lumen,drover --limit dms-controller3
```

Exit 0: **201 ok, 14 changed, 0 failed, 0 unreachable**, 54 skipped. Log: `/home/pieroot/kolla-standard-deploy.log`. Afterglow DB/bootstrap/Manila prerequisites and Lumen bootstrap/PostgreSQL steps retain their normal controller1 delegation despite controller3 limit. Installer repeated successfully after deployment, including the corrected exact command help.

- Controller3 Afterglow backend/frontend, Drover API, Lumen API and HAProxy: running and healthy. Workers: running. Lumen worker retained its existing restart count 1 and start time `2026-09-10T11:12:11Z`; other inspected containers had restart count 0.
- Controller3 direct Afterglow API **configured** port 18020 `/api/v1/health`, frontend 18081 `/`, Drover 18011 `/v1/health/ready`, Lumen 18012 `/v1/health`: HTTP 200. An initial probe of the documentation's default Afterglow port 18000 refused connection; inspecting the actual container healthcheck identified the preserved operator override 18020.
- From controller3 Lumen API: authenticated MariaDB SELECT 1, Redis PING and PostgreSQL SELECT 1 all passed. The first diagnostic script used a newer Redis connection-close method than the installed client supported; adapting the diagnostic to its existing close API completed all checks without application changes.
- Normal DNS/TLS via system curl: `https://cloud.dmslab.re.kr/api/v1/health`, `https://drover.dmslab.re.kr/v1/health/ready`, `https://lumen.dmslab.re.kr/v1/health` all HTTP 200. System curl was used after local Python urllib lacked a usable trust path; TLS verification remained enabled.

## Scope and remaining boundaries
The exact untagged command is validated by native CLI/Ansible fixtures. Live execution deliberately covers the requested services on controller3, including role-defined delegated prerequisites; it is not evidence of an entire OpenStack cluster redeployment. Operators can use the documented untagged command to include stock services, subject to their own existing service prerequisites.

No application image pin, database storage identity, inventory or credential value was changed. No Kolla runtime upgrade, source commit, push, PR or main merge was performed. Unrelated local/operator edits and the user's real index remain preserved.

