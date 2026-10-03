## Implementation Tasks

- [x] 헤더 열기·drawer 닫기 버튼과 로고의 정렬을 일치시킨다.
- [x] 전체 drawer의 현재 페이지 메뉴 표시 항목을 제거한다.
- [x] 토폴로지를 활동 아래에 배치한다.
- [x] 프로젝트 설정을 전체 메뉴에서 제거하고 프로젝트 선택 popup을 유지한다.
- [x] 서비스 sidebar에서 전체 메뉴 항목을 제거한다.
- [x] 헤더 프로젝트 오른쪽의 복원 버튼을 제거하고, 상세 sidebar는 각 메뉴 아이콘만 남는 rail로 접으며 최상단의 같은 버튼으로 펼친다. 선택·프로젝트·모드·focus를 보존한다.
- [x] 실제 사용자·관리자 화면에서 정렬·배치·아이콘 rail 접기/펼치기·항목 이동과 반응형 동작, 관련 테스트·타입검사·이미지·로컬 runtime·gate를 검증하고 결과·한계를 기록한다.

## Verification

- 최종 compact nav는 component-scoped scrollbar 숨김 없이 전역 scrollbar token을 사용한다. `overflow-x: hidden`을 두고 첫 항목 focus ring을 위해 `pt-1`을 준다. `DESIGN.md`의 "Reuse global scrollbar tokens" 규칙에 따라 직전 `.nav-rail` 숨김을 제거했다.
- 실제 인증 admin 검증은 `/admin/chat/tools`, 1440×900에서 scrollbar 수정 전 rail build로 했다. 접힘 시 56px·offset 3.5rem·16px SVG에 보이는 label이 없고 선택·tooltip이 유지됐다. Enter 펼침은 240px·15rem이고 toggle focus와 auth hash가 유지됐다. 최종 build의 refresh/login은 backend의 Keystone `172.30.0.253:5000` TCP connect timeout(30s, refresh 503)으로 실패해 재로그인 검증을 하지 못했다. 인증 우회와 재시도는 하지 않았다.
- 최종 arm64 canonical frontend `sha256:bac03fada2d9be6ef82469da4934583e4fc65203f1b2bbcee237047771dd9cd1`를 `--no-deps --wait`로 적용해 healthy를 확인했고 env/mount/group_add를 보존했다. amd64 `sha256:abbafaa6f86446e83617dd4c45b41306b645df2e542b57e90578f95db26e80f7`는 container 안에서 `linux/x64`, `/health` 200을 확인한 뒤 중지했다.
- 최종 build를 내장 튜토리얼(user)·관리자 미리보기(admin) Chromium으로 320–1920px 14개 폭씩, 총 28 scenario 검증했다. 모든 폭에서 header 열기/drawer 닫기·로고 좌표가 일치하고 chrome overflow가 0이다. 768px 이상 20 case는 56px rail, 아이콘만, 44×44 target, 같은 toggle focus, 별도 header 복원 버튼 없음, Enter 재펼침을 유지했다. 1024px 이상은 검색이 viewport 중앙에 있다. Mobile 8 case는 rail이 표시되지 않는다.
- 800×300 network rail은 전역 10px gutter, client/scroll width 45/45, overflow-x hidden, 첫 항목 위 4px 여유를 보였다. Tab으로 마지막 `보안 그룹`까지 scrollTop 60, wheel로 60이 됐고 top toggle은 고정됐다. Scrollbar가 보이는 동안 focus ring 좌우 여유는 0.5px라 위·아래 ring만 온전하다.
- Space는 false→true→false로 바뀌고 focus를 유지한다. 접힌 rail에서 `라우터`로 이동해도 56px 접힘, aria-current, header의 프로젝트/모드, 튜토리얼 모드가 유지된다. `sidebarExpanded`는 메모리 상태라 전체 reload 시 펼침으로 시작한다.
- `/dashboard`, `/dashboard/network/topology`, `/dashboard/project-settings`는 `hidden`, offset `0rem`이며 sidebar·toggle이 없다. `/admin/libraries`는 Palimpsest rail을 유지한다.
- Volume detail SlidePanel에 790px 선호 폭을 저장한 뒤 800px에서 확인했다. 펼침 left 240/560px, 접힘 left 56/744px, 재펼침 240/560px이고 저장값 790은 유지됐다. Mobile frame은 left 0 전체 폭이다. 상세 panel은 resource URL(`/dashboard/volumes/mock-volume-1`)별 key를 쓰므로 그 key로 검증했다. QA key는 제거했고 기존 `slidePanel./dashboard/volumes.width=443`은 보존했다.
- Cloud Shell은 mockup에서 비활성이다. 따라서 `.cloud-shell-dock { left: var(--app-sidebar-offset) }`와 offset 값(15rem/3.5rem/0rem)만 확인했고 session은 만들지 않았다.
- Sidebar/AdminSidebar/nav 3 files 66 tests가 통과했다. 동시 작업이 overview 다음에 `프로젝트 패키지`를 추가해, topology 순서 test를 "활동 직후, 서비스 목적지 이전" 불변식으로 한정했다. `npm run check`는 2161 files, 0 errors, 2 warnings다. 경고는 모두 동시 작업 `src/routes/palimpsest/packages/+page.svelte`에서 나왔다.
- Gate layer는 최종 stamp `6391d93e4c2bd6d0c791cfb5684bcc5436567aa90ea649af23e24de29c735152`에서 실행했다. Docs freshness, orchestration 106, kolla 26, CLI 13(15 skipped), backend unit 3453, contract 133, functional 28이 통과했다. Frontend unit은 274/275 files, 1874/1876 tests다. 실패 2개는 동시 landing 변경(`LandingPage.svelte`, `LandingOpsBoard.svelte`)을 검사하는 `typographyRoles.test.ts`다. `lint:backend`는 동시 작업 `app/api/palimpsest/package_keys.py`, `packages.py`의 Ruff check(I001/SIM102)로 실패해 전체 gate는 실패다.
- 직전 gate의 functional layer는 `127.0.0.1:3307` 일시 충돌로 실패했다. 공유 `afterglow-test` project를 건드리지 않도록 같은 compose 정의의 owned dynamic-port MariaDB/PostgreSQL/Redis로 재실행했고 종료 후 container·network를 제거했다.
- 범위 밖 기존 문제: 320px `/dashboard/compute/instances`는 `TableShell` scroller가 `position: static`이라 표의 absolute `sr-only` header가 body 기준으로 배치되어 문서 폭이 1078px이 된다. 수정하지 않은 `InstancesTable`/`TableShell` 문제라 이번에 고치지 않았다.
- 운영 배포·staging·commit·push·OpenStack 자원 변경은 하지 않았다.
