# 작업 체크리스트

## 구현

- [x] `files/merge_toolbox_clouds.py`: clone configured Kolla auth cloud, overlay password-only or full auth overrides, preserve sibling clouds, fail closed on missing/invalid source
- [x] `tasks/toolbox_cli_auth.yml`: prepare each Afterglow controller toolbox, not only first controller
- [x] Direct `openstack.cloud` calls pass both `auth` and `cloud: openstack_auth_cloud`; installed `service-ks-register` already passes both
- [x] Update deployment and architecture documentation for Kolla 2026.1 auth/cloud contract

## 검증 (실행한 것)

- [x] `npm run test:target -- backend:tests/test_kolla_toolbox_clouds_merge.py` — 12 passed
- [x] `uv run ruff check` / `uv run ruff format --check` — helper와 test 통과
- [x] PyYAML으로 변경한 Ansible task 3개 파싱 통과
- [x] 임시 toolbox 파일에서 `main()` 쓰기·0600 권한·반복 실행 idempotency 통과
- [x] Root wheel `afterglow_kolla-1.32.14-py3-none-any.whl` 빌드, 수정 role payload 포함 확인
- [x] Disposable MariaDB 10.11.19에서 migration 110, multi-grant, duplicate guard, dump restore, 재적용 통과
- [x] Production DB read-only preflight: MariaDB 10.11.19, InnoDB, `grant_id NOT NULL`, legacy PK, 2 rows, duplicate groups 0
- [x] Architecture freshness: stamp, `npm run docs:check`, staged check 통과
- [x] `PATH=/Users/pieroot/code/afterglow/backend/.venv/bin:$PATH npm run test:gate` — full gate 통과

## 검증 (아직 실행하지 않은 것)

- [ ] `ansible-playbook --syntax-check` — local Ansible 미설치
- [ ] 1.32.14 tag-triggered CI, images, aliases, Helm chart 발행 검증
- [ ] Full Kolla precheck/reconfigure, schema cutover, runtime health and Manila API acceptance

## 운영 (승인 전 금지)

- [ ] 패치 배포
- [ ] 이미 덮어쓰인 운영 `clouds.yaml` 복구와 `kolla` 항목 병합
- [ ] Afterglow role 재실행(`deploy`/`reconfigure`/`upgrade`, 태그 없음 또는 `--tags afterglow`)

## 완료 후

- [ ] 위 미체크 항목이 끝난 뒤에만 `openspec/changes/archive/`로 이동
