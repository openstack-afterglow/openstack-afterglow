## Implementation Tasks

- [x] Cloud Shell 버튼을 기존 우측 프로젝트 선택 위치로 옮긴다. 기존 capability·desktop-only·승인 조건을 유지한다.
- [x] 프로젝트 선택 버튼을 좌상단 로고 오른쪽으로 옮기고 긴 이름의 말줄임과 기존 portal dropdown을 보존한다.
- [x] 상단 리소스 검색을 전체 viewport 중앙에 배치하고 좁은 desktop에서 좌우 컨트롤과 겹치지 않게 한다.
- [x] 실제 인증된 user/admin 화면에서 반응형 경계와 dropdown·검색·Cloud Shell 승인 취소를 확인하고, 해당 frontend 이미지·문서·아키텍처 검증을 완료한다.

## Verification Evidence

- 실제 사용자 인증을 유지한 `http://localhost:3080/dashboard`와 `/admin`을 확인했다. 인증·OpenStack API를 mock하지 않았고 project scope는 `DMSLAB`으로 유지했다.
- User viewport: 320, 390, 767, 768, 1023, 1024, 1120, 1279, 1280, 1440, 1535, 1536, 1920px. Admin viewport: 390, 767, 768, 1023, 1024, 1120, 1279, 1280, 1440, 1535, 1536, 1920px. Admin 판정은 URL만 보지 않고 실제 header의 `현재 관리자 모드, 사용자 모드로 전환` 상태가 적용된 뒤 측정했다.
- Desktop 검색 중심과 viewport 중심의 오차는 0px였다(1440px → 720px). Header 높이는 48px이고 visible control overlap과 document horizontal overflow는 없었다. 1024px 아래에서는 header의 project/search/Cloud Shell이 숨겨지고 sidebar 진입점을 유지했다.
- Desktop project dropdown은 x=264, y=43.5, width=256px로 trigger 아래에 열리며 header 밖에 portal되고 viewport 안에 표시됐다. Mobile 390px project dropdown도 viewport 안에 표시되고 바깥 클릭으로 menu와 drawer가 닫혔다. 긴 project label은 1024/1440px에서 아이콘·32px 높이를 유지하며 말줄임했다(임시 DOM label은 즉시 복원).
- 검색에서 `볼륨` 입력 후 실제 Cinder volume 이름과 navigation 결과를 확인했다. Tablet sidebar search도 열고 Escape로 닫았다.
- Cloud Shell 클릭 → 현재 project를 명시한 승인 dialog → 취소: ticket POST 0, dialog 닫힘, trigger focus 복귀를 확인했다. 승인 버튼은 누르지 않았고 Cloud Shell 생성을 재시도하지 않았다.
- Dark/light header를 확인했다. 200% 대응은 720px viewport / 2x deviceScaleFactor의 zoom-equivalent emulation으로 확인했으며 native Chrome zoom 조작은 검증하지 않았다. 마지막에 원래 1440×857 viewport·dark/system theme·사용자 dashboard로 복귀했다.
- Canonical dev Compose arm64 frontend 빌드 및 `--no-deps --wait frontend` 적용을 확인했다. 실행 container는 healthy이고 기존 env와 두 mount가 동일했다. 실제 container의 Node는 `arm64`/Linux/`v20.20.2`였다. 별도 amd64 frontend 이미지 빌드와 Node `x64`/Linux/`v20.20.2` 실행도 확인한 뒤 이 verification image tag만 제거했다.
- `python3 scripts/check_architecture.py --stamp --summary ...` 및 `npm run docs:check`: working source `1a19180f016049e80243488f99d3a65468fea640b531ab5b06ae114fc56298b6`, 2146 files. `python3 scripts/check_architecture.py --staged`도 기존 index에서 통과했다. 이번 파일을 stage하거나 commit/push하지 않았다.
- `npm run check --prefix frontend`: Svelte/TypeScript 검사 2125 files, 0 errors, 0 warnings.

## Verification Limits

- 순수 frontend composition/CSS 변경이므로 새 permanent test는 추가하지 않았다. `npm run test:gate`는 재실행하지 않았다.
- ProjectSelector의 기존 Escape 미지원은 그대로이며 바깥 클릭 닫기를 확인했다. 이벤트 handler·project switching 계약은 변경하지 않았다.
- 기존 Cloud Shell의 compute-side RBD 장치 경로 오류와 audit DB migration 누락은 변경하지 않았다. Terminal ready·bootstrap·CLI 성공을 이 헤더 검증으로 주장하지 않는다.
- `gbrain` CLI가 PATH에 없어 code-index sync는 실행하지 않았고 CLAUDE.md·인증 session export는 하지 않았다.
