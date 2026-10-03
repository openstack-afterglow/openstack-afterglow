## Implementation Tasks

- [x] 1. 기존 보안 그룹 타입 기반의 인터페이스별 규칙 합집합·포트/ICMP/원격 대상 표시 유틸리티와 결정적 경계 테스트 구현.
- [x] 2. 기존 UI primitive와 semantic token을 사용하는 인바운드/아웃바운드 읽기 전용 표시 컴포넌트 및 오류·누락·미적용 행동 테스트 구현.
- [x] 3. 상세 controller의 보안 그룹 로딩/오류/포트 snapshot을 노출하고 NetworkSection의 저장된 적용 그룹과 새 표시를 연결.
- [x] 4. 관련 frontend 회귀 및 check를 실행하고 실제 Chromium 상세 화면에서 반응형·합집합·편집 후 갱신·조회 실패를 확인.

## Verification Evidence

- `node scripts/test-target.js frontend:src/lib/components/instance/__tests__ frontend:src/lib/stores/__tests__/instanceDetailController.resize.test.ts frontend:src/lib/stores/__tests__/instanceDetailController.loading.test.ts frontend:src/lib/utils/__tests__/securityGroupUnion.test.ts`: 11 suites, 71 tests passed.
- `npm run check` (frontend): 2125 files, 0 errors, 0 warnings.
- Source Vite의 실제 Chromium에서 합성 identity/API로 직접 상세·목록 상세 패널·관리자 공용 상세의 규칙 병합과 인터페이스 격리를 확인했다. 미저장 선택은 정책을 바꾸지 않으며 저장 후 SG 응답의 포트 snapshot이 오래된 interfaces cache를 덮어쓴다.
- SG 요청을 지연하면 두 인터페이스 모두 로딩 상태·표 0개·편집 차단이 되고 성공하면 각각 인바운드/아웃바운드 표와 편집이 복구된다. 503 실패와 누락 그룹은 이전/부분 표를 숨기며 미적용 그룹과 빈 규칙은 서로 다른 상태다.
- Dark/light 390–1440px에서 document overflow 0, 390px 관리자 패널의 내부 표 가로 스크롤 및 안내문 영역 내 줄바꿈을 확인했다.
- `ARCHITECTURE.md`, `docs/api/instances.md`, `CHANGELOG.md`를 갱신하고 working architecture freshness를 통과했다. 기존 UI primitive/token을 재사용하여 DESIGN.md에 새 규칙을 추가하지 않았다.
- QA 브라우저·임시 profile·소스 preview를 종료/제거했다. 운영 배포·실제 OpenStack/Neutron 검증·staging/commit은 하지 않았다. Gbrain CLI 미설치로 index sync는 실행하지 못했다.
- 후속 검토 (`fix-instance-security-group-refresh`): 위 저장 후 snapshot 검증은 합성 API 응답에 한정된다. 실제 SG GET은 refresh query를 읽지 않으며 저장 전 느린 Neutron `_inflight` 조회와 저장 후 응답이 합류하는 서버 cache race는 검증·수정하지 않았다. 후속 frontend 변경은 silent polling 표시 및 브라우저 broker 요청 합류만 수정한다.

