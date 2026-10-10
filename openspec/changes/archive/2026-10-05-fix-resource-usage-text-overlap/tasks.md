## Implementation Tasks

- [x] 공용 UsageBar와 inline 사용처에서 막대·수치 겹침의 CSS 원인을 확인한다.
- [x] 공용 기본 폭의 utility override를 복구하고 관리자 표의 헤더·열 간격을 확보한다.
- [x] 실제 Chromium에서 폭·테마·reduced motion·큰 사용량·프로젝트 선택을 검증하고 관련 기존 검사를 실행한다.

## Verification

- 원인: unlayered scoped `.usage-bar { width: 100% }`가 Tailwind `w-14`보다 우선해 막대가 56px 대신 120px 전체 셀을 차지했다. 수정 후 막대 56px, 수치 간격 6px, 열 간격 12px다.
- 실제 현재 source의 Chromium 관리자 개요: 390·640·767·768·1023·1024·1343·1440px × light/dark × reduced/no-preference = 32개 조건에서 text Range의 셀 밖 넘침·페이지/작업 영역 가로 넘침·막대/수치 겹침 없음. 긴 프로젝트명·큰 수치·무제한 쿼터 포함.
- 공용 기본 막대·QuotaBar·CapacityBar·flex inline 막대·LandingConsolePreview cluster를 실제 컴포넌트로 mount해 390·767·768·1023·1024·1440px × light/dark = 12개 조건의 표시 영역 비중첩을 확인했다.
- 모바일 표를 마지막 열까지 가로 스크롤해 GPU 헤더를 확인했고, 프로젝트 선택으로 CV 쿼터 패널의 인스턴스 한도 20을 읽은 뒤 닫았다. 저장 요청은 하지 않았다.
- 200% zoom 등가(1343px → 672px CSS viewport, device scale 2)에서 수평 넘침 없음. 실제 browser zoom 조작·다른 브라우저 검증은 아니다.
- `npx vitest run src/lib/components/ui/__tests__/UsageBar.test.ts src/routes/__tests__/designSystemRules.test.ts`: 2 files / 18 tests passed. 구현 문자열만 고정하던 5개 meter test를 삭제했고 표시값 경계 검사는 유지했다.
- 최종 `npm run check`: 2,174 files, 0 errors, 0 warnings.
- HEAD+현재 변경 source 3개 파일의 임시 index에서 architecture `--staged` 통과: `feeca05b22ae6bc1f50a781155fd17234c70a636da0ba527df823cfc87bc19c7`, 2,164 source files. 실제 index와 공유 architecture review block을 덮어쓰지 않았다.
- 증거: `~/.gstack/projects/afterglow/designs/resource-text-overlap-20261006/`의 before/after·light·mobile·zoom 등가·공용 컴포넌트 screenshot과 `verification.json`. QA browser·Vite server·임시 index·browser profile 정리 완료.
- identity/API 응답은 합성 fixture다. 실제 OpenStack·전체 동시 변경 test:gate·운영 배포·커밋/푸시는 수행하지 않았다.

