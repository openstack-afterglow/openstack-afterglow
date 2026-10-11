## Implementation Tasks

- [x] 현재 account/resource/wizard/authority 계약과 디자인 규칙을 확인한다.
- [x] OAuth/API 키를 나란히 선택하고 선택한 방법의 setup와 연결/키 목록만 표시한다.
- [x] 키 이름·권한 발급 form을 간결한 responsive 구성으로 바꾼다.
- [x] 개인 키의 실제 1일·1주·1달·3달·6달·1년·만료 없음·직접 선택 lifetime을 구현하고 OAuth/내부 위임 정책을 유지한다.
- [x] 각 mcp.json 전체 복사와 발급 secret once-only/scope fence를 검증한다.
- [x] 최근 활동의10/15/20개 page size·이전/다음·filter/refresh/scope 경계를 구현한다.
- [x] unsupported squashfs consumer 옵션·상태·호출 경로를 제거하고 Palimpsest 독립 build/package/runtime를 보존한다.
- [x] 비동작 HA beta 옵션·state·caller/payload를 제거한다.
- [x] 내 리소스에서 DB·Drover·Waygate 및 현재 지원 사용자 resource inventory를 owning project·부분 오류와 함께 표시한다.
- [x] 계정과 내 리소스의 centered PageShell 및 네 locale·responsive/theme UI를 맞춘다.
- [x] 모든 페이지의 외부 콘텐츠 박스에 동일 80rem 기본 최대 폭·가운데 정렬·responsive padding을 적용하고 개별 page 폭·여백 불일치를 제거한다.
- [x] 행동 회귀·실제 API/SQL/native·Chromium smoke와 project gate를 실행하고 성공·실패를 기록한다. 전체 gate는 아래 동시 변경1건 때문에 통과하지 않았다.
- [x] architecture/design/API/user/security/testing 문서·Unreleased changelog를 실제 변경/증거와 동기화한다.

## Qualification receipt

- 구현 완료, 배포하지 않음. Gate 통과/운영 qualification을 뜻하는 archive가 아니다.
- 실제 source Chromium: 만료8종의 발급/전체 JSON clipboard/secret 제거, 활동10/15/20 paging·filter,8개 breakpoint. 실제 compiled preview: account/resources32 locale/theme/width조건 및27route81폭조건, center/overflow0. Native-shaped fixture의 partial/denied/disabled·503 stale snapshot 제거·recovery, 다른 project 링크 차단. Ordinary VM4단계 review까지 이동 후 취소; cloud 생성0.
- Native inventory: 실제 SDK·TCP1449응답,25종·2project·완전 pagination·ownership·keypair dedup·warm-cache 권한/namespace 변경·오류null. Keystone/provider/role graph/fakeredis는 합성이다.
- Personal MCP: 실제 Uvicorn/SDK24 upstream HTTP/MariaDB로 never/6mo/year 생성201·UTC microseconds·conflict422·revoke204. SQL103passed. Migration085 nullable CHECK와 ORM precision·public UTC projection을 함께 검증했다.
- Drover dependency: `../drover/drover/db.py`, `api/clusters.py`, `services/store.py` 및 회귀를 수정했다. 실제 SQL/Redis16HTTP의 wall-clock breaker/recovery/fallback0, focused93passed·Ruff. Native 전체 migration/readiness·IAM은 미검증이고 legacy cache key 충돌은 범위 밖 한계로 기록했다.
- VM backend 최종87passed; 실제TCP retired list/consume404, retained endpoints401. 마지막 test-only 개선은 router/column wiring assertion을 제거하고 실제 HTTP regression으로 교체한 것이다.
- Gate: backend4993passed/1failed (`test_mutation_invalidate_coverage`의 동시 Lumen approve/disable). 이 변경의 실패로 숨기거나 예외를 추가하지 않았다. 나머지 original suite 별도 실행: frontend2909+runner9, contracts156, functional118/23deselected, Ruff573files. JS orchestration175·Kolla27+11·shell19/PowerShell36skip. Svelte0errors/2warnings, i18n0문제, production build 통과.
- 검증 환경: private TOML 오류를 고치거나 읽지 않고 isolated source cwd 사용. 초기 smoke의 catalog interface 누락·Docker 재시작 후 임시 port 변경·Redis fixture key 충돌·브라우저 금지port1은 검증 fixture에서만 수정했다. 실제 운영 URL/DB/키/볼륨·공유 index·review marker는 보존했다.
- Migration085 schema-before-writer, 현재 운영 snapshot/양방향·mixed-version 호환성·rollback 검증 및 Drover 배포는 별도 운영 선행 조건이다. 이번 작업은 운영 조회/쓰기·release/deploy·commit/push를 하지 않는다.
- Evidence: `/Users/pieroot/.local/share/afterglow-proofs/account-resources-20261011/`; 상세 원문/실패 이력은 `docs/testing.md`의 계정·전체 리소스 검증 절.
- Final architecture: private 설정 없는 frozen source의 working/staged guard 모두 `d3768d2de0ad659d9c97a0afa77df6cdc1353339978c6ac9faa3e2b407bda4ed`/2601files 통과. 실제 shared index/review marker 보존. First gate digest·마지막 test-only HTTP 회귀 차이는 `docs/testing.md`에 구분했다.
