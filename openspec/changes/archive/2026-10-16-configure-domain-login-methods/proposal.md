## Why

운영자는 Keystone federation과 Afterglow 로그인 버튼을 별도로 설정한다. 현재 Afterglow의 공급자 설정은 도메인 IAM의 SQL CRUD에만 있으며, `afterglow.conf`에는 공통 공급자와 도메인 전용 공급자를 선언하는 방법이 없다.

## What Changes

- `[auth.providers.<key>]`에 기존 OIDC/GitHub OAuth 흐름과 같은 연결 정보를 선언한다. GitLab은 `kind = "oidc"`, issuer는 `https://git.dmslab.re.kr` 형식을 사용한다.
- `[auth.default] providers = [...]`는 모든 활성 도메인에 추가하고, `[auth.domain."<canonical Keystone domain ID>"] providers = [...]`는 해당 도메인에만 추가한다. 공통 목록 → 도메인 목록 순서, 중복 제거, disabled 공급자 제외. 선택하지 않은 공급자는 공개하거나 직접 authorize할 수 없다.
- 파일 설정은 기존 SQL 공급자를 지우거나 로그인/이메일/회원가입 정책을 대체하지 않는다. 비밀번호 정책·DB 장애 fail-closed·native user의 정확한 도메인/IdP/protocol 검증을 유지한다. Keystone 설정은 읽기/로그인만 하며 생성·수정하지 않는다.
- 파일 공급자는 `cfg:<key>` 식별자를 사용하고 기존 authorize/callback/refresh 경로에서 재검증한다. 보안 설정/secret 변경은 revision fingerprint를 바꿔 진행 중 state와 provider-bound refresh를 거부한다. 파일 공급자의 성공 검증은 SQL provider의 검증 stamp/last-method guard로 오인하지 않는다.
- 기존 도메인 우선 로그인 UI가 합성된 API 목록을 그대로 표시한다. 프론트엔드에 별도 공급자 목록을 추가하지 않는다.
- K8s는 공급자 비밀을 `AUTH__PROVIDERS__<KEY>__CLIENT_SECRET` 환경 변수로 Secret에 분리하고 비밀 없는 auth 구조만 ConfigMap에 보존한다.

## Capabilities

### New Capabilities

- 선언적 공통/도메인별 로그인 공급자 선택과 배포 설정 round-trip.

### Modified Capabilities

- 도메인 조회, authorize, callback 및 세션 refresh가 파일 공급자도 도메인에 묶어 검사한다.

## Impact

- Backend configuration/service와 K8s renderer, 예시·인증 문서·architecture/changelog를 갱신한다.
- DB schema/migration 및 기존 API 응답 형식은 바꾸지 않는다. 운영 DB/Keystone 변경이나 배포, commit/push는 범위 밖이다.
- 실제 API/브라우저 smoke는 격리된 synthetic native/IdP 경계로 확인하고 실제 GitLab/Keystone 연동 성공과 구분한다.
