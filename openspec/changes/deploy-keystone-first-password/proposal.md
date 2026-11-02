# SSO 계정 최초 비밀번호: Keystone first-password 확장 운영 배포 계획

## Why

GitLab OIDC로만 연결된 shadow 사용자(예: `test-bong`, Accounts domain)는 local password가 없어 현재 비밀번호를 알 수 없습니다. 2026-11-02 관리자 난수 재설정은 stock Keystone `PATCH /v3/users/{id}`에서 500으로 실패했습니다. Keystone 28 `User.password` setter가 federated 사용자에게 `LocalUser()`를 만들고 이름은 federated display name으로만 가므로 `local_user.name` NULL IntegrityError가 납니다(transaction rollback, password 미변경). Stock API로는 이런 계정에 최초 local password를 만들 수 없습니다.

Afterglow는 이를 위해 본인 메일 proof + 15분 이내 새 SSO 세션을 요구하는 프로필 "최초 비밀번호 만들기"를 이미 구현했고, native 쪽은 `services/keystone-first-password`(API revision `first-password-galera-v2`) 확장이 담당합니다. 운영 Keystone에는 확장이 없어 `GET /v3/OS-AFTERGLOW/initial-password/capabilities`가 404이고 프로필은 "실제 비밀번호 상태를 확인하지 못했습니다"를 표시합니다.

사용자는 2026-11-02 이 확장의 **배포 계획 수립**을 선택했습니다. 이 change는 계획·사전 관측·즉시 안전 수정만 다루며 운영 Keystone/DB 변경은 각 단계별 별도 승인 후에만 수행합니다.

## 2026-11-02 읽기 전용 운영 관측

| 항목 | 관측 | 계획 영향 |
|---|---|---|
| Keystone image (controller1~3) | `quay.io/openstack.kolla/keystone:2025.2-ubuntu-noble`, image ID `sha256:954238ea…` | `release-image.json` `base_image_id`와 동일 → 검증된 base 위 빌드 |
| 실행 Keystone 버전 | `28.0.3.dev6` | 확장은 `keystone==28.1.0` wheel 고정 → **배포가 Keystone 28.0.3.dev6→28.1.0 교체를 포함** |
| 확장 모듈 | 3 node 모두 `afterglow_keystone_first_password` 없음 | 신규 설치 |
| 발행 asset | release `v1.31.4`에 `native-v2-paired-build2-amd64.tar.gz` (sha256 `0a1f3e20…`, image `cff27763…`) | GHCR 발행 전 재검증 대상 |
| MariaDB/Galera | `10.11.19`, size 3, Primary, Synced, ready ON | validator 지원 범위와 일치(배포 시점 재확인) |
| Afterglow DB `afterglow_kolla` | `account_recoveries.native_identity_revision` **없음**(103 미적용) | 현재 v1.32.0 backend ORM도 이 컬럼을 SELECT → recovery 조회 경로 잠재 실패. 103은 확장과 무관하게 선행 필요 |
| 추가 native writer 후보 | `keystone_accounts_personal`(accounts personal bridge, controller에서 실행) | writer inventory·drain 대상 |
| 무관 오류 | `PATCH /domains/3de8d34d…`에 `afterglow_compute_pool` extra 포함 시 schema 400 반복 | 별도 조사(이 change 범위 밖) |

## What Changes

1. **즉시 안전 수정(source, 완료):** 관리자 난수 재설정은 `afterglow_local_password=true`가 없는 federated 계정을 감사 fence·native 쓰기·세션 폐기 전에 `409 admin_password_reset_external_account`로 거부하고 9개 언어 안내를 표시합니다. **의도된 동작 변경:** 실제 local password가 있지만 marker가 없는 legacy 연결 계정도 거부됩니다. Stock Keystone은 shadow 사용자와 구분할 근거를 주지 않으며(name filter 목록은 shadow 사용자를 포함) 2026-11-02 운영 federated 3명이 모두 이 범주입니다. 확장 배포 후에는 native `password_state`로 판별할 수 있습니다.
2. **운영 배포 계획:** `docs/deployment.md` "프로필 password·native first-password guard" 절의 1~6단계를 현재 운영 관측에 맞춘 실행 checklist로 고정합니다(tasks.md). 핵심 결정:
   - Afterglow migration 103을 먼저 적용(additive nullable 컬럼, 별도 승인).
   - Keystone 28.1.0+확장 immutable image를 **격리 환경에서 qualification** 후, 3 controller 전체를 동시에 전환하는 점검창 cutover(rolling mixed-version 미지원).
   - Native schema(`schema.sql`, guard·trigger)는 모든 Keystone/bridge/Afterglow writer 중지 상태에서 offline CLI로 검증 후 `--apply`.
   - 활성화 전 보안 정책 승인: local password는 GitLab MFA·계정 비활성화를 우회하는 별도 로그인 경로.

## Non-goals

- Keystone DB에 직접 local_user/password를 넣는 일회성 우회.
- 운영 Keystone/DB/Afterglow 배포 자체(각 단계 승인 후 별도 수행).
- domain PATCH schema 오류 수정.

## Risks

- Keystone 버전 교체(28.0.3.dev6→28.1.0)는 password 외 전체 identity/token 경로에 영향 → 격리 qualification·rollback image 보존 필수.
- Native DDL은 AUTOCOMMIT/TOI로 rollback이 없음 → 부분 실패 시 writer 전체 중지 유지, snapshot 기반 복구.
- 기존 pending recovery proof(NULL revision)는 새 reader가 410으로 거부 → cutover 전 drain/만료.
