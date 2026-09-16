# Controller 3 recovery evidence

## Result
Drover and Lumen were restored on `dms-controller3` (`172.30.0.13`) using the existing operator environment on `wireguardserver` (`172.30.0.50`). Final verification time: `2026-09-10T15:24:06Z` (2026-09-11 00:24 KST).

## Findings
- Initially no Drover/Lumen API or worker containers existed, even stopped. Service configuration directories and HAProxy fragments were absent; ports 18011, 18012, 8011, 8012 refused connections. Cached images remained.
- Operator inventory correctly includes controller 3 in both service groups and enables both services. The other two controllers run the same immutable image revisions. The historical action that removed/omitted controller 3 resources was not established.
- Standard prechecks passed (28 ok, zero changed, zero failed), but deploy without privilege escalation failed in `drover/tasks/config.yml` at service-project lookup because the toolbox module could not access the Docker socket. That failed run made zero changes.
- Retrying the same deployment with `--become` passed the exact previously failing task and completed. This is a reproduced deployment blocker; it does not prove the cause of the earlier resource disappearance.
- The Drover default `v0.2.19` image accessibility warning checks a tag rather than the configured immutable image reference. It did not block this digest-pinned deployment.

## Applied operation
Executed from `/etc/kolla` on the operator host, with `/etc/kolla/.venv/bin` on PATH:

```sh
/etc/kolla/.venv/bin/kolla-ansible deploy --become --tags drover,lumen --limit dms-controller3
```

Ansible recap: **105 ok, 24 changed, 0 failed, 0 unreachable**, 38 skipped.

The standard roles rendered controller 3 settings/secrets, ran both migration jobs, started four service containers, generated internal/public HAProxy fragments, and reconciled controller 3 HAProxy. DB users and catalog endpoints/projects were unchanged. Keystone service-user reconciliation reported changes; Drover user handling retried once. Bootstrap and PostgreSQL checks delegated to controller 1 as defined by the roles. Existing PostgreSQL container reconciliation was unchanged and its authenticated SELECT 1 passed; its persistent volume remained `lumen_postgres_data` and bind address remained `172.30.0.11:5432`.

No application source, image pin, operator globals, inventory, shared password file, or role package was edited. No commit, push, release, or main merge was performed. Existing unrelated local and operator checkout modifications were preserved.

## Immutable service images
| Service | Manifest digest | Source revision |
|---|---|---|
| Drover API | `82ed8fe7bde9c0b76d03009f24a3e3c3df367be0b62682166765a02eed568380` | `3264e7cc66a0dfc297615a052b24cc5165a46700` |
| Drover worker | `bdd24344f587fc46a370f54c66bd1c0815a6a460ea98d8f1fd6b6b46aea5053f` | same |
| Lumen API | `3ed9ab018a7454fd60a535b73f7668c0e1ed4b90d3d00f227e1e5a40f3995261` | `368a2598f82964017b616527e1956a6fd3b3ab50` |
| Lumen worker | `a2661c2fbc83f8062c45ce8ae35ad64e3de172ab32ce025da93e2fc8cbab77c9` | same |

## Verification
- All four controller 3 containers running. Both APIs and HAProxy healthy.
- Drover local `/v1/health/ready`: HTTP 200; database, Redis, migration ledger and Keystone all `ok`.
- Lumen local `/v1/health`: HTTP 200. Separate authenticated in-container MariaDB SELECT 1, PostgreSQL SELECT 1 and Redis PING all passed.
- TLS requests forced through VIP `172.30.0.254`: Drover readiness and Lumen health both HTTP 200.
- Final normal DNS/TLS requests: `https://drover.dmslab.re.kr/v1/health/ready`, `https://lumen.dmslab.re.kr/v1/health`, `https://cloud.dmslab.re.kr/api/v1/health` all HTTP 200.
- Drover API/worker and Lumen API restart counts: zero. Lumen worker restart count: one, unchanged across observations. It restarted at `2026-09-10T11:12:11Z` after an initial MySQL VIP connection failure and was still running at final verification over four hours later. The inspected recent 15-minute worker logs contained zero error lines.
- Local Afterglow Kolla contract suite: 22 passed. Its initial sandbox-only cache-permission failure was resolved by running with approved permissions; no test source change was needed.
- Initial standalone Lumen dependency probes used a cleanup API absent from the deployed Redis client, obscuring the successful connection with AttributeError/event-loop cleanup errors. An independent SELECT/PING probe with compatible client cleanup passed; those probe errors were not treated as runtime service failures.
- Independent recovery reviewer approved the operation after delegated config, image compatibility, PostgreSQL identity and HAProxy inclusion checks; final closure was approved contingent on the subsequently successful public DNS/TLS and Afterglow health checks.

## Limits and follow-up
Actual authenticated VM creation and model/chat execution were not performed; these results demonstrate deployment and dependency readiness, not those workflows. The original resource-removal event remains unproven. Retain the initial Lumen worker restart as a recovered startup event.

No code/config/schema/dependency/deploy-source/test changes were authored, so source architecture stamping and source-change/full commit gates do not apply to this operational record. Existing published images were redeployed, with live verification above. The broader source-audit candidates (fresh install ordering, mutable/source-image lifecycle, staging workflow paths) were not changed or claimed as causes of this controller 3 incident.
