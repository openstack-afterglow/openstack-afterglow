## Why

프로젝트 role 편집이 대상 사용자의 모든 refresh family와 Keystone credential을 폐기하여, 본인 권한을 조정하는 동안 반복적으로 강제 로그아웃된다. 사용자는 원래 다음 로그인부터 반영을 요청했지만 보안 tradeoff 설명 후 **로그인은 유지하고 새 요청에는 현재 권한을 적용**하는 방식을 명시적으로 선택했다.

## What Changes

- 로그인 증명을 프로젝트 role에서 분리한다. Redis `keystone_token`에는 caller의 검증된 native unscoped credential을 저장하고, 실제 provider 요청에는 현재 프로젝트로 새로 검증한 native token만 사용한다. 시스템/서비스 계정 credential로 사용자 세션을 대체하지 않는다.
- 비밀번호/federated 로그인, access 검증, refresh, 프로젝트/작업 도메인 전환에서 이 불변성을 유지한다. 기존 유효한 scoped 세션도 첫 요청의 native unscoped exchange를 통해 전환하며 별도 schema/migration은 없다.
- 프로젝트 role 직접/그룹 할당과 멤버 role 교체는 로그인 family를 삭제하지 않고 권한/프로젝트/토큰 검증 cache를 무효화한다. 추가·축소 뒤 다음 요청은 현재 Keystone 할당을 사용한다.
- 프로젝트 접근만 회수되면 인증 실패(401)와 구분하여 403으로 거절하며, 유효한 로그인 증명은 남는다. Refresh는 더 이상 접근할 수 없는 프로젝트 권한을 재발급하지 않는다.
- 비밀번호 변경, 계정 비활성화, provider/domain policy 차단, 절대 세션 만료, 명시적 개별/전체 세션 폐기의 기존 fail-closed 경계를 보존한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- Project role editing preserves authentication without preserving removed authority.
- Native authentication credentials and per-request project credentials have distinct lifetimes and storage boundaries.

## Impact

`backend/app/api/deps.py`, `backend/app/api/identity/auth.py`, native Keystone/session handling, identity/project role cache invalidation, affected authentication and membership regressions, auth/project API docs and architecture review. DB schema, configuration, dependencies, role graph definitions, production IAM and deployment are unchanged. Shared dev checkout/index and unrelated concurrent changes are preserved. Verification uses isolated native-provider fixtures, real HTTP smoke, focused auth/access tests and documented evidence boundaries; no production role mutations or deployment are authorized.
