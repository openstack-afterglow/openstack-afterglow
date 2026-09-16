---
title: 국소 기능테스트 가이드
lang: ko
nav_order: 8
---

# 국소 기능테스트 가이드

## 원칙 및 4계층 테스트 계약

Afterglow 테스트 체계는 4개의 명확한 레이어 계약으로 구성됩니다.

1. **단위 테스트 (Unit)**: `npm run test:unit:backend`, `npm run test:unit:frontend`, `npm run test:unit`. 외부 네트워크·Docker·자격 증명 없이 실행되는 기본 격리 계층이며, `test:unit`은 테스트 오케스트레이터 회귀도 포함합니다.
2. **소비자 계약 테스트 (Contract)**: `npm run test:contract`. Afterglow BFF 경로, SDK adapter, Keystone catalog/ingress, immutable SDK source 등 추출 서비스와의 소비자 경계를 검증합니다 (`backend/tests/contracts/`).
3. **국소 기능 테스트 (Functional)**: `npm run test:functional`. `docker-compose.dev.yml`의 `test` profile을 전용 project에서 실행합니다(MariaDB 3307, PostgreSQL 5434, Redis 6380). 실제 persistence/cache 경계를 사용하고 OpenStack·추출 서비스는 fake로 유지합니다.
4. **실제 환경 테스트 (Live OpenStack)**: `npm run test:live` (`live:{auth,admin,compute,network,storage,layers}`). 실제 Keystone 인증 및 OpenStack 서비스 API 통합을 검증합니다.

### 실패 소유권 (Failure Ownership)

- **단위 / 계약 / 국소 기능 테스트**: 실패 시 작성자/개발자 소유의 확정 게이트 실패(deterministic gate failure)입니다. 원인을 반드시 수정해야 합니다.
- **실제 환경 테스트 (Live OpenStack)**: 필수 Keystone 자격 증명 또는 엔드포인트 도달성이 없으면 **보고된 검증 공백(reported verification gap)**입니다. 사전조건이 충족된 뒤 발생한 assertion/resource cleanup 실패는 실제 결함으로 처리합니다.

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
| `instances` | Nova 인스턴스 API, 메타데이터/메트릭/헬스, 인스턴스 UI를 바꿨을 때 |
| `storage` | Cinder/Manila/Swift 스토리지 API 또는 스토리지 UI를 바꿨을 때 |
| `layers` | admin libraries, squashfs, union layer build/consume 플로우를 바꿨을 때 |
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

---

## 에이전트 및 엔드포인트/보안 개발 가이드

1. **엔드포인트 테스트 작성 의무**: 백엔드 엔드포인트를 수정/추가하면 반드시 `backend/tests/` pytest를 함께 작성합니다. 테스트 없는 엔드포인트는 미완료로 간주됩니다.
2. **보안 가이드라인 검증**:
   - 인증/권한, owner check, IDOR guard, admin dependency(`require_admin`)를 건드린 경우 `auth` 또는 `access` 타깃을 반드시 포함합니다.
   - cloud-init 템플릿보간, shell 쿼팅, Pydantic validation 변경 시 관련 단위/기능 테스트를 함께 실행합니다.
3. **커밋 전 확정 게이트**: 커밋 또는 푸시 전 반드시 `npm run test:gate` 명령을 실행하여 `test:all`과 `lint:backend` 통과를 확인합니다.
