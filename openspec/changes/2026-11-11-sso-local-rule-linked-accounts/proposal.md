# type: local 규칙으로 기존 Accounts 계정 연결

## 배경

pinned `sso_oidc_mapping`(schema 2.0)의 이메일 조건 규칙 33개는 `user.type: local`이고 이름은 리터럴입니다. Keystone은 이 규칙에 걸리면 기존 로컬 계정의 토큰을 주고 `OS-FEDERATION` 블록을 생략합니다. 기존 `native_oidc.federate()`는 ephemeral 전용이라 이 결과를 `native_mapping_unsafe`로 거부했고, Horizon은 같은 결과를 그대로 쓰므로 정상이었습니다. 운영자는 특정 이메일을 특정 Accounts 계정에 묶으려고 이 규칙을 두었습니다.

## 변경

- `native_oidc._local_identity_reason(native, identity, descriptor, ks)`: `OS-FEDERATION`이 없을 때 다음을 모두 확인합니다.
  1. 사용자 도메인이 `account_domain_id`와 같다.
  2. 고정된 mapping에 같은 이메일을 가진 `OIDC-email` 조건과 같은 리터럴 이름의 `user.type: local` 규칙이 있다.
- `federate()`: local 결과이면 기존 `_email_user` readback(계정 도메인·이메일·외부 subject 바인딩)을 그대로 적용하고, mapped `<username>-project` 템플릿을 조회하지 않으며, 비밀번호 로그인과 같은 세션 준비 경로로 Personal primary를 확인합니다.
- 공개 응답은 `native_mapping_unsafe` 한 문구이고, 구체 사유는 서버 WARNING 로그에만 남깁니다.

## 보안 경계

- 신뢰 근거는 digest로 고정된 mapping입니다. 이름·이메일 매칭은 mapping 규칙 자체와 일치해야 하며, ephemeral 규칙으로는 local 결과를 설명할 수 없습니다.
- 다른 도메인 계정, 다른 이름, 규칙에 없는 이메일은 거부합니다.
- 연결 계정의 Personal 프로젝트를 GitLab username 템플릿으로 찾거나 채택하지 않습니다.

## 범위 밖

- Keystone 운영 mapping 재등록(ID 참조 형태, digest 갱신)과 배포 pin 정렬은 운영 승인 대상입니다.
- 두 번째 그룹 규칙의 허용 여부는 별도 보안 결정입니다.
