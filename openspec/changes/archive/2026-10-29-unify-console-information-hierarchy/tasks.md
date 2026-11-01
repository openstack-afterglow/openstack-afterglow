## Implementation Tasks

- [x] 1. 현재 source·실행 화면과 보고서의 13개 화면/상태 대조 및 증거 기록
- [x] 2. 사용자/관리자 핵심 목록 우선 구조·접힌 추이·용량 분석·하단 페이지 조작
- [x] 3. 행동색/상태색/중립 선택과 기본 조작 크기 통일
- [x] 4. 타이포그래피/간격/숫자/식별자/대비 규칙 개선
- [x] 5. 기능 중심 navigation/브랜드 병기/명시 scope/즐겨찾기·최근
- [x] 6. 사용자 dashboard empty와 관리자 운영 우선순위/전체폭 domain 표
- [x] 7. 지표 정의·분모·초과 실제 비율과 측정/할당 구분
- [x] 8. 공통 상태·짧은 UUID/복사·소유자·행 메뉴/위험·bulk·기존 상세 일관성
- [x] 9. VM wizard 실패/빈/필터/쿼터/로딩 분리 및 프로젝트 구분
- [x] 10. topology grouping/selection/inspector/zoom summary/toolbar/help/animation off
- [x] 11a. Drover 오류 요약·상세 및 Cloud Shell 단일 헤더
- [x] 11b. Palimpsest 작업별 분리와 명시 기반 선택
- [x] 11c. 설정 분류/지역화 및 Lumen 권한 범위·복구 안내
- [x] 12. 유지/제거/추가 원칙과 설치 브랜드·Afterglow 관계 반영
- [x] 13. 실제 화면·상태·두 테마·반응형·지원 locale·키보드 검증 및 관련/전체 checks
- [x] 14. DESIGN/architecture/상세 guide/changelog/verification 갱신과 archive

## Light / dark priority additions
- [x] L1. 추가8개 확인 화면을 기존 source/실행 증거와 대조
- [x] L2. white editable/card/table vs page/readonly/disabled 역할 분리
- [x] L3. 상태 text/wash 대비4.5:1·12–13px·점/아이콘/명명 검증
- [x] L4. 프로젝트 선택행·입력·카드·popover 테두리/focus 위계
- [x] L5. 관리자 빈회색 영역 제거와 warning text/fill/line 분리
- [x] L6. 두 theme chart/topology hierarchy·선택·zoom 검증
- [x] L7. 명시 theme menu/current check/system resolved outcome와 OS 추종
- [x] L8. 의미 token 동기화·동일 instances 기준 화면 dark/light 검증

## Verification disposition

- Source-only. Actual Chromium matrices, native SDK loopback observations, complete test receipts and limitations are recorded in `docs/testing.md` and `verification.json`.
- Final isolated gate snapshot: backend11137passed/106skipped, frontend5772passed/474files, contract183passed, DB functional167passed/33deselected. Gate is **not green**: final Ruff reports three unrelated concurrent Cloud Shell import errors. Task-owned Python Ruff check/format passed; no lint suppression or unrelated source rewrite.
- Production build passed; check0errors/16warnings; localization0errors/45orderingwarnings; no hard-coded Korean source lines. No live-provider/production acceptance, deploy, commit, push, or shared-index mutation.
- Repository rapid workflow has no delta-spec layer (`docs/agent-development-guide.md`). Generic strict validation reports missing deltas; archive follows the documented `--skip-specs` workflow, not a fabricated spec-validation pass.
