# SSO 로그인을 identity-only native mapping으로 수락

## 배경

운영 Keystone의 `sso_oidc_mapping`은 `schema_version 1.0`이며 `projects` 절이 없습니다. Accounts 사용자(`name: {0}`, `email: {1}`)와 조건부 그룹 절(`groups: {0}`, `HTTP_OIDC_EMAIL_VERIFIED` 조건)만 있습니다. Afterglow의 `native_mapping` pin 경로는 Personal project 템플릿을 필수로 요구하고 schema `2.0`만 수락해서, 이 mapping을 권한 원천으로 쓰면 SSO 로그인이 `native_mapping_unsafe`(503)로 거부되었습니다. 비밀번호 로그인은 정상입니다.

## 목표

- 붙여 넣은 mapping 자체를 권한 원천으로 유지합니다. mapping 내용은 바꾸지 않습니다.
- pin digest(canonical `{schema_version, rules}` SHA-256)가 같을 때만 수락합니다.
- `projects`·`roles`·무조건 그룹·추가 규칙이 있으면 계속 거부합니다.
- Personal project는 mapping이 만들거나 채택하지 않고, 비밀번호 로그인과 같은 세션 준비 경로가 확인하거나 생성합니다.

## 변경 요약

- `backend/app/services/native_oidc.py`
  - `SUPPORTED_SCHEMAS = ("1.0", "2.0")`; digest pin 검사는 그대로 유지합니다.
  - `_has_projects`로 `projects` 절이 있으면 기존 Personal 템플릿 경로, 없으면 `_require_identity_only`를 탑니다.
  - `_require_identity_only`는 정확한 사용자 절(ephemeral, `{0}`/`{1}`, Accounts)과 서명 claim 조합, 선택적 조건부 그룹 절만 허용합니다.
  - `federate()`와 `_mapped_personal_project()`는 identity-only일 때 Personal project 조회·채택을 건너뜁니다.
- `backend/tests/test_native_oidc.py`: 라이브 shape 수락, 로그인 시 Personal project·grant 미생성, grant 형태 drift 거부(재 pin 후에도), pin 후 변경 거부 테스트 8개 추가.
- `docs/api/auth.md`: identity-only 형태와 pin 요구, 그룹 절의 보안 참고 추가.

## 범위 밖

- 배포 Keystone pin(`[auth.providers.dmslab_gitlab_domain.native_mapping].sha256`)과 배포 `afterglow.conf`: 운영 변경이므로 운영자 승인 후 같은 digest로 갱신해야 합니다. 이 change에서는 로컬 `afterglow.conf`만 갱신했습니다.
- 두 번째 그룹 규칙(`dmslab` 도메인 그룹을 Accounts 사용자에게 부여): 보안 정책 결정이 필요합니다. 이 change는 mapping이 권한 원천이라는 요구에 따라 허용하고, 문서에 검토 의무를 명시합니다.
- Lumen 암호화 키 불일치(`.env` `LUMEN_ENCRYPTION_KEY`): 별도 change로 다룹니다.
