## Review and Candidate

- [x] 1. 다섯 기본 checkout의 현재 source와 version consumer를 검토하고 확인된 release blocker를 수정한다. Waygate framework 호환 갱신과 실제 재현 worker 종료, Afterglow dependency floor와 안전 SVG label 수정은 별도 change/evidence로 추적한다. 운영 blocker는 rollout 단계에 남긴다.
- [x] 2. 각 저장소의 필수 gate, architecture guard, 실제 실행 smoke와 secret scan을 완료한다. 최신 Afterglow full gate와 Waygate framework/signal gates는 아래 증거를 따른다; live auth/production은 rollout acceptance에 따로 남긴다.
- [x] 3. 모든 검토한 변경을 사용자 파일 보존 하에 dev에 커밋했다. 최신 source는 Afterglow bab526fb, Waygate a6e7dfd, Drover8afc434e, Lumen c168b8a5, Palimpsest locald0bda353이며 presentation/pf.md는 제외·보존한다.
- [ ] 4. 모든 dev 커밋을 정상 push한다. Afterglow/Waygate/Drover/Lumen은 원격 dev에 반영됐으나 Palimpsest 정상 push는 GH013·required checks6개로 차단됐다. 보호 규칙·별도 ref·native approval을 우회하지 않는다.
- [x] 5. 대상 기본 checkout은 모두 dev다. 검토한 source를 dev에 직접 커밋했으므로 중복 branch merge는 필요하지 않다; owner dev→main 통합과 구분한다.

## Main and Publication

- [ ] 6. pie_root가 모든 대상 dev→main PR 생성 및 merge를 수행한다. 이 세션은 로컬 제안 본문만 준비한다.
- [ ] 7. main 통합된 프로젝트별 불변 버전 tag를 생성·push한다.
- [ ] 8. 프로젝트별 release/wheel/image 게시 결과와 불변 ref를 검증한다. 기존 Lumen 0.5.0은 재게시하지 않는다.

## Kolla Rollout

- [ ] 9. 실제 operator package pins·inventory·복구 지점을 검증한 뒤 정확한 릴리즈의 `uv sync`를 실행한다.
- [ ] 10. 사용자 선택인 기존 inventory로 `kolla-ansible genconfig -i multinode`를 실행한다.
- [ ] 11. 성공한 genconfig 다음 `kolla-ansible reconfigure -i multinode`를 실행한다.
- [ ] 12. 서비스 health와 실제 배포 버전·authenticated boundary를 검증하고 완료된 범위만 archive한다.

## Operational Monitoring

- [ ] 13. 진행 중인 전체 배치의 완료·실패·보호 규칙 blocker를 모니터링한다.
- [ ] 14. 전체 문제 처리와 릴리즈 선행 조건 완료 후에만 배포한다.
- [ ] 15. 배포 전후 VIP·ProxySQL·HAProxy의 실제 동작을 확인하고 발견한 문제를 처리한다.
- [ ] 16. 배포 전후 나머지 활성 서비스, 특히 Keystone의 인증·catalog·downstream 읽기 동작을 확인하고 발견한 문제를 처리한다.
- [x] 17. 사용자가 점검 중인 기존 WireGuard 서버 keepalive 설정과 네트워크를 보존했다. 이 세션은 관련 설정·네트워크를 변경하지 않았다.


## Evidence and Boundaries

- Main PR 생성/편집과 merge는 pie_root 소유다. 태그·운영 배포를 이 선행 조건 전에 수행하지 않는다.
- 배포 호스트 inventory를 확인했고 `multimode`가 없으며 사용자가 기존 `multinode`로 실행하도록 선택했다. inventory 파일·대상 그룹을 변경하지 않는다.
- `/etc/kolla` 설치 조회: Kolla-Ansible 21.0.1.dev53, Drover 0.2.22, Lumen 0.2.2, Waygate 0.1.3, Palimpsest client 0.2.3. 현재 operator source는 서비스 `rev=dev`이며 릴리즈 pin promotion 전 uv sync를 수행하지 않았다.
- 각 gate/smoke/커밋의 결과는 완료 시 추가한다. 출판 또는 운영 성공은 관측한 경우만 기록한다.
- Afterglow review의 재현된 blocker 7개(PCI count 할당, aggregate CSV 일치, cache flight freshness, native JWT Hub rescope, key project assertion, 설정 CA TLS, drawer remount rescope)를 수정했다. 같은 identity 재로그인 후 이전 응답 적용도 failing-before regression으로 확인·수정했으며 동일 identity refresh는 허용했다.
- Focused backend: capacity/cache/identity/package/Hub proxy 274 passed. Frontend navigation: ProjectSelector/Sidebar 34 passed. 실제 390px Chromium synthetic identity에서 보류 rescope→drawer 닫기/다시 열기→동시 전환 잠김(POST 1회)→정확한 scope 적용/잠금 해제와 tutorial native package 링크 0·지원 VM 링크 유지·overflow 0을 관측했다. 실제 Keystone 로그인 증거는 아니다.
- Native boundary는 signed-JWT ASGI·legacy/export-ticket runtime에서 denial-before-exchange 및 기존 동작을 확인했고, actual loopback HTTPS에서 설정 CA200·다른/없는 CA503·os_insecure로 검증 우회 없음·key mismatch403·duplicate401을 확인했다(throwaway harness 제거).
- Root/backend/frontend/Cloud Shell/Helm/Kolla version consumer가 1.30.0으로 일치했다. 현재 release 범위 backend formatter 요구 13파일만 정리했다. 최종 `PWSH=<verified portable runtime> npm run test:gate` 완료: backend3523·frontend1896·contract141·DB functional28·Ruff/format530 files 통과, installer Node suite27 passed/Windows1 skipped. `npm run check && npm run build`:2130 files/0 errors/0 warnings·production build 통과. Gate working source_sha256=f44758f90d282a4de681e4861573ea7976b181bf94090a78ac8437ad16027c24(2165 files). 사용자 PPT 제외 후 정확한 publishable staged source를 별도로 stamp·검증했다:0582559077dc87344d6c76e461607ff24c01005c3fffb4a79fa2fac2993a9b88(2164 files). 보존된 untracked PPT로 working/staged source set이 다르며 precommit에는 staged guard를 사용한다. Gbrain CLI가 PATH에 없어 sync는 blocked.
- Drover dev8afc434e·Waygate dev29f28cdc는 정상 push/CI success. Palimpsest locald0bda353는 승인된 정상 dev push가 GH013의 required GitHub checks6개로 거부됐다. 보호 규칙·별도 ref·native KVM approval은 우회하지 않았다. Lumen dev는 기존 게시된0.5.0 기준이며 중복 tag/release를 수행하지 않았다.
- 공식 SHA-256을 검증한 portable PowerShell runtime으로 installer behavior 14 passed, 실제 Windows DPAPI/ACL 1 skipped를 확인했다. Windows 보안 acceptance를 macOS에서 대체하지 않았다. API/frontend/Notion worker/Cloud Shell canonical image의 amd64·arm64 build와 실제 architecture/runtime smoke를 완료했다. API는 x86_64/aarch64 import·PCI bound16, worker는 두 architecture의 crypto0.1.1, Cloud Shell은 두 architecture의 non-root/private bootstrap/CLI/persistent home을 검증했다.
- 격리 canonical Compose frontend(18729)의 실제 compiled Chromium에서 arm64와 amd64(x64 node runtime)를 각각 실행하고 명시적390×844 emulate 후 tutorial native service group/link0·overflow0을 확인했다. Source Chromium의 deferred project switch/remount proof와 구분한다. 이것은 운영 사용자·Keystone acceptance가 아니다. Secret scan은 synthetic `perplexity/sonar` model-name 1건의 확인된 false positive만 scratch baseline으로 제외한 뒤 staged1.39MB에서 추가 finding0이었다. 사용자 presentation과 `pf.md`는 파일을 보존하고 release commit에서 제외한다.
- 읽기 전용 production preflight는 `local://release-preflight-infra.md`, `local://release-preflight-openstack.md`, `local://release-preflight-keystone-canonical.md`에 보존했다. VIP는 C1 단일 owner, HAProxy syntax3노드 통과, 실제 ProxySQL SELECT/Galera Primary·Synced/Valkey replication·Sentinel quorum/RabbitMQ membership은 해당 관측 시점에 정상이다. 이미 외부 작업으로 복구된 Keystone·Drover readiness200은 재설정하지 않았다. 현재 operator token/catalog/inventory proof는 자격 증명 부재로 blocked이며 과거401 credential은 재시도하지 않았다.
- 운영 NO-GO: C3 원본 OpenSearch RBD image의 mapper entry 누락·미마운트, OpenSearch red·Dashboards migration/503, storage1의 L2/SSH/RGW/MON 접근 불가·Ceph33.051% objects degraded(5/8 OSD up/in), C2 exporter systemd14 restarts/collector contract errors, C2 Lumen worker heartbeat3711초 stale를 확인했다. C2 기존 SQL socket5개는 ProxySQL3노드 runtime processlist에 counterpart0이며 새 SQL/Redis probe는 성공했다. Stale SQL pool hypothesis는 inference이며 worker 처리 정상으로 표시하지 않는다. storage console·원본 datastore/saved-object backup·신규 operator auth 등 복구 선행 조건을 생략하지 않는다.
- C2 worker는10:30Z 새 read-only check에서 heartbeat4760초 stale·active_count0·nonterminal run0을 확인한 뒤 기존 `lumen_worker`만 restart했다. Container/image/config·HostConfig/mount hash를 동일하게 유지했고 신규 registration10:30:52·첫 heartbeat1초를 확인했다.10:42:44Z 후속 실제 read-only query에서도 C1/C2/C3 heartbeat 모두3초·accepting/capacity4·active0이었다. Native/provider 처리나 permanent SQL failover tolerance는 검증하지 않았다. `local://release-lumen-worker-recovery.md`에 관측과 한계를 보존했다. 다른 운영 mutation이나 WireGuard/keepalive/network 변경은 없다.
- Waygate inherited advisory5개의 source reachability와 metadata를 검토한 뒤 FastAPI0.136.3/Starlette1.3.1을 선택했다. Frozen API/worker를 aarch64/x86_64 canonical Compose의 real MariaDB/Redis·synthetic Keystone HTTP와 실행해 actual API/SDK, project/agent/admin auth, JSON/+json/null/zero, trusted/untrusted proxy, malformed Host/path normalization, safe INFO/DEBUG logging과120/1200 rate budget을 확인했다. Reproduced worker stop137/30s는 signal runner로 고쳐 두 architecture exit0/<1s와 SQL polling을 확인했다. Lease/retry·운영 ingress·cloud lifecycle는 바꾸거나 성공 주장하지 않는다. Default-branch alert closure는 main 통합 후 별도다.
- Drover 추가 실제linux/amd64 API/worker Dockerfile build·binary x86_64/version0.3.0·API live200/ready503(no dependencies)/auth401·worker25 real query polls/cleanSIGTERM0을 확인했다. Source110 copied tracked inputs parity와 owned resource cleanup을 검증했다. `local://release-drover-amd64-proof.md`의 로컬 cross-architecture proof이며 native hardware/운영 authenticated job success는 아니다.
- Afterglow dependency floor: PyJWT2.15.0/AnyIO4.14.2/urllib32.8.0/AsyncSSH2.24.0/pypdf6.19.0, frontend devalue5.9.3/DOMPurify3.4.16/smol-toml1.7.1/Vitest·coverage4.1.11. Backend API의 양 architecture real JWT/TLS/chunked HTTP/SSH/PDF harness를 통과했고 worker 설치 graph/import 뒤 canonical Compose에서 실제 DB/scheduler startup과 runtime-disabled Notion loop를 관측했다. Root OpenStack CLI10.0.0은 격리 Keystone HTTP의 endpoint list를 실제 요청해 통과했다. Operator local frozen sync·Kolla21.2.0 CLI만 확인했으며 operator에는 OpenStack CLI가 없고 운영 sync/배포로 해석하지 않는다. 기존 immutable role pins는 유지했다.
- Compiled frontend 양 architecture canonical Compose에서 Nodearm64/x64·APIhealth200·Notion DB/scheduler startup을 관측했다. SSR은 scratch TOML의 비기본 site 이름과 Δ/<safe>/& 문자열과 payload의 Unicode script escaping을 보존했다. Synthetic Chromium chat에서 table·KaTeX·code·SVG text label과 script/event/javascript URL rejection을 확인했다. Baseline/첫 patched image의 blank Mermaid label은 roothtmlLabels=false로 해결했다. 두 architecture390/767/768/1023/1024/1440px에서 label 유지·overflow0, settledmobile12px label의 viewport내 표시를 확인했다. 별도 변경을2026-10-02-fix-mermaid-svg-labels로 archive했다.
- 최신 security+renderer source의 fullgate(2026-10-02): orchestration106/Kolla26/installer27+Windows1skip/backend3523/frontend1896+runner9/contract141/DBfunctional28/Ruff+format530 통과. 처음 gate의 Mermaid initialize-options copy assertion은 새 옵션 때문에 실패했으며 source를 우회하지 않고 obsolete copy/call-count assertion만 제거했다; 실제 SVG sanitization test와 compiled label/XSS smoke는 유지했다. Frontendcheck2130files/0errors/0warnings·productionbuild도 통과. 사용자 PPT/pf.md는 로컬 exclude로 보존하여 최종 source review·제출 대상에서 제외했다.
- 최신 dev source normal push: Afterglow bab526fbbfecf263b1990452c5c26912cd7478f6와 Waygate a6e7dfd3f5f4745fcf6c9e059a0e4e9b66531e55. Working/staged architecture guards는 각각82a971531bbacd153cd8cd01e110b68c08890839b67d5f210e691b0354aad50f/2164files 및 f4a82dc0df31e3b3912156cc2ac004bca47ddf964ee67cf68ec11cf06c3751bc/114files, staged Gitleaks는76.21KB/56.12KB에서 finding0이었다. 해당 source SHA의 hosted Docker Build & Push CI37012250604/37012473229 모두 success를 관측했다. Afterglow backend/worker/frontend build·manifest job이 통과했고 양 architecture local build/실행 proof는 위 증거와 별개다. Opt-in live OpenStack은 skipped다. 이것은 dev CI/이미지 발행이며 안정 release·운영 배포가 아니다. 원격 default-branch alert58/5개는 dev push로 닫혔다고 주장하지 않는다.
- Waygate v0.1.4 태그에는 독립 `waygate/agent/waygate_agent.py`가 없다. `waygate/templates/waygate_agent.yaml.j2`의 embedded register/reconcile transport에서 application/json header를 확인했다. Current shared agent·Afterglow JSON client/BFF도 제공/보존하나 운영 prebuilt VM의 실제 agent는 이번 검증에서 읽지 않았다.
- 검증용 owned Chromium과 isolated security Compose API/worker/frontend/MariaDB/Redis/network를 종료·제거했고 해당 project의 volume0을 확인했다. 공유 afterglow-local-services·타 세션 project·운영 data/indices/credentials/WireGuard/keepalive는 보존했다. Release ecosystem은 보호된 통합·인증·원본 storage 복구·release/migration/rollout acceptance 때문에 archive하지 않는다.



