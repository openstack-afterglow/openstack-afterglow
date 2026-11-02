# Tasks

## 0. 즉시 안전 수정 (source)

- [x] 0.1 실패 원인 확인: Afterglow 502 `outcome_unknown` ↔ Keystone 500 `local_user.name` NULL IntegrityError(controller3 `keystone.log.1`, 2026-11-02 06:42:55), 대상 federated shadow 사용자
- [x] 0.2 `admin_password_reset._subject`: marker 없는 federated 계정 409 `admin_password_reset_external_account`, fence·native·세션 폐기 전 거부
- [x] 0.3 Backend 테스트(`test_admin_password_reset.py` 54 passed), frontend 매핑·9개 locale(159 passed), CHANGELOG

## 1. 사전 준비 (변경 없음)

- [x] 1.1 읽기 전용 운영 관측 기록(proposal 표)
- [ ] 1.2 Keystone 28.0.3.dev6 → 28.1.0 차이(DB migration 유무·policy·token 변경) 검토, `keystone-manage db_sync --check` 결과를 격리 환경에서 확인
- [ ] 1.3 Native writer inventory 확정: keystone(3), keystone_httpd/fernet/ssh, `keystone_accounts_personal` bridge, Afterglow backend/worker(로컬 포함), CLI/admin 자동화, 직접 DB writer
- [ ] 1.4 운영 Keystone/Afterglow DB snapshot·현재 image digest·config 보존 경로와 rollback 절차 문서화
- [x] 1.6 Kolla 현황(읽기 전용): `globals.yml`에 `keystone_image`/`keystone_tag` override 없음(`openstack_release: 2025.2`), keystone override는 `/etc/kolla/config/keystone/keystone.conf` 존재
- [x] 1.7 관리자 reset 차단 영향: 운영 사용자 68명 중 federated 3명, 모두 marker 없음 → 모두 409(로컬 password 보유 여부는 stock API로 판별 불가. `users.list(name=)`은 shadow 사용자도 포함하므로 근거로 사용 불가)
- [ ] 1.5 보안 정책 승인: SSO 사용자 local password 허용(GitLab MFA·계정 비활성화 우회), recovery owner 지정

## 2. Artifact

- [ ] 2.1 `v1.31.4` asset sha256 `0a1f3e20…`·image ID `cff27763…`·linux/amd64·manifest(keystone 28.1.0, wheel sha256) 재검증
- [ ] 2.2 수동 workflow `publish_native_keystone=true`로 `ghcr.io/<owner>/keystone-first-password` digest 발행, digest 기록

## 3. 격리 qualification (운영 무변경)

- [ ] 3.1 MariaDB 10.11.19 3-node Galera 격리 환경 + 운영 Keystone DB snapshot 복제본
- [ ] 3.2 offline schema CLI 검증 모드 → `--apply`, trigger/guard/권한(writer·auditor 분리) 확인
- [ ] 3.3 multi-node 동시 first-create·일반 password writer 경합, federation/email ABA, 삭제·재생성, 응답 유실·회수 실패, member churn, schema tamper, 기존 self-service 변경 시나리오 통과
- [ ] 3.4 Afterglow(103 적용) ↔ 확장 end-to-end: capability `supported:true`, 프로필 "비밀번호 만들기", 메일 proof, 새 SSO 세션, 로그인 확인

## 4. 운영 cutover (단계별 승인 필요)

- [ ] 4.1 Afterglow migration 103 적용(`afterglow_kolla`, additive) — 확장과 별개로 선행
- [ ] 4.2 점검창 공지, 모든 native writer drain·중지, pending recovery proof drain/만료
- [ ] 4.3 Keystone DB snapshot 후 **Kolla inventory에 영속화**: `/etc/kolla/globals.yml`에 `keystone_image`/`keystone_tag`(발행 digest 고정) 기록, `[afterglow_initial_password]`는 기존 `/etc/kolla/config/keystone/keystone.conf` override(secret DSN은 passwords.yml/vault 참조)에 추가. 수동 `docker` 교체 금지 — `kolla-ansible deploy/reconfigure -t keystone`으로 3 controller 동일 digest 반영
- [ ] 4.4 Native schema CLI 검증 → `--apply`, 각 member 대조
- [ ] 4.5 Keystone 기동·capability 확인 후 bridge·Afterglow 재개(단일 writer 원칙 유지)
- [ ] 4.6 `test-bong`으로 실제 최초 비밀번호 생성·로그인·세션 회수 acceptance, 증거 저장
- [ ] 4.7 영속성 검증: 승인된 범위에서 `kolla-ansible reconfigure -t keystone`(또는 동등 dry-run/check) 이후 3 node image digest·config·`GET /v3/OS-AFTERGLOW/initial-password/capabilities` 200이 유지되는지 확인. Stock image/config로 되돌아가면 native schema만 앞선 상태가 되므로 이 확인 전 활성화 수용 금지

## 5. 문서

- [ ] 5.1 `docs/deployment.md`에 운영 관측(28.0.3.dev6, 103 미적용, bridge writer)과 실행 결과 반영, ARCHITECTURE 갱신
