# 작업 체크리스트 (폐기)

이 change의 identity-only 수락 경로는 제거되었습니다. 더 이상 active 계약이 아닙니다.

## 제거된 것

- [x] `native_oidc.py`의 identity-only 헬퍼(`_user_clause_ok`, `_user_remote_ok`, `_group_clause_ok`, `_group_remote_ok`, `_require_identity_only`)와 상수
- [x] `SUPPORTED_SCHEMAS`를 `("2.0",)`으로 축소(schema 1.0 수락 제거)
- [x] `accepts()`는 projects 템플릿을 필수로 요구
- [x] `federate()`·`_mapped_personal_project()`·`retire_deleted_primary_intent()`의 빈 template 가드(죽은 분기)
- [x] `test_native_oidc.py`의 identity-only 테스트 블록과 `configure_identity` 픽스처
- [x] `test_domain_auth.py` `api` 픽스처에서 identity-only 테스트용 필드
- [x] `docs/api/auth.md` identity-only 문단

## 대체

- 새 change `2026-11-11-sso-local-rule-linked-accounts`에서 `type: local` 기존 계정 연결을 추적합니다.
