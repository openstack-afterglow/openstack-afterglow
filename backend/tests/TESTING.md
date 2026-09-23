# 백엔드 테스트 실행 가이드

## 빠른 시작

```bash
cd backend

# 단위 테스트 (외부 네트워크·Docker·자격 증명 없음)
AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/ --ignore=tests/integration --ignore=tests/contracts -m "not db and not contract" -v

# 소비자 계약 테스트 (BFF/SDK/catalog/ingress 경계)
AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/contracts/ -m contract -v

# 국소 기능 테스트 (전용 일회용 Compose DB/캐시 환경: 3307, 5434, 6380)
npm run test:functional

# Live 테스트 (실제 OpenStack + Redis 필요)
AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/integration/ -v
```

> **주의**: 환경변수는 `AFTERGLOW_ALLOW_INSECURE=1` (코드 기준).

---

## 루트 국소 테스트 래퍼

루트에서 실행 가능한 국소 기능테스트 가이드는 [`../../docs/testing.md`](../../docs/testing.md) 를 기준으로 삼는다.

```bash
npm run test:list
npm run test:unit:backend
npm run test:contract
npm run test:functional
npm run test:functional -- --no-start
npm run test:functional -- --keep
npm run test:live
npm run test:gate
```

위 래퍼는 개발 중 빠른 반복 및 커밋 전 확정 게이트용이다.

---

## 4계층 테스트 구조 및 소유권 (4-Layer Framework)

```
backend/tests/
├── conftest.py                  # unit 기본: mock OpenStack + fakeredis, functional: real Redis
├── test_*.py                    # 단위 또는 db-marked local functional 테스트
├── test_endpoint_inventory.py  # 라우트 카탈로그 회귀 방지
├── contracts/                   # 추출 서비스 소비자 계약
│   ├── conftest.py              # contract marker 자동 적용
│   └── test_*.py
└── integration/                 # Live 테스트 (실제 OpenStack 자격 증명 기반)
    ├── conftest.py              # 실제 OpenStack + Redis fixture
    ├── credentials.toml.example # 크리덴셜 템플릿
    ├── credentials.py           # 크리덴셜 로더
    └── test_*.py                # 실제 API scenario
```

### 실패 소유권 (Failure Ownership)

- **Unit / Contract / Functional**: 실패 시 개발자 소유의 **확정 게이트 실패 (deterministic gate failure)**입니다. 원인을 수정한 뒤 `npm run test:gate`를 통과해야 커밋할 수 있습니다.
- **Live OpenStack**: Keystone 자격 증명 또는 네트워크 엔드포인트 도달성 미비 시, 실패가 아닌 **보고된 검증 공백 (reported verification gap)**으로 다룹니다.

---

## 전용 국소 기능테스트 환경 (Functional Ports & Lifecycle)

`npm run test:functional`은 일회용 전용 Compose 프로젝트에서 실제 DB 및 Redis 경계를 검증하고 성공·실패 모두에서 소유한 컨테이너와 volume을 정리합니다.

- **전용 포트**:
  - MariaDB: `3307` (`mysql+aiomysql://afterglow:dev@127.0.0.1:3307/afterglow_functional`)
  - PostgreSQL: `5434` (`postgresql://afterglow:dev@127.0.0.1:5434/afterglow_checkpoints`)
  - Redis: `6380` (`redis://127.0.0.1:6380/0`)
- **생주기 제어 옵션**:
  - `--no-start`: 이미 실행 중이거나 CI가 제공한 서비스를 재사용하며 teardown하지 않습니다.
  - `--keep`: 로컬 자동 기동 서비스를 디버깅용으로 유지합니다.

---

## 크리덴셜 설정 (Live 테스트)

### 방법 A: credentials.toml (로컬 개발)

```bash
cp tests/integration/credentials.toml.example tests/integration/credentials.toml
# 파일을 열어 admin 및 user 비밀번호 기입
vim tests/integration/credentials.toml
```

`credentials.toml` 파일은 `.gitignore` 에 포함되어 커밋되지 않는다.

### 방법 B: 환경변수 (CI/CD)

```bash
export AFTERGLOW_TEST_ADMIN_USERNAME=admin
export AFTERGLOW_TEST_ADMIN_PASSWORD=secret
export AFTERGLOW_TEST_ADMIN_PROJECT=admin
export AFTERGLOW_TEST_ADMIN_DOMAIN=Default

export AFTERGLOW_TEST_USER_USERNAME=testuser
export AFTERGLOW_TEST_USER_PASSWORD=secret
export AFTERGLOW_TEST_USER_PROJECT=test-project
export AFTERGLOW_TEST_USER_DOMAIN=Default
```

### 우선순위

환경변수 > `credentials.toml` > `afterglow.conf [openstack]`

admin 계정은 `afterglow.conf [openstack]`으로 폴백되므로 로컬에서 별도 설정 없이도 admin 테스트는 동작한다.
일반 유저 계정이 없으면 `user_client` 픽스처가 필요한 테스트는 자동으로 **skip** 된다.

### Cloud Shell live smoke 안전 게이트

`npm run test:live:cloud-shell`은 persistent home을 초기화하는 destructive scenario다. 전용 disposable `[user]` credential 외에는 사용하지 않는다.

```bash
CLOUD_SHELL_LIVE_USER_IDENTITY=cloud-shell-smoke \
CLOUD_SHELL_LIVE_CONFIRM=reset-disposable-home \
npm run test:live:cloud-shell
```

Identity 환경 변수는 실제 integration username과 정확히 일치해야 한다. Confirmation 값은 literal `reset-disposable-home`이다. 첫 workspace 조회에 active session 또는 기존 home이 있으면 test는 mutation 전에 실패하며 그 resource를 정리하지 않는다.

---

## 테스트 픽스처

### 단위 테스트 (`tests/conftest.py`)

| 픽스처 | 설명 |
|---|---|
| `client` | member role, `is_system_admin=False` |
| `admin_client` | admin+member role, `is_system_admin=True` |
| `non_admin_client` | member role, `is_system_admin=False` — 403 테스트용 |
| `mock_conn` | MagicMock OpenStack Connection |

### Live 테스트 (`tests/integration/conftest.py`)

| 픽스처 | 설명 |
|---|---|
| `client` | admin 계정 AsyncClient (기존 호환) |
| `admin_client` | admin 계정 AsyncClient |
| `user_client` | 일반 유저 AsyncClient (미설정 시 skip) |
| `anon_client` | 인증 없는 AsyncClient |
| `admin_auth_data` | admin 로그인 응답 (token, project_id 등) |
| `user_auth_data` | user 로그인 응답 |

---

## 선택적 서비스 테스트

Manila, Magnum, Zun, k3s 는 `afterglow.conf [services]` 에서 활성화되어야 라우터가 등록된다.
비활성화 상태에서 해당 테스트를 실행하면 **skip** 된다.

```bash
# manila 테스트 포함 실행
SERVICE_MANILA_ENABLED=true AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/integration/test_file_storage.py -v
```

---

## 권한 분리 테스트

admin 엔드포인트 77개에 대해 admin 계정(200)과 일반 유저(403)를 쌍으로 검증:

```bash
# 권한 분리 테스트만 실행
AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/integration/test_admin.py -v -k permission

# 단위 테스트에서 require_admin 전체 확인
AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/ --ignore=tests/integration -v -k requires_admin
```

---

## GitHub Actions CI 파이프라인 구조

GitHub Actions 워크플로 `.github/workflows/test.yml`은 `.github/workflows/docker-build.yml`이 reusable `Layered Tests`로 호출한다. 아래 잡 중 `test-live`를 제외한 모든 잡은 서로 `needs:` 없이 t=0에 병렬로 시작한다. 이미지 빌드는 `docker-build.yml`의 `changes`가 이 workflow 전체 결과(`needs: [test, test-pr]`)를 기다려 게이팅한다. push/dispatch는 `test`, PR은 `test-pr` caller가 호출한다.

- `version-check`: architecture freshness, 태그/버전 정렬, pure Node target-runner 오케스트레이션(`test:orchestration`: workflow 계약과 `scripts/ci/*` 단위 테스트 포함) 확인. 테스트 잡의 선행 조건이 아니며, 실제 자격 증명을 쓰는 `test-live`만 이 잡을 기다린다.
- `test-backend`: ruff와 backend unit. `test:unit:backend`는 `pytest-xdist -n 4 --dist worksteal`로 4 vCPU runner에 맞춰 실행한다(`-n auto` 금지). unit/contract 계층은 `tests/conftest.py`의 network guard로 non-loopback connect와 UDP `sendto`가 차단되며, 차단 기록에는 시도한 thread 이름이 붙는다.
- `test-cloud-shell`: Cloud Shell image build와 bootstrap smoke (`test:cloud-shell:image`)
- `test-contract`: 추출 서비스 소비자 계약과 uv-backed Kolla helper 계약
- `test-functional`: 실제 MariaDB/PostgreSQL/Redis를 쓰는 local functional (`test:functional -- --no-start`). 경로와 무관하게 항상 실행한다. service health check는 `docker-compose.dev.yml` `test` profile과 같은 2s interval / 5s timeout / 20 retries이다.
- `test-frontend`: SvelteKit unit을 `shard: [1, 2]` matrix로 나눠 실행한다.
  - `vitest run --shard=N/2`를 직접 호출한다. `npm run test:unit:frontend -- --shard`는 인자가 전달되지 않아 전체 스위트가 돈다.
  - `scripts/ci/verify-vitest-shard.js`가 JSON 보고서로 각 shard가 Vitest 분할이 배정하는 정확한 파일 수(247개면 124/123)를 실행했고 실패가 없는지 검증한다.
  - `run-with-file-log` node test는 shard 1에서만 실행한다.
- `detect-live`: `workflow_dispatch`에서 `run_live_openstack=true`로 명시한 경우에만 Keystone 토큰 POST 및 network endpoint 도달성 검사
- `test-live`: 수동 opt-in과 사전조건을 모두 충족한 경우에만 실제 OpenStack scenario (`test:live`) 실행; push/PR 기본 CI에서는 제외. `version-check`와 모든 테스트 잡(`test-cloud-shell` 포함)이 통과한 뒤에만 시작한다.

`docker-build.yml`의 PR 전용 `pr-dedup` 잡은 같은 저장소 `dev` 브랜치에서 온 PR이고 merge tree가 head tree와 같을 때만 `test-pr`(`Layered Tests (PR)`)를 건너뛴다. `test-pr`은 `github.event_name == 'pull_request'`에서만 실행되고, `changes`는 push/dispatch에서 `test`, PR에서 `test-pr` 결과만 본다. 같은 tree는 dev push 실행이 테스트한다. fork·dependabot·diverged PR과 판단 오류는 항상 테스트한다. 판단 규칙은 `scripts/ci/pr-dedup.js`와 그 단위·실제 git 테스트가 소유한다. 건너뛴 PR을 병합하기 전에는 dedup notice의 commit 링크에서 그 SHA의 dev push 실행이 green인지 확인한다. 이미지 target 감지, 발행 revision 기준, manifest 검증, stale re-run 가드는 root `ARCHITECTURE.md`의 `CI와 이미지 발행`을 참고한다.
