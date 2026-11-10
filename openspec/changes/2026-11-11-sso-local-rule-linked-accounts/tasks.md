# 작업 체크리스트

## 구현

- [x] `native_oidc._local_identity_reason`: 계정 도메인, 필드, local 규칙(이메일·리터럴 이름) 검사
- [x] `federate()`의 local 분기: 템플릿 조회 생략, 세션 준비 경로 위임
- [x] 공개 `detail` 단일 문구, 사유는 서버 WARNING
- [x] identity-only 경로 제거와 함께 죽은 분기 정리

## 검증 (실행한 것)

- [x] `test_native_oidc.py`의 local 테스트 6개 통과: 정상 연결, 이름 불일치, 도메인 불일치, 규칙에 없는 이메일, 대조군, ephemeral 규칙으로는 local 결과를 설명할 수 없음
- [x] 집중 테스트 355개 통과(`test_native_oidc`, `test_domain_auth`, `test_canonical_federation`, `test_personal_login_defaults`)
- [x] 로컬 Keystone 읽기 전용 점검: 규칙 32의 로컬 계정이 Accounts에 있고 enabled, 이메일 일치, GitLab issuer 바인딩 1개, Personal 프로젝트 1개 소유
- [x] 로컬 callback 1건 HTTP 200 기록(`federated_login` complete, 22:23:21Z)

## 검증 (아직 하지 않은 것)

- [x] `federate()` 수준 테스트(local 토큰을 주는 Keystone 대역): 성공 시 템플릿 조회 생략, 이름·도메인·규칙 불일치는 503과 토큰 revoke. 실제 callback HTTP end-to-end는 아님
- [ ] 최종 트리에서 `npm run test:gate` 전체 실행
- [ ] 로컬 callback 결과의 사용자 본인 확인(pieroot.02@gmail.com 계정으로 대시보드 진입)

## 운영 (승인 전 금지)

- [ ] 운영 Keystone mapping 재등록과 digest 갱신
- [ ] 배포 `native_mapping.sha256` 정렬
- [ ] 배포

## 완료 후

- [ ] 위 미체크 항목이 끝난 뒤에만 `openspec/changes/archive/`로 이동
