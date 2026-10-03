---
title: 국소 기능테스트 가이드
lang: ko
nav_order: 8
---

# 국소 기능테스트 가이드

## 원칙 및 4계층 테스트 계약

Afterglow 테스트 체계는 4개의 명확한 레이어 계약으로 구성됩니다.

1. **단위 테스트 (Unit)**: `npm run test:unit:backend`, `npm run test:unit:frontend`, `npm run test:unit`. 외부 네트워크·Docker·자격 증명 없이 실행되는 기본 격리 계층이며, `test:unit`은 테스트 오케스트레이터 회귀(workflow 계약과 `scripts/ci/*` 단위 테스트 포함)도 포함합니다. 백엔드 unit은 `pytest-xdist -n 4 --dist worksteal`로 병렬 실행하고, `backend/tests/_network_guard.py`의 network guard(`conftest.py`가 autouse로 등록)가 unit/contract 계층의 non-loopback connect·UDP `sendto`와 localhost 이외 호스트 이름의 DNS 조회(`socket.getaddrinfo`)를 차단하여 실패시킵니다. 로컬 `afterglow.conf` 유무로 결과가 달라지면 결함입니다. 다만 guard는 설정 파일 로딩을 격리하지 않으므로, 네트워크 호출 없이 설정값에만 의존하는 차이는 잡지 못합니다.
2. **소비자 계약 테스트 (Contract)**: `npm run test:contract`. Afterglow BFF 경로, SDK adapter, Keystone catalog/ingress, immutable SDK source 등 추출 서비스와의 소비자 경계를 검증합니다 (`backend/tests/contracts/`).
3. **국소 기능 테스트 (Functional)**: `npm run test:functional`. `docker-compose.dev.yml`의 `test` profile을 전용 project에서 실행합니다(MariaDB 3307, PostgreSQL 5434, Redis 6380). 실제 persistence/cache 경계를 사용하고 OpenStack·추출 서비스는 fake로 유지합니다.
4. **실제 환경 테스트 (Live OpenStack)**: `npm run test:live` (`live:{auth,admin,compute,network,storage,layers}`). 실제 Keystone 인증 및 OpenStack 서비스 API 통합을 검증합니다.

### 독립 서비스 실제 로직 검증 (Service-real)

4계층 기본 게이트와 별도로 **현재 서비스 API/worker를 로컬 또는 Docker에서 실행한 HTTP 검증**을 수행합니다. `test:lumen`, `test:waygate`, `test:palimpsest`는 Afterglow 소비자/BFF 계약이며 서비스 실행 증거가 아닙니다. `test:functional`도 실제 DB/cache에 연결하지만 추출 서비스는 fake입니다. Synthetic browser는 UI 경계만 증명합니다.

```bash
# 기존 dev manifest/project/volume/key를 보존하며 선택한 source만 빌드·기동
# 선택하지 않은 Drover의 service project나 Waygate callback은 요구하지 않음
npm run services:up -- --only lumen,palimpsest

# 로컬 프로세스, Docker 또는 별도 테스트 endpoint에 직접 연결
export LUMEN_API_BASE_URL='http://127.0.0.1:8012/v1'
export LUMEN_API_KEY='<scoped-lumen-api-key>'
npm run services:verify -- lumen                 # 인증 조회만; acceptance 아님
export LUMEN_SMOKE_MODEL_ID='<active-text-model>'
npm run services:verify -- lumen --exercise      # provider 실행·비용 명시 opt-in

# Waygate/Hub는 Afterglow JWT가 아닌 실제 Keystone token 사용
export PALIMPSEST_API_BASE_URL='http://127.0.0.1:8020/v1'
export PALIMPSEST_SMOKE_TOKEN='<project-scoped-keystone-token>'
export PALIMPSEST_SMOKE_BLOB='/path/to/unique-layer.sqsh'
export PALIMPSEST_SMOKE_BUNDLE=1                 # 선택: OCI bundle도 검증
npm run services:verify -- palimpsest --exercise
```

CLI는 Docker·전체 Afterglow 설정·Drover·원격 dashboard를 사전 조건으로 삼지 않습니다. `*_API_BASE_URL`은 origin 또는 `/v1` base이며 redirect/catalog/provider fallback을 허용하지 않습니다. Secret은 환경변수로만 받고 출력·파일 저장하지 않습니다. 환경변수를 echo하거나 shell tracing으로 노출하지 않습니다. 필요 시 `<SERVICE>_SMOKE_PROJECT_ID`로 허용된 project를 명시합니다. Lumen은 `LUMEN_API_KEY` 대신 `LUMEN_SMOKE_TOKEN`을 사용할 수 있지만 둘을 함께 받지 않습니다.

| 서비스 | `--exercise`의 실제 HTTP 시나리오 | 사전 조건·미검증 경계 |
|---|---|---|
| Lumen | native temporary admission/idempotency → worker completed → 연속 journal/text → canonical history·run 귀속 token ledger 대조 | 활성 text model, completion·models·usage 읽기 권한. Journal/ledger는 서비스 retention에 남으며 실패한 비종료 run은 cancel한다. 실제 provider key 또는 서비스 소유 system stack의 fake provider를 구분하여 보고한다. Media·외부 provider 진위는 자동 증명하지 않는다. |
| Waygate | client 발급·다운로드/config/key/IP → PATCH 설정·key 보존 → passphrase-encrypted export/import → 생성 client 삭제·404·server defaults/network 보존 | `WAYGATE_SMOKE_TOKEN`, `WAYGATE_SMOKE_SERVER_ID`, `WAYGATE_SMOKE_IMPORT_SERVER_ID`. 같은 project의 **서로 다른 ACTIVE·등록된·client가 없는 전용 disposable server 두 개**가 필요하다. VM을 생성하거나 callback/auth를 우회하지 않는다. VM callback·VPN data plane은 별도다. |
| Palimpsest Hub | 실제 SquashFS byte SHA-256 → 다중 offset PATCH → finalize/단일 root 계보 → blob bytes/hash 대조 → 선택 OCI tar 참조·hash 대조 → 소유 upload/catalogue 삭제·404 | 실제 고유 `.sqsh`, 쓰기 가능한 Hub store, project-scoped Keystone token과 system-admin 삭제 권한. 기존/shared digest는 거부하며 무해한 invalid-digest DELETE로 정리 권한을 선확인한다. CAS 물리 byte는 지연 GC 대상이며 GC·다중 계보·bundle import·KVM/OpenStack build/consume는 미검증이다. |

Waygate는 현재 API/worker startup에서도 VM-reachable callback 설정을 요구합니다. Client control 시나리오가 callback을 호출하지 않는다는 사실과 callback 없이 서비스를 시작할 수 있다는 주장은 다릅니다. `--only lumen,palimpsest`와 외부의 이미 실행된 Waygate endpoint 연결은 이 전제를 분리하지만 production guard는 바꾸지 않습니다.

서비스 로직 변경은 이 경로 또는 서비스 소유 system runner로 **변경한 동작을 실제 실행**합니다. 보고에는 API/DB/cache/worker/crypto/blob와 모의 identity/provider/cloud를 따로 적습니다. 필수 자격·model·ready server·artifact가 없으면 검증 공백이며 read-only 성공으로 승격하지 않습니다. 사전 조건 충족 뒤 assertion·정리 실패는 실패로 종료합니다.

### 실패 소유권 (Failure Ownership)

- **단위 / 계약 / 국소 기능 테스트**: 실패 시 작성자/개발자 소유의 확정 게이트 실패(deterministic gate failure)입니다. 원인을 반드시 수정해야 합니다.
- **Service-real / 실제 환경 테스트 (Live OpenStack)**: 필수 자격 증명·엔드포인트·model·ready server·artifact가 없으면 **보고된 검증 공백(reported verification gap)**입니다. 사전조건이 충족된 뒤 발생한 assertion/resource cleanup 실패는 실제 결함으로 처리합니다.

### 검증 진행 순서

개발 루프 및 사전 검증은 다음 순서로 수행합니다:
1. **정확한 경로 (Exact selector)**: 변경한 파일/함수의 direct selector
2. **도메인 타깃 (Named target)**: 관련 도메인 named target (예: `auth`, `layers`, `live:auth`)
3. **교차 관심사 타깃 (Cross-cutting target)**: `npm run test:all` (`unit` + `contract` + `functional`)
4. **커밋/PR 확정 게이트 (Deterministic Commit Gate)**: `npm run test:gate` (`test:all` + `lint:backend`)

---

## 빠른 명령

```bash
npm run test:list
npm run test:target -- auth layers
npm run test:target -- --parallel instances
npm run test:target -- backend:tests/test_instances.py::test_delete_instance
npm run test:target -- frontend:src/lib/config/site.test.ts
npm run test:functional
npm run test:functional -- --no-start
npm run test:functional -- --keep
npm run test:live
npm run test:target -- live:auth
npm run test:gate
```

---

## 일회용 국소 기능테스트 환경 (Functional Lifecycle & Ports)

`npm run test:functional`은 `docker-compose.dev.yml`의 `mariadb`, `postgres`, `test-redis`만 기본 `afterglow-test` project에서 자동 기동합니다. 별도 test manifest는 없습니다. Cloud 자격 증명이나 형제 소스 checkout 없이 실행할 수 있으며 runner는 자동 `.env` 보간을 사용하지 않습니다. 성공·실패 모두에서 이 세 컨테이너만 종료하고 tmpfs 데이터를 폐기합니다. 개발 앱·named volume·orphan을 삭제하지 않습니다. 이 계층은 일반 단위 테스트의 fakeredis fixture를 끄고 실제 Redis 연결을 검증합니다.

- **전용 포트**:
  - MariaDB: `3307` (`mysql+aiomysql://afterglow:dev@127.0.0.1:3307/afterglow_functional`)
  - PostgreSQL: `5434` (`postgresql://afterglow:dev@127.0.0.1:5434/afterglow_checkpoints`)
  - Redis: `6380` (`redis://127.0.0.1:6380/0`)
- **생주기 제어 옵션**:
  - `--no-start`: 이미 실행 중이거나 CI가 제공한 DB/캐시 서비스를 재사용하고 소유권을 가져가지 않습니다. 다른 주소는 `AFTERGLOW_TEST_DATABASE_URL`, `AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL`, `REDIS_URL`로 지정합니다.
  - `--keep`: 자동 기동한 컨테이너를 실행 상태로 유지해 디버깅합니다. 데이터는 tmpfs이므로 컨테이너 중지 시 사라집니다. 정리는 아래의 service-scoped 명령을 사용합니다.

```bash
# 자격 증명 없이 test profile만 수동 실행 (기본 앱을 함께 시작하지 않음)
docker compose --env-file /dev/null -f docker-compose.dev.yml -p afterglow-test --profile test up -d --wait --no-deps mariadb postgres test-redis
npm run test:functional -- --no-start
docker compose --env-file /dev/null -f docker-compose.dev.yml -p afterglow-test --profile test down mariadb postgres test-redis
```

일반 개발 앱은 기존처럼 `npm run services:up`으로 private 설정·키를 검증하고 시작합니다. 테스트 profile만을 위해 비밀값을 채우거나 insecure 모드로 실행하지 않습니다. 명시적인 service 목록 없이 `--profile test up`을 사용하면 기본 앱까지 선택되므로 테스트 단독 실행에는 위 명령 또는 npm runner를 사용합니다.

---

## 타깃 선택표

| 타깃 | 설명 및 사용 시점 |
|---|---|
| `auth` | 로그인/로그아웃, 토큰, 세션, site-config 인증 경로를 건드렸을 때 |
| `access` | 관리자 전용 체크, owner check, IDOR/BOLA, audit prefix, legacy v1 계약을 바꿨을 때 |
| `config` | afterglow.conf/config, K8s 설정 생성, 캐시 설정, 프론트엔드 런타임 config를 바꿨을 때 |
| `crypto` | k3s 암호화 또는 키 파생 로직을 바꿨을 때 |
| `contracts` | 추출 서비스 BFF/SDK/catalog/ingress 소비자 계약을 독립적으로 확인할 때 (`npm run test:contract`) |
| `db` | local functional DB selector. 보통 환경·teardown까지 소유하는 `npm run test:functional`을 사용합니다. |
| `instances` | Nova 인스턴스 API, 생성용 flavor 쿼터·same-host GPU/CPU/RAM capacity/admission, wizard refresh·제출 fence, 메타데이터/메트릭/헬스, 인스턴스 UI를 바꿨을 때 |
| `storage` | Cinder/Manila/Swift 스토리지 API 또는 스토리지 UI를 바꿨을 때 |
| `layers` | admin libraries, squashfs, union layer build/consume 플로우를 바꿨을 때. Dockerfile 편집기의 FROM 해석·lint 상호작용과 후보 표시도 포함합니다. |
| `k3s` | k3s API, cloud-init, 보안, 플러그인, nodegroup 테스트를 건드렸을 때 |
| `workers` | worker runtime, notion worker 템플릿/동작을 바꿨을 때 |
| `design` | 디자인 시스템 규칙, raw visual debt guardrail을 확인할 때 (`npm run test:frontend:design`) |
| `live:{auth,admin,compute,network,storage,layers}` | 실제 OpenStack 자격 증명이 필요한 live 통합 슬라이스를 확인할 때 |

---

## 직접 pytest / Vitest 실행

### 백엔드 직접 pytest 실행

```bash
npm run test:target -- backend:tests/test_instances.py::test_delete_instance
```

백엔드와 프론트엔드 step이 함께 있는 target(`instances`, `auth`, `config` 등)은 `--parallel`을 붙이면 backend lane과 frontend lane을 동시에 실행합니다.

```bash
npm run test:target -- --parallel instances
```

직접 pytest 호출:

```bash
cd backend && AFTERGLOW_ALLOW_INSECURE=1 uv run python -m pytest tests/test_instances.py::test_delete_instance -v
```

### 프론트엔드 직접 Vitest 실행

```bash
npm run test:target -- frontend:src/routes/__tests__/logout-flow.test.ts
```

직접 Vitest 호출:

```bash
cd frontend && npm test -- src/routes/__tests__/logout-flow.test.ts
```

CI의 frontend 잡은 파일 단위 2-way shard로 실행합니다. 샤드는 래퍼가 아니라 vitest를 직접 호출해야 합니다. `npm run test:unit:frontend -- --shard=1/2`는 내부 npm이 인자를 전달하지 않아 전체 스위트를 실행합니다.

```bash
cd frontend && ./node_modules/.bin/vitest run --shard=1/2 --reporter=json --outputFile.json=/tmp/shard-1.json
node ../scripts/ci/verify-vitest-shard.js --report /tmp/shard-1.json --shard 1/2 --root .
```

---

## 에이전트 및 엔드포인트/보안 개발 가이드

1. **엔드포인트 테스트 작성 의무**: 백엔드 엔드포인트를 수정/추가하면 반드시 `backend/tests/` pytest를 함께 작성합니다. 테스트 없는 엔드포인트는 미완료로 간주됩니다.
2. **보안 가이드라인 검증**:
   - 인증/권한, owner check, IDOR guard, admin dependency(`require_admin`)를 건드린 경우 `auth` 또는 `access` 타깃을 반드시 포함합니다.
   - cloud-init 템플릿보간, shell 쿼팅, Pydantic validation 변경 시 관련 단위/기능 테스트를 함께 실행합니다.
3. **커밋 전 확정 게이트**: 커밋 또는 푸시 전 반드시 `npm run test:gate` 명령을 실행하여 `test:all`과 `lint:backend` 통과를 확인합니다.
