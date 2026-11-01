## Why

운영(dmslab Kolla, 2026-10-31) 측정에서 인증이 필요한 모든 Afterglow API가 단순 조회도 p50 2.5–7s였고, 인증 없는 endpoint는 6–10ms였다. Keystone access log의 `POST /v3/auth/tokens` p50은 451ms였고, 운영 backend 안에서 서비스 계정 password 인증을 직접 재면 305–781ms였다. `keystone._get_admin_ks_client()`가 호출마다 새 `v3.Password` 플러그인을 만들기 때문에 `NativeOperation` 하나, 단독 호출 하나마다 서비스 계정 password 로그인이 다시 일어난다. Redis 응답 캐시는 이 인증 단계 뒤에서만 조회되므로 hit여도 체감 속도가 거의 바뀌지 않았다.

같은 기간 Valkey Sentinel failover가 3회 있었고, redis-py 클라이언트에 재시도가 없어 failover 직후 세션 조회가 503이 되었다. refresh rotation은 이전 JTI를 즉시 삭제하므로 서버가 commit한 응답이 브라우저에 도달하지 못하면 다음 refresh가 401(terminal logout)이 된다.

## What Changes

- 서비스 계정 Keystone 토큰을 프로세스 안에서 공유한다. 호출자마다 독립 Session/Client를 유지(native_transport 계약)하되, 인증 플러그인은 공유 캐시에서 AccessInfo를 받는다. 만료 임박 시 lock 아래에서 한 번만 재인증하고, 401로 invalidate되면 그 토큰일 때만 폐기한다. 사용자 권한 관측(role assignment, membership, system admin)은 여전히 요청마다 live로 읽는다.
- Redis/Valkey 직접·Sentinel 클라이언트의 안전한 읽기만 bounded retry한다. 쓰기/EVAL은 응답 유실 뒤 이미 commit되었을 수 있으므로 일반 재시도를 금지한다. Refresh rotation만 동일 요청 receipt로 idempotency를 증명하고 재시도한다.
- refresh rotation과 30초 replay receipt를 같은 Lua commit으로 발행한다. 정확한 후속 세션/가족/범위/수명·출처 바인딩과 현재 native/provider 권한을 재검증한 뒤 이미 발급된 동일 응답만 재전달한다. 동시 갱신 패자·응답 유실을 복구하되 로그인 수명을 연장하지 않는다.
- 동일 로그인·사용자·도메인·프로젝트에서 token만 바뀌면 대시보드 표시 데이터를 보존한다. 실제 scope/권한 전환은 기존대로 즉시 무효화하며, 중복 usage-schedules 조회를 병합하고 caller abort와 timeout을 함께 적용한다.
- async metrics 핸들러의 동기 Nova 호출을 분리하고 project-pool 조회의 순차 native I/O를 안전한 제한 병렬화로 바꾼다. 인가/admission 결과를 캐시하지 않고 dashboard 표시용 데이터 TTL만 폴링에 맞춘다.
- 사용자가 명시한 access token 1시간, refresh 및 로그인 원래 시작 기준 최대7일 정책을 source/config 생산 경로에 반영한다. Native token 만료·폐기를 우회하지 않으며 native 수명 제약과 운영 override는 별도 명시한다.

## Non-goals

- 사용자 Keystone 토큰(unscoped/scoped) 교환 결과 캐시: 권한 회수 반영 지연이라는 보안 경계 변경이므로 별도 결정.
- 운영 배포, Keystone/Valkey 운영 설정 변경.
