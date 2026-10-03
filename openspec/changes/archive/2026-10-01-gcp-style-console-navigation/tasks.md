## Implementation Tasks

- [x] 상단 로고 오른쪽의 세로선을 제거한다.
- [x] 로고 옆 Admin·페이지 경로 표시를 제거하고 프로젝트 선택만 남긴다.
- [x] 왼쪽 사이드바에 숨김·다시 열기 기능을 추가한다.
- [x] GCP처럼 전체 메뉴 drawer와 서비스별 sidebar를 분리하고 기존 항목·권한·capability·beta 조건을 보존한다.
- [x] 세부 페이지 이름을 상단 헤더 대신 왼쪽 사이드바 상단에 표시한다.
- [x] 실제 사용자·관리자에서 direct/nested navigation, menu keyboard/outside dismissal 및 focus, sidebar hide/reopen과 panel/dock offset, project dropdown, 검색, breakpoint·dark/light·overflow를 검증한다.
- [x] frontend 이미지·runtime·로컬 적용 및 타입검사·관련 행동 테스트·프로젝트 gate를 실행하고 결과·검증 한계를 기록한다.

## Verification

- 실제 인증된 `http://localhost:3080` Chromium에서 `/dashboard`, `/dashboard/volumes`, 실제 volume UUID 하위 route, `/admin`, `/admin/drover/templates`를 탐색했다. Nested template는 Drover 부모 대신 `클러스터 템플릿` 하나만 current로 표시했다. 개요는 sidebar 없이 main left 0을 유지했다.
- 사용자·관리자 각각 320, 390, 640, 767, 768, 800, 1023, 1024, 1280, 1440, 1920px에서 48px header, 검색 viewport 중앙, header 비중첩과 수평 overflow 0을 확인했다. Dark/light desktop·mobile screenshot을 확인했으며 720 CSS px로 1440px의 200% zoom-equivalent를 확인했다. Native browser zoom 검증은 아니다.
- Drawer route 선택·Escape·실제 backdrop 클릭과 opener focus 복원을 확인했다. Desktop reverse Tab은 마지막 `프로젝트 설정`, mobile은 마지막 모드 링크로 이동하고 Tab은 닫기 버튼으로 돌아왔다. Mobile drawer 검색은 drawer를 닫고 combobox를 focus했다. User/admin 프로젝트 popup은 dialog 내부에 열렸고 현재 DMSLAB 선택은 popup을 닫았다. 다른 프로젝트로의 Keystone rescope는 수행하지 않았다.
- 실제 VM 생성 panel과 volume detail에서 sidebar 숨김·복원에도 열린 작업이 유지됐다. 800px에서 default VM panel은 left 240, width 560으로 sidebar 침범이 없다. 실제 resizable volume panel을 1000px로 저장한 뒤 800px에서는 left 240/width 560, sidebar 숨김 후 left 0/width 800으로 줄고 저장된 1000은 유지했다. QA 변경 선호 폭과 테마는 복원했다.
- Dock은 실제 배포 CSS의 숨긴 임시 geometry probe로 overview/mobile left 0, sidebar 표시 240, 숨김 0을 확인하고 즉시 제거했다. 승인 dialog 취소의 ticket POST는 0이다. 실제 terminal/session은 생성·재시도하지 않았으므로 live dock lifecycle·Zun/Cinder mkfs 문제는 검증·수정하지 않았다.
- Canonical local Compose frontend arm64 이미지 build·선택 service apply가 healthy이며 기존 env와 두 mount가 보존됐다. Dockerfile frontend target amd64 build와 실제 Node server `/health` 200, `linux/x64` 실행을 확인하고 임시 container를 중지했다. 초기 관련 6개 파일 74 tests가 통과했고 최종 `npm run check --prefix frontend`는 2127 files, 0 errors/warnings다.
- `npm run test:gate` 실행 결과: docs freshness, backend unit 3393, frontend 275 files/1857 tests, contract 136, functional 28 및 Ruff check 통과. Ruff format check만 `backend/app/main.py`, `backend/app/services/layer_build.py`, `backend/tests/test_logging_contract.py` 세 파일에서 실패했다. 이 작업에서 수정하지 않은 파일은 보존했으며 gate 전체는 실패다.
- 운영 배포·staging·commit·push·OpenStack resource mutation은 하지 않았다. Post-change gbrain sync는 CLI가 설치되지 않아 수행하지 못했다 (`gbrain --version`: command not found).
- Gate 실행 시 working source fingerprint는 `47cddfd3a5d6da4e007e04867d8781799e67e16657f226068f10916e9aec5822`였다. 동시 작업의 별도 source 변경을 보존한 archive 시점은 `1894b4f100df3c4d27f50cae11141712aa6b6f3fd17c49b676482f53de411da4`이며 docs freshness와 실제 index `--staged` guard가 통과했다. Gate 결과를 이후 동시 변경 전체의 재검증으로 간주하지 않는다. Rapid schema에는 delta specs가 없어 archive의 경고만 표시됐다.
