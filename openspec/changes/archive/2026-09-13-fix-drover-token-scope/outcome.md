# DMSLab 운영 반영 기록 (2026-09-14)

## 결과

`cloud.dmslab.re.kr` 대시보드의 `Drover 클러스터` 타일이 `사용할 수 없음`에서 `0 활성`으로 복구됐다. Drover API는 더 이상 `/v1/stats/clusters`에 401을 반환하지 않는다.

## 반영한 소스 (repo `drover`, branch `dev`)

| commit | 내용 |
|---|---|
| `e35412b` | `X-Project-Id` 없는 호출에서 제출된 토큰을 `GET /v3/auth/tokens`로 introspection하여 원래 project scope를 보존. 무범위 재인증 제거. |
| `80f9d01` | internal identity endpoint를 `/v3`로 정규화. Kolla catalog는 버전 없는 identity endpoint를 등록하므로 bare endpoint의 `/auth/tokens`·`/roles`가 404였다. |
| `0806c02` | `80f9d01`이 별도 workstream의 기존 staged 파일(architecture guard scaffolding, CI step, 루트 문서, 무관한 docs 재작성)을 함께 커밋한 것을 되돌림. 인증 수정만 유지하고 해당 파일은 로컬 상태로 복원. force-push 없이 전진 커밋으로 처리. |

토큰 검증과 관리자 role 조회는 이제 catalog의 `identity` **internal** endpoint만 사용하고, 실패 시 external/public으로 fallback하지 않는다.

## 배포

- 운영 pin 파일: `/etc/kolla/globals.d/90-openstack-afterglow-globals.yml` (wireguardserver `172.30.0.50`).
- 변경 전 백업: `/home/pieroot/afterglow-kolla-globals-before-drover-20260914T132830Z.yml` (mode 0600, sha256 일치 확인).
- 최종 pin
  - `drover-api@sha256:a2f7838a455b246ec59bfbeef4da5147473b1c81e2438c866e4d6043fae5c2df`
  - `drover-worker@sha256:00a97c9f7952de19bd4bab6500978e733b15556ec014586cca7263a2a82cd2de`
- 적용 명령: `kolla-ansible pull|reconfigure -i multinode --tags drover --skip-tags haproxy --become`.
  중간 1회차(`e5d0d908…`/`72ac1b62…`)는 `--skip-tags haproxy` 없이 실행되어 공용 HAProxy/Keepalived가 재시작됐다. 최종 회차는 shared loadbalancer play를 건너뛰고 Drover 컨테이너만 교체했다.

## 검증 (2026-09-14 13:46–13:53Z)

- controller1/2/3 `drover_api` = 새 digest, `running`, `healthy`, RestartCount 0. `drover_worker` = 새 digest, `running`, RestartCount 0.
- 세 controller의 `http://<host>:18011/v1/health/ready` 및 `https://drover.dmslab.re.kr/v1/health/ready` → 200, `database/redis/migrations/keystone` 모두 `ok`.
- 실제 운영 로그인 세션으로 `GET /api/v1/dashboard/k3s-stats?no_cache=true` → 200 `{"total":0,"active":0,"available":true}` (동일 계정의 배포 직전 응답은 `available:false`였다).
- `GET /api/v1/admin/k3s-clusters` → 200, `GET /api/v1/dashboard/summary` → 200.
- Drover 로그(배포 후): `/v1/stats/clusters` 200 ×6, 401 ×0, `Failed to resolve Keystone admin role` ×0, `keystone.dmslab.re.kr` ×0 (내부 VIP 사용).
- Afterglow backend 로그: 배포 후 90초 창에서 `dashboard Drover stats 조회 실패` 0건 (배포 전 13:44:53Z에 마지막 경고 기록).
- 실제 브라우저(headless Chrome, 1440×900)로 운영 로그인 후 `/dashboard` 요약 행이 `Drover 클러스터 0 활성`을 표시(스크린샷 `.local-services/logs/drover-dashboard-tile-verified.png`). `/admin/drover` 관리자 화면도 정상 렌더링.

## 범위 밖·남은 항목

- Afterglow 소스는 변경하지 않았다. `k3s-stats` 핸들러의 `available:false` 흡수 계약은 그대로다.
- Drover 저장소의 architecture guard workstream(`ARCHITECTURE.md`, `scripts/check_architecture.py`, `.github/workflows/ci.yml` guard step 등)은 사용자의 진행 중 작업이라 커밋하지 않았다. `80f9d01`에서 잘못 포함됐던 파일은 `0806c02`로 원복했고 작업 트리 내용은 보존했으나, 해당 파일들의 **index staged 상태는 복원되지 않았다**(내용은 동일, 다시 `git add` 필요).
- 13:53Z 검증에서는 실제 lifecycle을 실행하지 않았다. 아래 후속 incident에서 DMSLAB 프로젝트의 1+1 클러스터 생성·헬스·삭제를 완료했다.

## 후속 incident: 실제 cluster create 401 (2026-09-14 13:52–15:22Z)

### 원인

사용자가 생성한 `test-cluster`의 durable create job은 첫 Neutron 보안그룹 생성에서 Keystone 401로 실패했다. Worker의 `get_admin_connection_for_project(project_id)`가 서비스 계정 username/password를 임의 tenant project에 직접 scope했기 때문이다. 운영에서 동일 서비스 계정의 service project 인증은 성공했지만 DMSLAB project scope 인증은 401이었다. 서비스 계정은 service/admin project에만 role이 있으므로 이것은 올바른 Keystone 동작이다.

Drover에는 이미 프로젝트별 `afterglow-cluster-mgr-<project>` 사용자, 암호화된 자격 저장, 최소 role 부여 구조가 있었지만 application credential 생성에서만 일부 사용했고 create/delete/scale/health/reconcile worker 경로는 잘못된 service-account tenant scoping을 계속 사용했다.

### 수정·배포

- Drover commit `7902506` (`fix(worker): use tenant manager credentials`).
- `ensure_cluster_manager_user()`는 service 계정의 유효한 admin-project scope로 Keystone identity 작업을 수행한다.
- `get_project_manager_connection()`이 암호화 저장된 프로젝트 manager 자격으로 tenant-scoped OpenStack connection을 반환한다.
- create, agent/HA bootstrap, delete, nodegroup scale/reconcile, health probe, OpenStack drift reconciliation, Stampede flavor lookup, HA callback 경로를 모두 새 connection으로 전환했다.
- 로컬 검증: 623 passed, 3 skipped; Ruff 통과. GitHub CI와 Docker Build & Push run도 전부 성공.
- 1차 auth-fix 운영 pin:
  - `drover-api@sha256:8847e513e581debec01a1583cc2c2170c9f4910e5bf5d06105646ea4d1f5c73a`
  - `drover-worker@sha256:56822b0310131ad4c9f0c71dd2e7a2379b6e14c5042241a19cea4352ffabd69b`
- 배포 직전 pin 백업: `/home/pieroot/afterglow-kolla-globals-before-drover-manager-20260914T141031Z.yml` (mode 0600, source/backup sha256 `4be0d73f…` 일치).
- `kolla-ansible pull|reconfigure --tags drover --skip-tags haproxy` 성공. controller1/2/3 API는 새 digest, `running|healthy|RestartCount=0`; Worker는 새 digest, `running|RestartCount=0`; readiness 4개 check 모두 `ok`.

### 실제 lifecycle 검증

1. DMSLAB manager connection으로 기존 실패 지점과 동일한 Neutron security group create/delete를 실행해 인증과 cleanup을 확인했다.
2. 원래 실패한 `test-cluster` (`07142afa-…`)를 관리자 delete job으로 제거했다.
3. 첫 검증 요청(`9425d148-…`)은 검증 스크립트가 `network_id`를 빠뜨려 `primary_network_id` validation에서 실패했다. 이때 **Drover create job의 자원 누수 결함**이 노출됐다: `create_cluster_job`이 `neutron.create_security_group`과 `cinder.create_volume_from_image`를 먼저 실행한 뒤 `cloudinit.generate_server_userdata`에서 `primary_network_id` 입력 검증에 걸려 예외를 던지며, worker retry(최대 3회)마다 매번 새 SG와 Cinder volume을 생성해 총 3개 SG와 3개 Cinder volume이 누수됐다. (인증 401은 발생하지 않았고, 누수된 3개 볼륨과 3개 SG는 후속 delete job으로 모두 정리했다). 후속 과제로 API 레벨 사전 검증(또는 `instance_orchestration.resolve_default_network` 연동) 및 시도별 자원 rollback이 필요하다.
4. 원래 사용자 요청과 같은 DMSLAB network를 지정해 `drover-verify-7902506-v2` (`f307f50a-…`, server 1 + agent 1)를 실제 Afterglow API로 생성했다.
5. 상태가 `CREATING → PROVISIONING → ACTIVE`로 전환됐고 server VM, agent VM, API address가 기록됐다. Worker 로그: `ACTIVE: 1 agents created, 0 failed`; K3s `/healthz`와 `/api/v1/nodes`가 각각 200.
6. 검증 클러스터를 delete job으로 제거했다. Nova server 2개, Cinder volume 2개, security group 1개 삭제 로그와 최종 cluster record 제거를 확인했다.

### 조사 중 조치와 별도 관찰

- **운영 DB/Keystone 직접 변경 보고**: 진단용 독립 smoke 스크립트가 Keystone에서 기존 manager 사용자(`afterglow-cluster-mgr-ed38d6d0`)의 비밀번호를 새로 발급했지만, 진단 프로세스에 DB 세션 팩토리가 초기화되지 않아 MariaDB `project_manager_credentials` 테이블이 갱신되지 못하고 불일치가 발생했다. 이 진단 부작용을 해소하기 위해 MariaDB에서 해당 프로젝트의 stale row 1건을 수동 삭제(`DELETE FROM project_manager_credentials WHERE project_id = ...`)했고, 이후 정상 worker 흐름(`ensure_cluster_manager_user`)이 Keystone 비밀번호 갱신과 DB 암호문 저장을 원자적으로 재수행하도록 복구했다. 최종 DB 상태를 재조회하여 `project_manager_credentials`에 `ed38d6d012f84367acf98575048e6cb6` (user_id `fecd919c72aa49bd80da28a502a065b0`) 1행이 올바르게 보존되어 있음을 확인했다.
- **검증 중 발생한 간헐적 Afterglow 503 증거**: 검증 도중 Afterglow 로그인 및 admin API에서 간헐적 503이 발생한 같은 시각의 `afterglow_backend` 로그에는 `_has_system_admin_role`이 외부 공용 주소 `https://keystone.dmslab.re.kr:443`으로 role assignments를 조회하다 `HTTPSConnectionPool ... Read timed out (read timeout=15.0)` 및 `The handshake operation timed out`에 걸린 기록이 반복됐다. 이는 해당 503의 가장 구체적인 관찰 증거지만 access-log 요청과 exception을 일대일 correlation하지 않았으므로 유일 원인으로 단정하지 않는다. Drover의 내부 tenant-manager 인증 401과는 별개다.
- **Drover worker Redis WRONGTYPE 원인 규명**: 15:21Z controller1 health loop에서 발생한 `WRONGTYPE` 경고는 `drover.services.store:list_all_clusters`의 버그로 확인됐다: DB가 정상 동작 중이더라도 전체 클라우드에 활성 클러스터가 0개여서 DB 조회 결과가 빈 리스트(`clusters == []`)일 때, `if clusters:` 조건이 False가 되어 `# DB 미설정이거나 DB에 데이터 없으면 Redis fallback` 분기로 빠져 `_redis.list_all_clusters()`를 호출했다. 이때 Redis의 레거시 비-Set 키를 조회하며 `WRONGTYPE`이 발생했다. 클러스터가 존재할 때는 DB 결과를 직접 반환하므로 Redis를 호출하지 않는다. 후속 과제로 `list_all_clusters`에서 DB 정상 시 빈 리스트를 즉시 반환하도록 수정해야 한다.

### connection lifecycle hardening 및 최종 운영 pin (15:35–16:12Z)

- tenant manager 전환 후 장기 worker의 OpenStack connection 종료 경로를 추가 점검했다. `openstack.connection.Connection.close()`는 현재 SDK에서 executor/atexit만 정리하고 내부 `keystoneauth1.session.Session.session`의 `requests.Session` pool을 닫지 않는다. 운영 worker에서 manager connection을 warm-up 후 10회 열고 기존 `conn.close()`로 닫았을 때 process FD가 `14 → 34`로 20개 증가해 실제 socket leak을 재현했다.
- Drover `ab8b8d0` (`fix(worker): close tenant manager connections`)은 create/agent/HA, scale/delete/reconcile, health와 Stampede 경로에 `finally`/async context manager를 추가했다. 런타임 FD 증거로 SDK `close()`의 불충분함을 확인한 뒤 `ce1d9a6` (`fix(worker): close OpenStack HTTP sessions`)에서 공통 cleanup이 내부 requests session과 SDK connection을 모두 닫도록 수정했다. manager bootstrap/app credential/Barbican, callback, deletion, reconciliation 및 caller-token connection도 동일 cleanup을 사용한다.
- 최종 로컬 검증은 `625 passed, 3 skipped`; Ruff 통과. GitHub CI `34866094508`와 Docker Build & Push `34866094750`의 모든 job이 성공했다.
- 최종 운영 pin:
  - `drover-api@sha256:45ff231486ddae9a2aa4640c1fdc92a277634e9fa5159b409bdb090ae5b3e45c`
  - `drover-worker@sha256:ffe73e48291298c5af836f36fcf46529a8cc070ded1d305348a2ec42f77da038`
- 최종 배포 전 pin 백업: `/home/pieroot/afterglow-kolla-globals-before-drover-http-close-20260914T160645Z.yml` (mode 0600). `pull`/`reconfigure --tags drover --skip-tags haproxy`가 성공했고 controller1/2/3 모두 API `running|healthy|restarts=0`, Worker `running|restarts=0`, readiness database/redis/migrations/keystone 전부 `ok`였다. 공개 readiness도 `ok`였다.
- 최종 운영 worker에서 실제 DMSLAB manager connection으로 Nova 목록 조회를 반복한 steady-state FD smoke는 warm-up 뒤 10회 전후 `8 → 8` (`delta=0`)이었다.
- 첫 connection-cleanup 배포에서 병렬 digest 조회 결과의 라벨을 반대로 해석해 API/worker pin을 잠시 서로 바꿨다. 두 image가 같은 app source를 포함하고 Kolla가 실행 command를 지정해 컨테이너와 readiness는 정상 동작했지만, 최종 배포에서는 registry manifest를 image별로 다시 조회해 위의 올바른 API/worker digest mapping으로 교정했다.
- FD smoke의 첫 실행도 wrapper의 추가 인자 위치를 잘못 사용해 base64 payload 자체를 project ID로 전달했다. 이 진단 부작용으로 `afterglow-cluster-mgr-aW1wb3J0` Keystone user 1개가 생성됐고 MariaDB 저장은 project_id 길이 제한으로 rollback됐다. 사용자 ID/이름을 정확히 대조한 뒤 해당 user를 삭제하고 동일 이름 조회 결과 `remaining=0`을 확인했다. 이 두 번째 진단 부작용 처리에서는 실제 DMSLAB credential row와 manager 계정을 변경하지 않았다.

## Drover API → kubeconfig → Kubernetes 실운영 검증 (2026-09-15 02:53–03:35Z)

- 위 최종 digest pin을 유지한 채 운영에서 `kolla-ansible pull`과 `reconfigure -i /etc/kolla/multinode --configdir /etc/kolla --tags drover --skip-tags haproxy --become`를 다시 실행했다. 두 명령 모두 성공했고 공개 `/v1/health/ready`는 `database/redis/migrations/keystone` 전부 `ok`였다.
- Afterglow 프록시를 거치지 않고 DMSLAB 프로젝트 스코프 Keystone token으로 `https://drover.dmslab.re.kr/v1/clusters/async`를 직접 호출했다. 최종 검증 클러스터 `drover-prod-e2e-20260915-031310`의 ID는 `23c26fc7-608a-436a-bd17-82b6ac9de1ad`, operation ID는 `4af73242-8c9f-4ce0-a796-cbf40d6d08db`였다. SSE는 enqueue, server callback, agent provisioning 완료를 반환했고 상태는 `CREATING → PROVISIONING → ACTIVE`로 전환됐다.
- 최종 클러스터는 공유 external `public_provider` network에서 server `d643af82-4edb-47f2-99db-001d9ccb95f4` (`117.16.137.218`)와 agent `041d4811-6ce4-41ef-aa26-a46b2a6444df` (`117.16.137.222`)를 만들었다. 외부 kubeconfig 검증 동안에만 API CIDR을 `0.0.0.0/0`로 열었고 검증 직후 클러스터 전체를 삭제했다.
- `GET /v1/clusters/23c26fc7-608a-436a-bd17-82b6ac9de1ad/kubeconfig`는 200으로 2,957-byte YAML을 반환했다(SHA-256 `34253801923d59fd06f77ff36a5090da1e23d0f4f9c98d22688fafad71c959a5`). 이 파일을 mode 0600으로 저장해 로컬 `kubectl`로 사용했다. `/healthz`는 `ok`, server와 agent 두 node는 모두 `Ready`가 됐다. 임시 namespace와 ConfigMap을 생성하고 `data.result=ok`를 읽은 뒤 namespace를 정상 삭제해 Kubernetes API CRUD도 확인했다.
- **완전한 리소스 정상화는 실패했다.** 15분 동안 기다려도 `coredns`, `local-path-provisioner`, `metrics-server`가 Ready가 되지 않았고 반복 재시작했다. 로그에는 pod에서 Kubernetes service IP `10.43.0.1:443`로 접근할 때 `i/o timeout`이 반복됐다. 두 Nova node가 Ready이고 외부 API `/healthz`와 Drover health가 `HEALTHY`인데도 기본 system pods가 정상화되지 않으므로, 현재 Drover의 `ACTIVE`/health 판정은 클러스터 내부 service-network readiness를 보장하지 않는다.
- 사전 파라미터 확인 중 생성한 private `Default` network 클러스터 `ab4f34cb-0ceb-46e9-b195-40e763959aab`와 API CIDR이 제한된 external network 클러스터 `ef2fa68a-45b9-4acc-9eb4-ed389934a64d`도 각각 Drover delete SSE로 삭제했다. 세 검증 클러스터 삭제 후 `drover-prod-e2e` 이름 prefix의 Nova server, Cinder volume, Neutron security group 조회 결과는 모두 빈 목록이고 DMSLAB 활성 Drover cluster 수도 0이다.

결론: 운영 배포, Keystone 프로젝트 인증, Drover 직접 create/delete, kubeconfig 발급, 외부 `kubectl` 접속, 두 node join 및 API object CRUD는 통과했다. 기본 K3s system workload readiness는 통과하지 못했으므로 “정상 클러스터 리소스” 기준으로는 부분 성공이며, service-network(`10.43.0.1`) 연결 장애와 너무 이른 `ACTIVE`/`HEALTHY` 판정을 별도 수정·재검증해야 한다.
