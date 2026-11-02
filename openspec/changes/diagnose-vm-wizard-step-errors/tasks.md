# Tasks

- [x] 1.1 운영 3개 controller backend 요청 로그 읽기 전용 확인(해당 경로 non-200·10초 초과 없음)
- [x] 1.2 실제 store+API client로 같은 scope 쓰기 중 옵션 조회 영구 `loading` 재현(수정 전 실패 테스트)
- [x] 2.1 `optionError` 실패 분류, `currentStepErrors`, 배너 항목 목록, 9개 언어 key
- [x] 2.2 무효화된 옵션 조회 재요청(요청 key별 최대 2회, 초과 시 `options.cancelled` 오류·명시적 재시도), `apply` 예외를 네트워크 분류와 분리
- [x] 3.1 회귀 테스트: 무효화 후 재조회, 네트워크/시간 초과/HTTP 503 원인 표시, 반복 무효화 상한·재시도 성공(`vmCreateStoreRealClient.test.ts`)
- [x] 3.2 관련 store/wizard/component suite 67 files 1086 passed, `npm run check` 0 errors, `i18n:check` 0 errors
- [x] 3.3 로컬 frontend 재빌드 후 실제 compiled UI(Chromium, 모든 API 합성 fixture, keypairs 연결 실패)에서 3단계 배너 "키페어: 네트워크 연결 실패(서버 응답 없음)" 확인
- [ ] 4.1 운영 배포(별도 승인)와 다음 발생 시 화면 원인 수집
- [ ] 4.2 원인 확정 후 archive
