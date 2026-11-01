## Why

프로필의 비밀번호 변경은 현재 native 인증 뒤 일반 member 권한으로 거절될 수 있는 Keystone `update_user` 경로를 사용하며, 제공된 로그에서 실제403이 관측됐다. OIDC 등 외부 로그인 사용자는 로컬 비밀번호를 관리할 수 없다.

## What Changes

- 기존 비밀번호를 확인하는 native self-service 변경 경로와 정확한 identity/home 경계를 검증한다.
- 외부 계정의 최초 비밀번호 생성은 신뢰할 수 있는 소유 증명과 기존 credential 보존 조건을 충족할 때만 허용한다.
- 사용자 선택: Keystone 측 원자적 최초 생성으로 기존 native password 덮어쓰기를 금지한다. 로컬 password 로그인이 외부 IdP MFA/비활성화 통제를 우회할 수 있음을 명시하고, 짧은 수명의 본인 소유 증명과 운영자 password 정책을 적용한다.
- Native endpoint가 설치·검증되기 전에는 생성 기능을 허용하지 않는다. Direct native writer를 포함한 동시성·재생성·불명 결과를 검증하며 Keystone 배포는 별도 승인이다.
- 프로필 화면, API 설명, 회귀 검증을 실제 가능한 권한 및 증명 모델에 맞춘다.
- 2026-10-30 사용자 요구: password 로그인 사용자의 변경 기능은 관리자 directory·SMTP·최초 생성 확장의 가용성과 분리한다. 외부/매핑 계정은 실제 native password history로 존재·부재를 구분하며 stale metadata로 기존 비밀번호를 덮어쓰지 않는다.
- 등록 메일의 일회용 링크로 기존 비밀번호를 복구하고 본인 프로필에 분실 안내·관리자 문의를 제공한다. 외부 never-password 계정은 공개 reset으로 최초 생성의 새 provider 본인 증명을 우회하지 않는다.
- 새 관리자 명시 동작은 암호학적 난수로 exact native 사용자 비밀번호를 변경하고 등록된 유일한 메일로 자동 전송한다. 메일함에 credential이 남는 위험을 안내하고 응답·로그·DB·감사에는 password를 남기지 않는다. Native 변경·메일 전달·세션 회수 결과를 구분하며 자동 재전송/rollback은 없다. 강제 첫 로그인 만료를 구현한 것으로 표현하지 않는다.

## Capabilities

### New Capabilities
- 외부 로그인 계정의 안전한 로컬 비밀번호 생성.

### Modified Capabilities
- 일반 사용자의 본인 비밀번호 변경.

## Impact

프로필 API, Keystone transport, 프로필 화면과 다국어 안내, 관련 테스트 및 문서. 공유 운영 계정·인증정보·DB·배포는 변경하지 않는다.
