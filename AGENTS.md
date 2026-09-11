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
  1. **단위 테스트 (Unit)**: `npm run test:unit:backend`, `npm run test:unit:frontend`, `npm run test:unit` (외부 네트워크·Docker·자격 증명 없음; 전체 unit은 오케스트레이터 회귀 포함)
  2. **소비자 계약 테스트 (Contract)**: `npm run test:contract` (`backend/tests/contracts/`의 BFF/SDK/catalog/ingress 경계)
  3. **국소 기능 테스트 (Functional)**: `npm run test:functional` (실제 MariaDB/PostgreSQL/Redis를 쓰는 전용 일회용 Compose). 기본 자동 기동·종료. 재사용은 `--no-start`, 로컬 유지는 `--keep`.
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
