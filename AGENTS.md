# Afterglow — AI 에이전트 개발 규정

## 브랜치 전략

| 브랜치 | 용도 | 관리자 |
| --- | --- | --- |
| `main` | 프로덕션·배포 기준 | pie_root (수동 PR/머지) |
| `dev` | 개발·AI 작업 대상 | Katherine (AI 에이전트) |

반드시 현재 repo root에서 `git switch dev` 후 작업한다. `main`에 직접 커밋하지 않으며 PR과 `dev → main` 머지는 pie_root가 수행한다.

## 개발 워크플로우

인터랙티브 작업은 plan 모드에서 목표·범위·설계·완료 기준·제약을 먼저 확정한다. 하네스 작업은 승인된 태스크 명세를 입력으로 구현한다. 결과는 변경 파일, 검증 증거, 미완료 또는 위험을 정확히 보고한다. 새로운 기능이나 수정은 OpenSpec change를 먼저 만들고, 작업 중 checklist를 갱신하며, 완료 후 archive한다.

## Architecture maintenance

- 작업 시작 전에 root [`ARCHITECTURE.md`](ARCHITECTURE.md)를 읽는다. 이 문서는 현재 source의 정본이며 계획·roadmap·archive는 완료 증거가 아니다.
- code/config/schema/dependency/deploy/test를 변경하면 영향받는 `ARCHITECTURE.md` 본문과 상세 `docs/`를 같은 변경에서 갱신한다. 구조 영향이 없는 bugfix/refactor도 최신 review summary에 no-structure-impact 이유를 남긴다.
- 실제 source를 검토한 뒤 `python3 scripts/check_architecture.py --stamp --summary "<검토 요약>"`으로 stamp하고, 완료/commit 전 `python3 scripts/check_architecture.py --staged`를 통과시킨다. source와 문서가 충돌하면 source가 우선이다.
- 이 저장소의 문서 freshness guard는 표준 라이브러리와 Git만 사용하며 자동 stage/commit하지 않는다. hook이 설치되지 않은 환경에서도 위 명령을 직접 실행한다.

## Docker Compose 배포 계약

- `docker-compose.yml`은 독립 실행 가능한 최소 기본값이며 Afterglow `frontend`와 `backend`만 정의한다. Redis·DB·형제 서비스는 외부 설정을 사용한다. 소스 빌드나 개발/운영 보조 서비스를 이 파일에 추가하지 않는다.
- `docker-compose.dev.yml`은 현재 소스를 직접 빌드하는 개발 환경의 정본이다. Afterglow와 Lumen·Waygate·Drover(기존 Palimpsest 포함)를 로컬에서 실행하고 기본적으로 Compose service DNS로 통신한다. `SERVICE_*_INTERNAL_URL` 또는 private `[services]`로 목적지를 선택할 수 있고 명시적 빈 환경 변수는 카탈로그를 선택한다. 로컬 DB/cache/checkpointer·설정·키는 운영과 분리한다.
- `docker-compose.prod.yml`은 GitHub/GHCR에서 빌드한 이미지를 pull·동기화하여 실행하는 운영 환경의 정본이다. `build:` 및 소스 빌드 fallback을 금지한다. HAProxy가 앞단에서 운영 인증서로 TLS 종료와 LB를 담당한다. 형제 서비스는 기본적으로 인증된 OpenStack service catalog endpoint를 사용하며 명시적 환경 변수/TOML override는 신뢰된 HTTPS endpoint만 허용한다. 개발 HTTP URL, 자동 self-signed 인증서 및 insecure secret 우회를 금지한다.
- 세 파일은 각각 명시적인 `-f`로 선택한다. 개발은 `npm run services:up` 또는 준비된 private env와 `docker-compose.dev.yml`로 실행하며, implicit override나 별도의 installed-image 개발 경로를 두지 않는다.
- 기능테스트 datastore도 `docker-compose.dev.yml`의 `test` profile이 정본이며 별도 test manifest를 두지 않는다. 실행기는 기본 `afterglow-test` project에서 `mariadb/postgres/test-redis`만 명시적으로 기동·종료한다. 전용 loopback 3307/5434/6380과 tmpfs를 사용하고 개발 DB/cache·named volume·orphan을 삭제하지 않는다. 테스트만 실행할 때 cloud credential을 요구하거나 앱을 함께 시작하지 않는다.
- 모드 전환 시 기존 project·volume·암호화 키를 보존하고 다른 프로젝트를 중지/삭제하지 않는다. `down --volumes`와 광역 prune을 사용하지 않는다. Container health와 실제 authenticated dashboard/OpenStack 통신을 별도로 검증하고 upstream 오류를 성공으로 숨기지 않는다.

## 태스크 명세

하네스 입력은 다음 형식을 사용한다.

```text
[목표]
<한 문장 목표>

[현재 상태]
<관련 파일 경로와 현재 동작>

[요구 사항]
- <구체적 요구 사항 1>
- <구체적 요구 사항 2>

[제약]
- dev 브랜치에서만 작업
- <기타 제약>

[완료 기준]
- <확인 방법>
```

## 프로젝트와 기술 스택

```text
backend/              FastAPI + openstacksdk
  app/api/            OpenStack 서비스별 라우터
    k3s/              k3s 프로비저닝 API
    union/            Union Mount 레이어 API
  app/services/       OpenStack 클라이언트 래퍼
  app/models/         Pydantic/SQLAlchemy 모델
  app/templates/      cloud-init Jinja2 템플릿
  tests/              pytest
frontend/             SvelteKit + TypeScript + Tailwind CSS 4
  src/routes/         페이지 라우터
  src/lib/components/ UI 컴포넌트
  src/lib/utils/      유틸리티
  src/lib/stores/     Svelte stores
  src/lib/api/        API 클라이언트
openspec/             changes/<slug>/ 진행 기록과 archive/ 완료 기록
milestone.md          OpenSpec redirect stub; append 대상이 아님
```

| 영역 | 기술 |
| --- | --- |
| Backend | FastAPI 0.125, Python 3.12, openstacksdk 3.3 |
| Frontend | SvelteKit 2.50, Svelte 5, Tailwind CSS 4 |
| DB/Cache | SQLAlchemy 2.0 asyncio + asyncmy, Redis 7 |
| 특화 기능 | k3s, content-addressable OverlayFS layer, AES-256-GCM kubeconfig |
| 스토리지 | CephFS via Manila (layer-store-rw / layer-store-ro / manifest-store) |

## 프론트엔드 UI/UX 디자인 시스템

- UI/UX 또는 시각 변경 전 root `DESIGN.md`를 읽는다.
- 시각 변경 전 `DESIGN.md`의 `Layout & responsive hierarchy`까지 읽고, mobile (`<768px`), tablet (`768–1023px`), desktop (`≥1024px`)에서 navigation, columns, table/card fallback, overlay, action placement 계약을 구현·검증한다.
- 권위 순서는 `frontend/src/routes/layout.css` → `frontend/src/lib/design/tokens.ts` → `frontend/src/lib/components/ui` → feature composition이다.
- 새 색상, gradient, 상태 tone, motion, component pattern은 feature 구현 전에 `layout.css`, `tokens.ts`, UI primitive, tests, `DESIGN.md`에 먼저 정의한다.
- 새 frontend 파일에는 raw hex 또는 raw Tailwind palette 색상 클래스를 추가하지 않는다. Legacy 색상은 `legacyVisualDebt.ts` guardrail baseline에만 남긴다.
- status는 `StatusChip`/`Pill`, action은 `Button`, alert는 `Alert`, form은 `Field`/input primitives, table은 `TableShell`을 우선 사용한다.
- `DESIGN.md`의 scrim, layer, motion, reduced-motion 규칙을 따른다. 새 route/component은 token/primitive 확장 → primitive test → feature composition → visual-debt 검사 순으로 만든다.

## 개발, 테스트, OpenSpec

### 테스트 의무와 4계층 계약

- 백엔드 엔드포인트 구현에는 반드시 `backend/tests/` pytest를 함께 작성한다. 테스트 없는 endpoint는 미완료다.
- 계층별 테스트 계약:
  1. **단위 테스트 (Unit)**: `npm run test:unit:backend`, `npm run test:unit:frontend`, `npm run test:unit` (외부 네트워크·Docker·자격 증명 없음; 전체 unit은 오케스트레이터 회귀 포함). backend unit은 `pytest-xdist -n 4 --dist worksteal`로 실행하며 `backend/tests/conftest.py` network guard가 non-loopback connect를 실패시킨다.
  2. **소비자 계약 테스트 (Contract)**: `npm run test:contract` (`backend/tests/contracts/`의 BFF/SDK/catalog/ingress 경계)
  3. **국소 기능 테스트 (Functional)**: `npm run test:functional` (`docker-compose.dev.yml`의 실제 MariaDB/PostgreSQL/Redis test profile). 기본 전용 project 자동 기동·종료이며 데이터는 tmpfs다. 재사용은 `--no-start`, 실행 중 유지/디버깅은 `--keep`이고 중지 시 데이터는 사라진다.
  4. **실제 환경 테스트 (Live OpenStack)**: `npm run test:live` (`live:{auth,admin,compute,network,storage,layers}`). 자격 증명/도달성 미비는 검증 공백으로 보고하지만, 사전조건 충족 뒤의 테스트 실패는 결함으로 처리한다.
- 검증 진행 순서: exact selector → named target → cross-cutting target (`npm run test:all`).
- `npm run test:list`로 target을 확인한다.
- named target: `npm run test:target -- <target>`
- backend exact selector: `npm run test:target -- backend:tests/test_file.py::test_name`
- frontend exact selector: `npm run test:target -- frontend:src/path/file.test.ts`
- backend endpoint 변경은 관련 `backend/tests` selector 뒤 도메인 target(`auth`, `access`, `layers` 등)을 실행한다.

### 커밋 전 필수 검증

확정 게이트 명령 하나로 검증한다.

```bash
npm run test:gate
```

`test:gate` (`npm run test:all` + `npm run lint:backend`)가 성공한 경우에만 `git add <변경 파일>`, `git commit -m "type: 요약"`, `git push origin dev`를 진행한다. 실패하면 커밋하지 않고 원인을 수정한 뒤 다시 실행한다.
### OpenSpec

- 신규 작업: `openspec new change <slug> --schema rapid`, then `proposal.md`와 `tasks.md`를 채운다.
- 작업 중: `openspec/changes/<slug>/tasks.md`의 `[ ]`를 `[x]`로 갱신한다.
- 완료: `openspec archive <slug> --skip-specs --yes`. 이 프로젝트는 specs 레이어를 두지 않으며 기능 명세는 `docs/`와 `union.md`가 담당한다.
- 현황: `openspec list`. 작업 change는 `openspec/changes/`, 완료분은 `openspec/changes/archive/`.
- OpenSpec slash command/skill은 현재 checkout `.claude/` 아래의 machine-local asset이며 `.git/info/exclude`에 등록된다. 머신별 최초 한 번 `openspec init` 또는 `openspec update`를 실행한다.

### 설정 파일 동기화

`afterglow.conf`가 유일한 base configuration filename이다. 활성 override는 같은 디렉터리의 `afterglow.*.conf`와 선택적 `config.gpu.toml`이다. 예시 정본은 `afterglow.conf.example` 하나다.

`afterglow.conf` 항목 추가·변경 시 함께 갱신한다.

- `backend/app/config.py`: `_load_toml()` flat dict와 `Settings` 필드
- `generate_k8s.py`: 비밀은 `render_secret()`, 나머지는 `_render_toml_for_k8s()`
- `afterglow.conf.example`: 예시와 주석

`backend/app/config.py` 필드 추가·변경 시에도 `generate_k8s.py`와 `afterglow.conf.example`를 갱신한다. password, secret, token, key는 `render_secret()`로 secret.yaml 환경변수에 주입하며 ConfigMap에는 넣지 않는다.

### API 버전

모든 신규 라우터는 `/api/v1` 단독 mount다. 개별 `APIRouter()`에는 prefix를 두지 않고 `backend/app/main.py`에서 `prefix="/api/v1/<resource>"`로 mount한다. baked cloud-init 계약인 아래 세 endpoint만 legacy `/api` dual-mount를 유지한다.

- `POST /api/k3s/callback`
- `POST /api/instances/{id}/health/report`
- `POST /api/instances/{id}/credentials/rotate-cephx`

프론트엔드, 테스트, 배포 설정 모두 `/api/v1/...`을 사용한다. 소유권 검증 대상 리소스 endpoint는 `main.py` `_AUDIT_PREFIX_MAP`에 `/api/v1/<resource>`를 반드시 추가한다. `backend/tests/test_api_v1_legacy_compat.py`의 baked legacy contract는 삭제하거나 무력화하지 않는다.

### Palimpsest

레이어드 VM 작업은 아래 순서로 읽는다.

1. `docs/palimpsest.md`: 도메인 정의, 세대/용어, digest 규칙
2. `docs/squashfs-layer-pipeline.md`: 운영 중인 Palimpsest core pipeline
3. `union.md`: content-addressable, single-parent, 3-lock 불변성, GC 설계 원칙

`.sqsh` blob byte sha256을 digest로 사용한다. 재현은 기존 layer 재사용, 재빌드는 새 digest layer 추가다. 기존 layer를 덮어쓰지 않는다.

## CI 파이프라인 성능 규정

근거는 두 가지다. 하나는 2026-09 afterglow CI 실측이다(실행 40건, `Layered Tests` 크리티컬 패스 중앙값 143초, p90 155초). 다른 하나는 Linear의 CI 개편 사례다. CI를 바꾸는 모든 변경은 아래 규칙을 따른다. 여기에는 `.github/workflows/`의 모든 workflow와 `scripts/ci/`가 포함된다. 현재 구조는 `ARCHITECTURE.md`의 `CI와 이미지 발행`이 정본이다.

1. **측정 먼저, 추정 금지.**
   - CI를 바꾸기 전과 후에 최근 20회 이상 실행의 잡·스텝 시간을 `gh run list` / `gh api .../actions/runs/<id>/jobs`로 수집한다.
   - 크리티컬 패스(실행 생성부터 마지막 필수 잡 종료까지)의 중앙값과 p90을 변경 기록(OpenSpec proposal, PR, 커밋 본문)에 남긴다.
   - 절감 효과는 합산되지 않으므로 가장 긴 잡부터 줄인다. 효과는 실제 CI 전후 수치로만 주장한다.
2. **목표 지표를 먼저 정한다.** 이 저장소는 public이고 무료 GitHub-hosted `ubuntu-latest`(4 vCPU)를 쓰므로 wall-clock(대기 시간)이 목표다. private 저장소나 유료 runner는 runner-minutes(비용)도 함께 본다.
3. **게이트 잡을 다른 잡 앞에 두지 않는다.**
   - 버전·문서·아키텍처 검사 같은 fail-fast 잡은 테스트 잡의 `needs:`로 걸지 말고 병렬로 실행한다. `test.yml`의 `version-check`는 어떤 테스트 잡의 `needs:`도 아니다. 실제 자격 증명을 쓰는 마지막 opt-in 잡 `test-live`만 이를 기다린다.
   - 빌드·배포 게이팅은 테스트 워크플로우 전체 결과로 한다. `docker-build.yml`의 `changes`가 `needs: [test, test-pr]`로 이를 맡는다.
   - skipped 잡 뒤의 잡은 암묵적 `success()`에 기대지 말고 `!cancelled()`와 앞 잡 결과를 명시한다.
   - `if:`에 `!cancelled()` 같은 status 함수를 쓰면 암묵적 `success()`가 사라진다. skipped 잡의 output은 빈 문자열이므로 `needs.X.outputs.Y != 'true'` 같은 조건은 X가 skipped여도 참이 된다. 특정 이벤트 전용 잡은 `github.event_name` 조건을 맨 앞에 명시한다.
   - reusable workflow caller에는 skipped 조상을 두지 않는다. 내부 잡까지 건너뛸 수 있으므로 push와 PR caller를 분리한다(`test`/`test-pr`). `test-pr`은 `github.event_name == 'pull_request'`에서만 실행된다.
   - 여러 caller 결과로 게이팅할 때는 각 결과를 자기 이벤트에 연결한다. `needs.a.result == 'success' || needs.b.result == 'success'`처럼 합치면 한 caller의 통과가 다른 caller의 실패를 가린다.
4. **잡당 고정비를 측정한다.**
   - checkout, 의존성 설치, 서비스 준비 시간을 잰다. 캐시 복원이 재설치보다 느리면 캐시를 쓰지 않는다.
   - 서비스 컨테이너 health-check는 짧은 interval(예: 2초)과 충분한 retries(또는 start-period)로 설정한다. `test.yml`의 MariaDB/PostgreSQL/Redis는 `docker-compose.dev.yml` `test` profile과 같은 2s/5s/20이다.
5. **샤딩은 고정비가 작을 때만 한다.**
   - 테스트 러너가 작업을 나누는 단위(vitest는 파일)로 균형을 맞춘다.
   - 샤드 명령은 러너를 직접 호출한다. 래퍼 스크립트 뒤에 `-- --shard`를 붙이면 인자가 전달되지 않아 전체 스위트가 조용히 돌 수 있다(`npm run test:unit:frontend -- --shard`가 그랬다).
   - 샤드별 실행 파일 수를 CI에서 검증한다(`scripts/ci/verify-vitest-shard.js`).
6. **격리 해제는 opt-in으로만 한다.**
   - `isolate: false`, 워커 간 모듈 공유 같은 최적화는 전역에 적용하지 않는다. `--no-isolate`는 순서 의존 실패와 OOM으로 기각됐다.
   - 먼저 순서를 섞어(shuffle) 2회 이상 실행해 상태 누수를 확인하고, 안전한 파일만 명시적으로 opt-in한다.
   - `vi.stubGlobal`·전역 상태를 바꾼 테스트는 반드시 복원한다.
7. **테스트는 hermetic해야 병렬화할 수 있다.**
   - 단위 테스트는 실제 외부 서비스(Keystone, Prometheus 등)에 접속하지 않는다. 로컬 설정 파일(`afterglow.conf`)이 있느냐에 따라 결과나 시간이 달라지면 결함이다. `backend/tests/conftest.py` network guard가 이를 강제한다.
   - 병렬 실행(pytest-xdist 등)의 워커 수는 CI vCPU에 맞춰 명시한다(`-n 4`, `-n auto` 금지).
8. **변경 감지의 diff 기준을 정확히 한다.**
   - push는 `github.event.before..github.sha`로 비교한다. zero SHA·forced push·fetch 실패 시에는 전체를 대상으로 한다.
   - PR은 base..head로 비교한다. Afterglow 이미지 target 감지는 PR에서 빌드하지 않으므로 PR diff를 계산하지 않는다.
   - `HEAD^1..HEAD`처럼 push의 마지막 커밋만 보는 비교는 금지한다. 이미지 target 감지(`scripts/ci/detect-build-targets.js`)와 Helm chart 발행 판단(`scripts/ci/helm-publish-decision.js`)이 같은 event 기준 구현을 쓴다.
   - 변경 파일 목록은 rename 감지 없이 만든다(`git diff --no-renames --name-only`). 기본 rename 감지는 경로 규칙 밖으로 옮긴 파일을 도착 경로로만 보고해 원래 대상을 놓친다.
   - 기준을 만들지 못해 전체로 fallback할 때, 예상하지 못한 원인(fetch/diff 실패, 잘못된 before SHA)은 `::warning::`으로 남긴다. 비용 변화가 조용히 지나가지 않게 하려는 것이다.
   - 발행 산출물(이미지 등)은 실제 발행된 revision을 기준으로 판단한다. `org.opencontainers.image.revision` label을 쓰며, 규칙은 `scripts/ci/detect-build-targets.js`에 있다.
   - 발행 revision을 읽지 못한 레지스트리 오류(인증·전송·rate limit)는 부재로 취급하지 않고 더 빌드하며 경고한다. 이미지·label이 없는 bootstrap만 event 기준으로 fallback한다.
9. **중복 실행은 입력 동일성으로만 제거한다.**
   - 같은 저장소의 브랜치에서 온 PR이고 merge 트리가 head 트리와 같을 때만 PR 테스트를 건너뛴다. 현재 구성(`docker-build.yml` `pr-dedup`, 규칙은 `scripts/ci/pr-dedup.js`)은 여기에 두 조건을 더한다. head ref가 `dev`여야 하고, 그 head SHA의 `docker-build.yml` push 실행이 존재해야 한다.
   - fork PR과 dependabot PR은 항상 테스트한다.
   - 브랜치 이름만으로 판단하지 않는다. fork의 동명 브랜치로 우회할 수 있다.
   - tree가 같다고 해서 같은 입력을 테스트한 실행이 있는 것은 아니다. push trigger의 `paths-ignore`에 걸린 push는 실행을 만들지 않는데, 그 경로의 파일도 테스트 입력이다(예: `check_architecture.py`의 source snapshot). 그래서 건너뛰기 전에 그 SHA의 push 실행이 존재하는지 확인한다. 실행이 0건이면 테스트한다. 결론은 보지 않는다. synchronize 시점에는 push 실행이 대개 아직 진행 중이기 때문이다.
   - 판단 오류(git·API·JSON)는 테스트 실행(skip=false)으로 처리한다.
   - 건너뛴 PR은 같은 입력을 테스트한 push 실행에 결과를 맡긴다. 병합자는 dedup notice의 실행 링크에서 그 push 실행이 green인지 확인한 뒤 병합한다. 실행이 존재한다고 해서 그 실행이 통과한 것은 아니다.
   - push 실행에는 `cancel-in-progress`를 두지 않는다. 오래된 실행의 재발행은 발행 revision 가드로 막는다.
   - 가드는 ancestry만으로 판단하지 않는다. 이번 SHA가 태그가 추적하는 브랜치(`:dev`→`dev`, `:nightly`→`main`, 실행 ref가 아님)의 끝이면(force-push rollback 포함) 발행하고, 그 브랜치 끝이 바뀌었고 발행본이 더 새로울 때만 건너뛴다. rollback할 때는 되돌릴 commit의 진행 중인 실행을 취소한다.
10. **보안: public 저장소의 `pull_request` 코드를 self-hosted runner에서 실행하지 않는다.**
    - 워크플로우 YAML의 `if:`는 PR이 수정할 수 있으므로, runner group의 저장소 제한과 fork PR 승인 설정으로도 보장한다.
    - PR 이벤트에서는 레지스트리 자격 증명을 쓰는 step을 실행하지 않는다.
    - 한 줄 리터럴 GitHub-hosted label이 아닌 runner(self-hosted, matrix expression, 목록·group)를 쓰는 잡은 `if:`에 `github.event_name != 'pull_request'`를 최상위 conjunct로 둔다. step 출력(`is_pr` 등)만으로 PR을 제외하지 않는다.
    - PR에서 도달하는 잡과 PR caller가 부르는 reusable workflow(`test.yml`)의 모든 잡은 GitHub-hosted `ubuntu-*`에서 실행한다. `pull_request_target`은 쓰지 않는다. `scripts/github-actions-contract.test.js`가 모든 workflow를 파싱해 이를 고정한다. 이 계약은 실수로 인한 회귀를 막는 장치일 뿐이다. PR이 YAML을 고칠 수 있다는 위 전제는 그대로다.
    - PR 코드를 실행하는 reusable workflow caller에는 쓰지 않는 `secrets: inherit`를 두지 않는다(`test-pr`).
11. **CI 형태는 계약 테스트로 고정한다.**
    - 샤드 수, 게이트 병렬성, dedup 조건, diff 기준 같은 불변식을 저장소의 테스트로 검증해 회귀를 막는다. `scripts/github-actions-contract.test.js`, `scripts/test-target.test.js`, `scripts/ci/*.test.js`가 `npm run test:orchestration`에서 실행된다. 모든 `scripts/ci/*.test.js`가 여기에 포함되는지도 계약이 확인한다.
    - 안전 단계는 존재만이 아니라 게이트하는지도 고정한다. 검증·guard step과 필수 테스트 계층 step에 `if:`, `continue-on-error:`, `|| true`가 붙거나, 명령이 바뀌거나, 오류 arm이 사라지면 계약이 실패해야 한다. 실제 자격 증명을 쓰는 opt-in 잡(`test-live`)의 `if:`에는 status 함수(`always()` 등)를 두지 않는다.
    - 판단 로직은 workflow 인라인 쉘보다 `scripts/ci/`의 테스트 가능한 스크립트에 둔다. 계약은 workflow가 그 스크립트를 호출하는지를 고정하고, 규칙은 스크립트의 단위 테스트가 고정한다.
    - 불변식을 바꾸면 계약 테스트를 같은 변경에서 의도적으로 갱신한다.
12. **지속 개선.**
    - CI를 바꾸는 변경에는 전후 실측을 첨부한다.
    - 다음 중 하나가 생기면 위 1번 절차로 다시 측정하고 가장 긴 잡부터 개선한다.
      - 크리티컬 패스 중앙값이 기록된 기준(143초)보다 20% 이상 나빠진다.
      - 테스트 수가 크게 늘어난다.
      - 새 테스트 계층이 추가된다.

## 보안 개발 가이드라인

Afterglow는 cloud-init/SSH root 실행과 OpenStack 멀티테넌트 리소스를 다룬다. 새 코드와 리뷰에 아래를 적용한다.

1. **쉘·cloud-init·템플릿 보간**: 동적 값과 외부 OpenStack API 반환값 모두 Python `shlex.quote()` 또는 Jinja2 `| shlex_quote`로 쿼팅한다.
2. **입력 검증**: 실행 context로 흐르는 입력은 Pydantic whitelist regex로 검증하고 출력에서 다시 쿼팅한다. YAML에 들어가는 값은 newline injection도 막는다.
3. **fail-closed**: 토큰 바인딩, 세션 blacklist, 소유권 검증은 예외 시 거부한다. `except Exception: pass`나 warning 뒤 허용은 금지다. 로그인 잠금의 Redis 장애 fail-open은 의도된 예외다.
4. **timing-safe compare**: API/download token, HMAC, webhook secret은 `==`가 아니라 `hmac.compare_digest`를 사용한다.
5. **인가**: 앱 DB resource는 `resource.project_id == token_info["project_id"]`를 확인한다. admin endpoint는 `Depends(require_admin)`를 선언한다.
6. **시크릿**: 하드코딩·평문 logging·5xx 내부정보 노출을 금지한다. 비밀 설정은 secret.yaml으로만 전달한다.
7. **신규 endpoint 확인**: 인증 dependency, project ownership, Pydantic validation, shell/cloud-init quoting, security/injection regression test를 모두 확인한다.

## 커밋과 금지 사항

- 브랜치: `dev`
- 메시지: `feat`, `fix`, `refactor`, `docs`, `test`, `chore` 중 하나로 시작
- 커밋 전 `git status`로 불필요한 파일을 확인
- `main` 직접 커밋, `git push --force`, `.env`/시크릿 커밋, 플래닝 없는 대규모 refactor, 테스트 없는 backend endpoint 커밋 금지

## Skill routing

- product idea/brainstorm → `/office-hours`
- strategy/scope → `/plan-ceo-review`
- architecture → `/plan-eng-review`
- design system/plan review → `/design-consultation` 또는 `/plan-design-review`
- full review pipeline → `/autoplan`
- bug/error → `/investigate`
- QA/site behavior → `/qa` 또는 `/qa-only`
- code review/diff → `/review`
- visual polish → `/design-review`
- ship/deploy/PR → `/ship` 또는 `/land-and-deploy`
- save/resume context → `/context-save` / `/context-restore`
