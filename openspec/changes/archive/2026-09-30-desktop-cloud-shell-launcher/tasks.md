## Implementation Tasks

- [x] 기존 root header·사이드바·Cloud Shell 승인 흐름과 1024px 반응형 계약을 확인한다.
- [x] 데스크톱 상단 왼쪽에 아이콘과 레이블을 가진 기존 Cloud Shell 실행 버튼을 연결한다.
- [x] 1024px 미만에서 실행 버튼을 숨기고 사용자·관리자 사이드바에는 추가하지 않는다.
- [x] 실제 브라우저에서 반응형 표시·숨김 및 승인·취소·기존 실행 경로를 확인하고 관련 frontend 검증을 실행한다.

## Verification

- Cloud Shell controller·terminal, Sidebar·AdminSidebar, visual-debt 기존 테스트: 5 files / 22 tests passed.
- `npm run check`: 2,111 files, 0 errors, 0 warnings.
- 실제 Chromium/Vite dashboard와 합성 API 경계: 375·768·1023px에서 실행 버튼 숨김 및 사이드바 부재; 1024·1440px에서 버튼 표시, 페이지 overflow 없음. 관리자 셸도 1023·1024px 전환과 사이드바 부재를 확인했다.
- 현재 프로젝트 승인 안내, 버튼·Enter 진입 및 취소 시 API 추가 호출 없음; 명시적 승인 시 ticket POST 1건; 합성 503을 기존 인프라 불가 안내로 표시. 서비스 capability 비활성화 시 버튼 숨김.
- 1024px 검색 한 줄 배치(36px, 48px header 안에 포함)와 dark/light header를 확인했다.
- `DESIGN.md`, `docs/api/cloud-shell.md`, `ARCHITECTURE.md` 갱신. Architecture guard working snapshot stamp/check와 기존 index의 staged check 통과. 사용자 변경·index는 보존했다.
- 운영 배포, 실제 Zun/Cinder 자원 생성 및 전체 `test:gate`는 실행하지 않았다. 서비스 설정과 인증 경계는 변경하지 않았다.

