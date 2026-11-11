# 운영 native mapping pin을 Kolla mapping 원본에서 유도

## 배경

운영 Afterglow의 native OIDC 가드는 Keystone `sso_oidc_mapping`의 canonical digest를 고정 pin과 비교합니다. 2026-11-11 콜백 503은 운영자 TOML의 pin(`f034e498…`)이 Kolla mapping 원본과 Keystone에 반영된 매핑(`d6238f80…`)보다 늦게 남아 있어 발생했습니다. 로컬 `afterglow.conf`만 갱신되고 배포 pin 정렬이 보류된 것이 직접 원인입니다.

pin을 사람이 따로 옮기는 방식은 같은 장애를 재발시킵니다. 이 change는 pin이 운영자가 관리하는 Kolla `keystone_identity_mappings[].file`에서 유도되도록 하고, 배포 전에 live Keystone과 대조합니다.

## 변경

- `render_effective_config.py`: `pin_native_mappings`가 `auth.providers.*.native_mapping`의 `mapping_id`로 Kolla mapping 원본을 찾아 `{schema_version: "2.0", rules}` canonical digest를 `sha256`으로 넣습니다. 운영 TOML에 `sha256`이 있으면 유도값과 같을 때만 허용하고, 다르면 실패합니다. 원본이 없거나 모호하면 실패합니다.
- `native_mapping_digest`: 백엔드 `native_oidc.mapping_matches`와 같은 직렬화를 사용합니다. `--mapping-digest`는 live Keystone 문서의 digest를 계산하고, `--native-pins`는 검사 대상 pin 목록을 냅니다.
- `effective_config.yml`: 병합 입력에 Kolla `keystone_identity_mappings`를 전달합니다.
- `precheck_native_mapping.yml`: 재기동 전에 `openstack mapping show`로 live 매핑을 읽고, 유도 digest와 다르면 reconfigure를 중단합니다.

## 보안 경계

- 신뢰 기준은 운영자가 관리하는 Kolla mapping 원본입니다. 이 파일은 Kolla가 Keystone에 등록하는 원본이므로, 파일을 바꾸면 Keystone과 pin이 같은 실행에서 함께 바뀝니다.
- live Keystone이 원본과 다르면 precheck가 중단하고, 로그인 가드도 여전히 fail-closed입니다.
- pin을 자동으로 live 값에 맞추지 않습니다. 검증 기준은 원본 파일이며, live 값은 대조 대상입니다.

## 범위 밖

- Keystone mapping 재등록과 digest 변경은 이 change의 배포 범위가 아닙니다. 원본을 바꾸는 작업은 같은 change에서 원본과 Keystone을 함께 갱신합니다.
- GitLab client secret 회전과 두 번째 그룹 규칙의 보안 검토는 별도 결정입니다.
