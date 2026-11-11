# 작업 체크리스트

## 구현

- [x] `render_effective_config.py`: Kolla mapping 원본에서 canonical digest를 유도해 native pin에 넣고, 운영 TOML `sha256`과 다르면 실패
- [x] `native_mapping_digest`: 백엔드 `native_oidc.mapping_matches`와 같은 직렬화로 digest 계산(`schema_version` 2.0만 허용)
- [x] `effective_config.yml`: 병합 입력에 `keystone_identity_mappings` 전달
- [x] `precheck_native_mapping.yml`: 재기동 전 live Keystone 매핑과 유도 digest 대조, 불일치 시 중단. stdin은 `from_json | to_json`으로 고정하고 assert에서 `no_log`를 두지 않음
- [x] 원본 digest parity: 백엔드 가드가 유도 pin을 accepted로 판정
- [ ] 운영 TOML의 `sha256` 키 제거(배포 단계)

## 검증 (실행한 것)

- [x] `backend/tests/test_kolla_native_mapping_pin.py` 신규 7개, `test_kolla_effective_config.py` 기존 테스트 포함 31 passed
- [x] 운영 호스트에서 실제 TOML과 실제 mapping 원본을 읽기 전용으로 렌더 로직에 통과시켜 `d6238f80…`를 얻음(설정 값은 출력하지 않음)
- [x] 운영 호스트에서 `precheck_native_mapping.yml`만 포함한 읽기 전용 ad-hoc playbook(ansible-core 2.19.6, 변경 없음): live `mapping show`, 로컬 digest, assert 모두 통과
- [x] 같은 playbook에 잘못된 12자리 pin을 넣었을 때 assert가 실패해 fail-closed 동작을 확인
- [ ] `npm run test:gate` 전체 통과(현재 로컬 `afterglow.conf` 누수로 host_health·site_branding 3건 실패, 원인 분석 중)
- [ ] 배포 후 controller 3대 컨테이너 내부 read-only 가드 검증
- [ ] 로그인 콜백 status 200 확인(사용자 로그인 필요)

## 배포 순서

1. 1.32.15 wheel 설치 후 운영 TOML에서 `sha256` 제거
2. `reconfigure --limit control --tags afterglow --skip-tags haproxy` 실행 시 precheck가 live 매핑과 유도값을 대조
3. Keystone reconfigure는 이번 배포에서 실행하지 않음. live 매핑은 원본 파일과 이미 같음
4. `schema_version` 2.0이 Kolla `keystone_identity_mappings` 등록 경로에서 실제로 적용되는지는 확인되지 않았으므로, 원본을 바꾸는 후속 변경 전에 확인하고 runbook으로 문서화하지 않음

## 범위 밖

- Keystone mapping 원본 변경과 등록(이번 배포에서는 원본과 live가 같으므로 변경 없음)
- GitLab client secret 회전, 두 번째 그룹 규칙 보안 검토
