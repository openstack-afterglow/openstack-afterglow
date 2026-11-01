## 1. 서비스 Keystone 토큰 공유

- [x] 1.1 `keystone._get_admin_ks_client()`가 호출마다 독립 Session/Client를 만들되, 인증은 프로세스 공유 서비스 토큰 캐시에서 받도록 변경
- [x] 1.2 만료 임박 시 single-flight 성공/실패 공유, 401 invalidate는 해당 토큰일 때만 폐기, 설정 변경 시 새 캐시
- [x] 1.3 회귀 테스트: 여러 NativeOperation의 한 번 인증, 만료·invalidate·concurrent failure·live revocation 검증

## 2. Valkey failover 재시도

- [x] 2.1 직접·Sentinel에서 안전한 읽기만 제한 재시도하고 모든 임의 쓰기/EVAL/pipeline의 자동 재실행 금지
- [x] 2.2 실제 loopback RESP/Sentinel에서 master 변경·명령 commit 뒤 응답 유실 경계 검증

## 3. refresh rotation replay 창

- [x] 3.1 rotation 성공 응답을 이전 JTI 기준 30초 replay 레코드로 저장(새 JTI·사용자 포함)
- [x] 3.2 이전 refresh JWT 재요청 시 새 세션이 살아 있고 차단되지 않았으며 출처 바인딩이 통과할 때만 동일 응답 반환, 아니면 기존 401
- [x] 3.3 회귀 테스트: 응답 유실 후 재시도 성공, 새 세션 로그아웃/추가 회전/차단/창 만료 뒤 401, 다른 사용자 토큰 거부
- [x] 3.4 rotation+receipt 원자 commit, 동일 EVAL 재전송 및 동시 갱신 패자 복구
- [x] 3.5 replay에도 현재 native/provider 정책·scope/family·원래 수명 재검증

## 4. 검증과 문서

- [x] 4.1 관련 backend selector/auth/config 및 전체 backend unit 검증, 공유 frontend/gate 차단 명시
- [x] 4.2 실제 Keystone service-reader 비교 및 isolated Uvicorn/Redis rotation smoke
- [x] 4.3 ARCHITECTURE.md, API/deployment/testing docs와 CHANGELOG 갱신; source-only archive, 전체 frontend/gate 차단 및 미래 운영 rollout 별도 명시
- [x] 4.4 정본 Dockerfile backend/frontend/worker 양 architecture build와 격리 실행 결과 기록

## 5. 대시보드와 조회 비용

- [x] 5.1 동일 scope의 token 갱신에서 표시 상태 보존, 실제 identity/scope 변화는 즉시 clear
- [x] 5.2 usage-schedule 중복 요청 병합 및 caller abort와 timeout 동시 적용
- [x] 5.3 async metrics의 동기 호출 제거, 정확한 전체 compute-pool accounting의 제한 병렬화
- [x] 5.4 dashboard 표시 cache TTL을 polling과 정렬하고 강제갱신·mutation invalidation 유지
- [x] 5.5 실제 Chromium에서 갱신 중 표시 유지와 scope clear 증명
- [x] 5.6 user inventory의 native token bytes cache identity 제거, current authority 경계 유지
- [x] 5.7 만료된 탭의 자동 인증 종료는 해당 탭만 정리하고 명시 logout/revocation broadcast 유지

## 6. 사용자가 지정한 세션 정책

- [x] 6.1 access 기본3600초, refresh/원래 로그인 최대604800초 및 config 생성 경로 동기화
- [x] 6.2 native 만료 제약과 기존 짧은 운영 override 반영 조건 명시, 만료/rotation 회귀 검증
