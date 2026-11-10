# 작업 체크리스트

## 구현

- [x] `files/merge_toolbox_clouds.py`: 단일 cloud 항목 병합, 파싱 실패 시 fail-closed, 동일 내용 `unchanged`
- [x] `tasks/toolbox_cli_auth.yml`: 덮어쓰기 대신 헬퍼 호출
- [ ] `docs/deployment.md`에 toolbox clouds.yaml 병합 계약과 태그 주의(afterglow role 재실행 금지 기간) 기록
- [ ] ARCHITECTURE.md의 Kolla afterglow role 설명 갱신

## 검증 (실행한 것)

- [x] `pytest tests/test_kolla_toolbox_clouds_merge.py` — 8 passed (sibling 보존, 파일 없음, 동일 내용, malformed/비정상 구조 fail-closed, 잘못된 입력 거부)
- [x] `pytest tests/test_kolla_toolbox_clouds_merge.py tests/test_kolla_effective_config.py` — 32 passed
- [x] `main()` 임시 디렉터리 실행: 1회차 `changed`, 2회차 `unchanged`, `kolla-admin-internal` 보존 확인
- [x] `ruff format` / `ruff check` 두 파일 통과
- [x] `toolbox_cli_auth.yml` YAML 파싱 통과

## 검증 (아직 실행하지 않은 것)

- [ ] `ansible-playbook --syntax-check` 또는 `ansible-lint`(Ansible 실행 환경 필요)
- [ ] 실제 kolla_toolbox 컨테이너에서 헬퍼 실행(개발 환경 toolbox 없음, 운영 금지)
- [ ] controller2·3 toolbox의 `clouds.yaml` 구성 확인(읽기 전용)
- [ ] `npm run test:gate` — 미실행

## 운영 (승인 전 금지)

- [ ] 패치 배포
- [ ] 이미 덮어쓰인 운영 `clouds.yaml` 복구와 `kolla` 항목 병합
- [ ] Afterglow role 재실행(`deploy`/`reconfigure`/`upgrade`, 태그 없음 또는 `--tags afterglow`)

## 완료 후

- [ ] 위 미체크 항목이 끝난 뒤에만 `openspec/changes/archive/`로 이동
