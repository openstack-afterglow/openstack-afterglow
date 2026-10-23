## Why

운영 backend 설정에 현재 v1.30.24가 소비하지 않는 `[gitlab_oidc]`가 남아 `default_domain` 이름과 과거 `/auth/gitlab/callback`을 실제 설정으로 오인하게 한다. 사용자는 dmslab 선택을 immutable Keystone domain ID로 관리하도록 요청했다. 실제 `[auth.domain."3de8d34d778e423ab7a92a4992378583"]`는 이미 정확한 파일 공급자와 mapped protocol을 선택한다.

## What Changes

- 운영자 source의 obsolete `[gitlab_oidc]`만 보호된 백업·동시 변경 fence 아래 제거한다. 기존 `[auth]` 전체와 다른 모든 TOML 값은 그대로 보존한다.
- 실제 domain-ID selector, provider client/secret/protocol, callback과 현재 이미지의 effective settings가 동일함을 실행 검증한다. Source 정리만으로 불필요한 service restart나 배포를 수행하지 않는다.
- 구형 default_domain/domain_protocols는 지원 경로가 아니며 현재 registry의 canonical domain ID와 generic callback을 사용한다는 운영 문서를 보완한다.
- 사용자 오류는 GitLab의 redirect URI 등록 거부다. 필요한 정확한 callback을 제시하되 접근할 수 없는 GitLab 앱의 등록값을 읽거나 수정했다고 주장하지 않는다.

## Capabilities

### New Capabilities

없음. 기존 domain-ID 기반 설정을 재사용한다.

### Modified Capabilities

없음. 인증·identity home·membership·provider trust·callback 보안 계약은 변경하지 않는다.

## Impact

운영 private 설정의 사용하지 않는 블록과 공개 운영 문서만 정리한다. 새 source/image/version/schema/dependency, native IAM/resource/quota 변경이나 credential rotation은 없다. 원본 설정은 0700 디렉터리의 0600 백업으로 보존하며 비밀은 출력하지 않는다. GitLab 앱 등록 확인·변경과 실제 사용자의 최종 OIDC callback은 수용 범위 밖으로 명시한다.
