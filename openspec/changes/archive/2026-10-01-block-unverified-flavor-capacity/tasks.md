## Implementation Tasks

- [x] 1. 로컬 DMSLAB의 원인(AZ 정책 미설정 → capacity 미평가 → CPU fail-open)을 실제 로그·DB·Placement로 확인한다. 승인된 두 AZ 정책을 `nova`로 저장하고, AZ를 생략한 목록에서 `cpu.16c_128g`가 `insufficient`로 막히는지 확인한다. (화면 스냅샷 시각 01:13:24 = backend 로그 `ResourcePolicyValidationError`. 정책 저장 전 AZ 생략: CPU 21개 모두 unavailable/선택 가능, 생성 사전검증 거부. 정책 저장 후: available 20·insufficient 1(`cpu.16c_128g`, `host_capacity_insufficient`), 사전검증 `nova/nova`. Placement 13 root 중 16 vCPU/128 GiB 적합 0)
- [x] 2. backend 목록·admission이 모든 `unavailable` capacity를 차단하도록 바꾸고 회귀 테스트를 갱신한다. (`flavor_eligibility.evaluate_project_flavors`: `unavailable`도 flavor 종류와 무관하게 `host_capacity_unavailable`)
- [x] 3. wizard 분류·문구에서 미확인 허용 경로를 제거하고 frontend 테스트를 갱신한다. (`flavorCreateBlock`: snapshot 없음/`unavailable`은 blocker가 없어도 `unchecked`; 허용 문구 3곳 제거)
- [x] 4. API·ARCHITECTURE·DESIGN·CHANGELOG를 새 계약으로 갱신한다.
- [x] 5. exact selector·관련 target, 이미지 빌드·로컬 배포와 실제 backend/브라우저 smoke를 실행한다.
- [x] 6. architecture snapshot을 검증하고 change를 archive한다.

## Verification Evidence

- 수정 전 `backend:tests/test_flavor_capacity_admission.py`: 6 failed/16 passed. CPU+`unavailable` 3개 생성 endpoint가 mock Nova `create_server`까지 진행했고, 목록 CPU 행과 기본 AZ 정책 누락 목록이 선택 가능했다. 수정 후 22 passed.
- frontend exact(`SelectFlavor`, `vmCreateStoreLoad`, `vmCreateStoreRealClient`) 3 files/43 passed. `npm run check` 2,127 files 0 errors/0 warnings. 변경 backend 2 files Ruff check/format 통과.
- `instances` target: backend 377 passed, frontend 15 files/97 passed. `k3s` target: backend 16, frontend 6 passed. `npm run test:unit`: JS 102/26/13 passed(PowerShell 15 skipped), backend 3,399, frontend 275 files/1,857, scripts 9 passed. `npm run test:contract` 136 passed.
- 미실행: `test:functional`과 이를 포함하는 `test:gate`. 이 변경은 datastore 경로를 바꾸지 않으며, 고정 `afterglow-test` Compose project를 동시 세션이 공유하고 있어 기동·종료로 간섭할 수 있다. 전체 gate 통과로 기록하지 않는다.
- 로컬 배포: `docker compose --env-file .env --project-name afterglow-local-services -f docker-compose.dev.yml build backend frontend` 후 `up --no-deps --no-build --wait`. config hash가 전후 동일했다(backend `97995e20…`, frontend `9711911b…`). 새 image는 backend `e61ccbd8…`, frontend `fb5ddbfb…`이며 healthy다. container의 `flavor_eligibility.py` SHA-256 `91a4438c…`는 source와 같다. 배포된 frontend bundle에는 새 상태 문구가 있고 이전 허용 문구 2종은 0개다. amd64 backend/frontend는 buildx로 빌드해 에뮬레이션 실행(`x86_64`/`x64`, 동일 source hash·bundle 문구)한 뒤 QA tag를 삭제했다.
- 실제 backend(새 container·실제 Nova/Placement, DMSLAB 78 flavor, 정책 저장 후 AZ 생략): 선택 가능 22(CPU 20), 상태 available 38/insufficient 34/unavailable 6(GTX TITAN X, 선택 불가). admission은 `cpu.16c_128g` 409, `cpu.16c_64g`·`cpu.2c_2g` 통과. 평가 프로세스에서만 운영자 연결 장애를 모의하면 unavailable 78/선택 0이고 CPU admission은 503 `host_capacity_unavailable`이다.
- 실제 frontend(localhost:3080) wizard: 합성 identity와 위 실제 backend JSON을 사용했다. 정책 저장 상태는 `생성 가능 (22)`/`생성 불가 (56)`이며 `cpu.16c_128g`는 `한 호스트에 CPU·RAM 여유 없음`이다. 장애 JSON은 `생성 가능 (0)`/`생성 불가 (78)`이며 CPU 10행이 비활성 `호스트 용량 확인 불가`이고 다음 단계도 비활성이다. 390/767/768/1023/1024/1440px에서 document·panel·list·row overflow 0. 실제 사용자 로그인·VM 생성·운영 배포는 하지 않았다.
- Architecture: working `python3 scripts/check_architecture.py` 통과(source_sha256=`1894b4f100df3c4d27f50cae11141712aa6b6f3fd17c49b676482f53de411da4`, 2,148 files). 공유 review block은 다른 세션이 2026-10-01T17:03:50Z에 이 변경의 source 편집 이후 working tree로 stamp한 것이며 덮어쓰지 않았다. 실제 index `--staged` 통과(`8d4a6811…`, 2,120 files). 검사 전후 ARCHITECTURE.md(`317e42d6…`)와 `.git/index`(`31ec7a87…`) hash 동일. 실제 committer가 staged 범위로 다시 stamp해야 한다.
- 남은 위험: 운영자 자격증명·Placement 장애나 AZ 정책 누락 동안에는 wizard/API VM 생성이 모두 503이다(사용자 선택). NUMA 셀·GPU 근접성은 여전히 Nova가 최종 판단한다.
