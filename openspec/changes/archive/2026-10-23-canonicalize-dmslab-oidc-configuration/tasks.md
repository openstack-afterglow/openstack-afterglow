## Implementation Tasks

- [x] 현재 source·운영 image·operator source를 확인하고 구형 gitlab_oidc가 무효이며 exact dmslab ID registry가 실제 선택됨을 확인한다.
- [x] 보호된 원본 백업과 exact-byte 동시 변경 fence 아래 obsolete section만 제거하고 나머지 모든 TOML 값·mode/owner를 보존한다.
- [x] 실제 이미지에서 정리 전후 effective settings의 완전 동일성과 exact native domain·공개 provider·callback surface를 확인한다. 서비스 재시작·native mutation은 하지 않는다.
- [x] auth/deployment/architecture/changelog에 설정 이관·GitLab 등록 및 미검증 경계를 기록한다. Architecture guard를 통과하고 normative spec 변경 없는 설정 정리로 --skip-specs archive한다. Strict delta 검증은 delta 부재로 거부되었으며 통과로 보고하지 않는다.
