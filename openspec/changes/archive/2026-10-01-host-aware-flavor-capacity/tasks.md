## 1. 계약 및 구현

- [x] 1.1 기존 GPU alias·프로젝트 쿼터·Nova/Placement·생성/resize 소비자를 조사하고 고정 flavor 규격·fail-closed·tenant 식별자 비노출 계약을 확정한다.
- [x] 1.2 GPU·CPU·RAM의 같은 root compute 매핑, host state/AZ/resource/trait/aggregate/`cpu_info` 제약, Placement inventory/usage와 VCPU/PCPU 정책으로 읽기 전용 capacity 서비스를 구현한다. 단일 NUMA 셀은 호스트 합계+`numa_unverified`, 이름만 등록된 GPU audio function은 장치 이름으로 매핑한다.
- [x] 1.3 사용자·관리자 생성 목록과 sync/SSE admission에 capacity snapshot·409/503 제출 재검증을 연결한다.
- [x] 1.4 VM wizard의 현재 프로젝트 capacity 표시, refresh fence, 불가 선택 보존·진행 차단 및 제출 직전 uncached 재검증을 구현한다.

## 2. 검증

- [x] 2.1 same-host 교집합, allocation ratio/reserved/단위, host/AZ/trait/aggregate/alias·audio·`cpu_info`·NUMA 경계와 quota/resize 계약의 실제 SDK fixture 회귀를 실행한다. (focused backend 126 passed)
- [x] 2.2 사용자·관리자 목록 후 점유 변경과 sync/SSE mutation 이전 차단 회귀를 실행한다. (admission pytest. 실제 ASGI→openstacksdk→합성 Nova/Placement에서 live 3090 Ti 형태가 세 endpoint 모두 admission 통과→점유 후 409→Placement 장애 503, Cinder/Nova 생성 0)
- [x] 2.3 frontend 동적 refresh·프로젝트 전환/폐기 fence·제출 재검증을 확인하고 instances target과 프로젝트 test gate를 실행한다. (frontend focused 29, instances target backend 364/frontend 64, check 0/0. `test:all`: JS 102/26/13 passed(PowerShell 15 skipped), backend 3,386, frontend 1,761, scripts 9, contract 136, functional 28 passed. `lint:backend` ruff check 통과, format check는 동시 세션의 미커밋 `app/main.py`·`app/services/layer_build.py`·`tests/test_logging_contract.py`만 실패. working `docs:check`는 무관한 동시 변경 때문에 stale이며 전체 gate 통과로 기록하지 않는다)
- [x] 2.4 실제 운영자 읽기 전용 평가와 실제 Chromium 사용자/관리자 wizard의 available→insufficient/unavailable 및 반응형 breakpoint smoke를 수행하고 fixture/live 증거를 구분한다. (live 79 flavor: 수정 전 unavailable 76 → 수정 후 available 39/insufficient 34/unavailable 6. Chromium 합성 origin: NUMA 안내 1440·390px, 점유 후 차단)
- [x] 2.5 운영 flavor 76/79개가 사용하는 `hw:numa_nodes=1`/`hw:mem_page_size=any`와 `<chip>-audio` companion alias로 인해 전부 503이 되는 회귀를 재현하고 수정한다.

## 3. 완료

- [x] 3.1 영향 API·DESIGN·CHANGELOG·ARCHITECTURE 문서를 갱신하고 현재 작업 범위의 architecture snapshot을 검증한다. (임시 index HEAD+변경 파일 36개 `--staged --stamp`/`--staged`: source_sha256=d72b92c69e333a61b8331306e0d136491fa6eed4a71b310dbf78e83b0edc5f0e, 2,123 files. 실제 `.git/index` SHA-256 전후 동일. 실제 commit은 실제 staged 범위로 다시 stamp/검증)
- [x] 3.2 운영 자원/설정 변경 없이 throwaway harness를 정리하고 검증 증거·운영 한계를 기록한 뒤 change를 archive한다. (smoke API/UI service·Chromium·/tmp harness 정리. 한계: NUMA 셀 미확인은 Nova 판단, GTX TITAN X는 Placement class 부재로 확인 불가, 운영 배포·실제 GPU VM 생성 미수행)

## 4. 리뷰 후속 (archive 후, 미커밋 상태에서 반영)

- [x] 4.1 capacity를 VM wizard opt-in(`capacity=create`)으로 바꿔 기본 `/api/v1/flavors`(K3s 모달·Drover prefetch)는 쿼터만 판정하고 운영자 연결을 만들지 않게 한다. K3s `[쿼터 초과]` label을 원복하고 `count>1`·resize는 capacity를 평가하지 않는다. (default-list/no-operator·count 회귀, k3s target 16/6)
- [x] 4.2 미확인 capacity는 GPU flavor만 차단(503/`host_capacity_unavailable`)하고 일반 flavor는 경고 후 Nova에 맡겨 운영자 인증·Placement 장애가 전체 VM 생성을 막지 않게 한다. 확인된 부족은 모든 flavor를 차단한다. (route·service 회귀)
- [x] 4.3 Placement는 flavor shape마다 한 번 조회하고 `provider_summaries`와 `max_unit`으로 같은 root에서 CPU/RAM을 맞추며, 표시값을 VM 하나의 한도(`min(잔여, max_unit)`)로 바꾼다. 등록되지 않은 class는 `unavailable`로 둔다(운영 Placement는 HTTP 400, 후보 없음은 `/resource_classes` 확인). (max_unit·unknown class 회귀)
- [x] 4.4 운영자 세션 재사용·snapshot 실패 시 폐기, 5초 명시적 요청 timeout·재시도 없음, 내부 15초 deadline/caller 20초 대기, 목록 10초 single-flight snapshot(실패 shape 포함), admission fresh를 적용한다. (session·single-flight·failed-shape·stall 회귀. 운영 79 flavor 27.0초/170회 → cold 4.4초/52회, 당시 warm 0.6초와 전체 catalog fresh 3.5초, 판정 동일. 3.5초는 단일 flavor admission이 아니었다.)
- [x] 4.5 wizard 자동 갱신은 선택·진행을 잠그지 않고 실패 시 경고만 표시한다. 수동·제출 갱신만 잠그며 서버 `refresh=true`는 수동에서만 보낸다. per-VM·NUMA/GPU 근접성·용량 미확인 문구를 적용한다. (frontend wizard/store 45, instances target 370/80, check 2,119 0/0)
- [x] 4.6 실제 FastAPI 앱(uvicorn·uvloop)+실제 openstacksdk+합성 Nova/Placement를 실제 Chromium wizard에 연결해 기준/점유/Placement 장애 상태 변화와 390·767·768·1023·1024·1440px 카드/표 overflow 없음을 확인한다. 나머지 화면 API는 합성이다.
- [x] 4.7 이 세션이 덮어쓴 Cloud Shell 세션의 `architecture-review` block을 원래 digest·시각으로 복원한다. 요약 뒷부분은 복구할 원문이 없어 유실 표시를 남긴다. 이후 stamp 검증은 임시 index에서만 수행하고 작업 트리 block은 보존한다.
- [x] 4.8 해당 시점 범위를 임시 index(HEAD+변경 파일)에서 `--staged --stamp`/`--staged`로 검증한다: source_sha256=ea4b9291274397e3ad09658770b6652633998d9f857ec949c41c22f431a6a05d, 2,123 files. 작업 트리의 공유 review block(Cloud Shell)은 그대로 두었고 실제 `.git/index`는 검증 전후 동일했다. 이 digest는 아래 4.10 이후 수정 전 증거다. 실제 commit은 실제 staged 범위로 다시 stamp해야 한다.
- [x] 4.9 최종 전체 실행: JS 102/26/13 passed(PowerShell 15 skipped), backend unit 3,393, contract 136, functional 28 passed. frontend는 1,764 tests passed, 266/271 files다. 실패한 5개 suite는 동시 세션의 미커밋 `frontend/src/lib/components/instance/NetworkSection.svelte`가 아직 없는 `./SecurityGroupUnion.svelte`를 import해 load 단계에서 멈춘 것이며 이번 변경 파일이 아니다. 따라서 `test:all`/`test:gate` 통과로 기록하지 않는다.
- [x] 4.10 사용자/관리자 store 테스트에서 selectFlavor의 자동 단계 진행 후 step 2로 돌아가 pending periodic round 중 Next 가능 상태를 확인한다. CPU-only/GPU 부족 문구를 카드·행·선택 경고·상세로 구분한다. (frontend exact 3 files 43 passed)
- [x] 4.11 일반 프로젝트의 public+허용 private catalog를 운영자 access 조회로 재구성해 평가 비용을 측정한다. private-heavy 61 flavor/17 shape: cold 3.64초/45회, warm 0.00초/0회, 전체 fresh n=6 min/median/max 2.77/2.90/3.00초/42회, 단일 GPU admission 0.43/0.45/0.47초/6회. public-only 18 flavor/1 shape fresh 0.75/0.77/0.82초/18회. endpoint 전체 목록·쿼터 지연과 tenant 로그인은 측정 범위 밖이다.
- [x] 4.12 token 발급 0.49–0.61초와 warm token services 0.14–0.22초를 분리한다. 15초 폴링이 10초 TTL을 넘는 비용과 내부 deadline/caller timeout의 차이를 문서화한다. 표본 6회로 p95를 주장하지 않고 추가 조회 병렬화는 적용하지 않는다.
- [x] 4.13 live 측정에서 발견한 동일 실패 shape의 flavor별/폴링별 traceback 반복을 제거한다. 실제 SDK 실패 fixture의 3회 폴링에서 HTTP 조회·단문 warning 한 번, TTL 후 정상 복구를 검증한다. (backend focused 133 passed, 변경 파일 Ruff check/format 통과)
- [x] 4.14 visibility-aware detector(width>0 && offsetParent!==null)로 실제 공용 SlidePanel+SelectFlavor+layout.css 격리 mount를 재검증한다. 가능한/불가 각 5행, 390 카드/767 표/768 카드/1023·1024·1440 표: 목록·실제 행·패널 overflow 없음, 390 screenshot 카드·CPU-only 문구 확인. 현재 전체 앱은 무관한 security-group export 불일치로 500이어서 이번 후속을 전체 앱 E2E로 기록하지 않는다. 소유 UI service·Chromium·throwaway script는 정리했다.
- [x] 4.15 후속 domain 검증은 instances backend 371/frontend 92, k3s 16/6 통과. 최신 Svelte check는 2,125 files 중 다른 세션의 `NetworkSection.test.ts` ByRoleOptions `exact` 타입 오류 13건(한 파일), warnings 0으로 실패했다. 해당 파일을 수정하지 않았고 최신 check/전체 gate 통과를 주장하지 않는다. pytest 밖 실제 SDK+합성 adapter smoke도 3회 폴링 unavailable·query/warning 각 1회·traceback 없음·TTL 후 available 복구를 실행했다. 공유 architecture stamp는 보존하며 실제 committer가 최신 staged 범위로 갱신해야 한다.
- [x] 4.16 후속 소스 수정 뒤 최신 작업 파일 36개+HEAD를 별도 임시 index에 넣어 별도 review root에서 실제 guard의 `--staged --stamp`/`--staged`를 통과시킨다. source_sha256=79a45202d4e6afab0e3c0ec326e9c91252d527858e838933256dd93e5ce22d5a, 2,123 files. 검증 중 작업 트리 ARCHITECTURE 원문 byte와 실제 index SHA-256(31ec7a875298c248869168667186bd94466f878c79f4903b7d2b85d183e051cf) 전후 동일. 공유 Cloud Shell review block은 수정하지 않았으며 실제 staged commit 범위의 최종 stamp를 대신하지 않는다.
