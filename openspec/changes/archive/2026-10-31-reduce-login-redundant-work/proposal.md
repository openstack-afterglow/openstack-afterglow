## Why

로그인 분석에서 refresh 뒤 /me 재검증과 token-keyed 표시 조회, 연장되지 않는 lifecycle 회전, request-local 정책/metadata 재조회와 개인 공간/비밀번호 계정 탐색의 과도한 native 조회를 확인했다. 사용자는 보안 경계를 유지하며 줄일 수 있는 부분 모두를 우선 줄이도록 요청했다.

## What Changes

- 완전한 exact-owner refresh 응답만 verified continuation으로 적용하고 restored/raw/rescope 검증 경계를 보존한다.
- 표시용 tutorial/project 조회를 논리 세션·범위 기준으로 소유하며 실제 권한 조회는 유지한다. 연장 불가 선제 lifecycle 회전은 preflight와 같은 억제를 공유하되401/expiry/명시복구를 보존한다.
- 백엔드는 현재 native/provider/domain 보장을 유지하면서 같은 요청·동일 검증 단계의 정책·표시 metadata 조회를 재사용한다. mutation/authority invalidate를 넘어 verdict를 cache하지 않는다.
- 개인 공간·canonical 계정 탐색에서 같은 검증 구간의 catalog/directory 조회 및 불필요한 잠금 구간 작업을 축소한다. 안전한 read-only 경로가 현재 계약상 증명되지 않으면 생성/복구 lock이나 유일성 검증을 제거하지 않고 증거와 유지 이유를 기록한다.
- Replay도 현재 native can_write·조직 생성 flag·정규화된 domain metadata·identity/workspace 표시명을 재대조해 완전한 refresh proof의 현재성을 보장한다. 변경 시401이며 동일 receipt만 같은 응답으로 복구한다. Proactive skip-only는 실제 갱신의 single-flight를 점유하지 않고 실패한 tutorial은 다음 token 갱신으로 재시도할 수 있다.

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
기존 로그인·refresh·세션 검증·표시 데이터 조회의 실행 비용을 줄인다. 실제 본인·home·scope·provider revision·membership·blacklist·deadline·origin·rotation CAS/replay·late response fences는 유지한다.

## Impact
프런트 auth lifecycle/store, backend authentication/personal-account services, 관련 회귀 및 architecture/testing 문서. 새 schema/dependency/config·권한 cache·비밀번호/공급자/운영 변경·배포는 없다. 성능은 실제 synthetic 실행의 요청/조회 수와 관측으로만 주장하며 앞선 실제 로그인 latency를 새 성능 결과로 재사용하지 않는다. 공유 dev/index를 보존한다.

새 frontend의 `/me` 생략은 새 replay 검증 backend 전체 전환 후에만 제공한다. 기존 frontend+새 backend는 유지되지만 구 backend+새 frontend 혼용은 stale replay capability 위험으로 지원하지 않는다. 이 paired source 경계를 문서화하며 실제 배포는 별도 승인이다.
