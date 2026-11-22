# 작업 체크리스트

## 구현

- [x] Keystone reachability task를 분리해 v3 version document (200)와 v3 discovery entry (300)를 검증한다.
- [x] 비-Keystone 300, 5xx, 연결 오류가 계속 실패한다는 runtime 회귀를 추가한다.
- [x] 한·영 배포 안내, CHANGELOG, ARCHITECTURE review summary를 갱신한다.

## 검증

- [x] `PATH=deploy/kolla/operator/.venv/bin:$PATH node --test scripts/kolla-runtime-contract.test.js` — 62 passed, 0 failed.
- [x] `PATH=deploy/kolla/operator/.venv/bin:$PATH npm run test:kolla:contract` — `scripts/kolla-contract.test.js` 29 passed; image resolver 13 passed; Cloud Shell 3 passed.
- [x] `ANSIBLE_ROLES_PATH=ansible/roles operator/.venv/bin/ansible-playbook -i 'localhost,' -c local playbooks/afterglow.yml --syntax-check` — 통과 (syntax-only inventory warning: localhost does not match `afterglow`).
- [x] `openspec validate 2026-11-21-keystone-discovery-precheck` — valid.
- [x] `npm run docs:check` and `python3 scripts/check_architecture.py --staged` — 통과.

## 운영

- [x] Backed up `/etc/kolla/globals.yml` to `/etc/kolla/globals.yml.before-afterglow-source-fix-20261121T203630Z`; corrected stale backend source path to `/etc/kolla/config/afterglow/backend/afterglow.conf`. Did not restore a globals.d link.
- [x] `ANSIBLE_LOG_PATH=/etc/kolla/kolla-afterglow-reconfigure-20261121T203938Z.log kolla-ansible reconfigure -i multinode --tag afterglow` — exit 0; controllers 1/2/3 failed=0. All Afterglow and HAProxy/ProxySQL containers running; backend/frontend healthy; public `/` and `/api/v1/health` returned 200. No authenticated request performed. Generated config hashes changed from baseline and were not byte-compared before rollout; source path correction is the known change. Local code fix is not installed in the production venv.
- [x] First approved reconfigure attempt stopped at Keystone precheck with HTTP 300; controller recap was `changed=0` for all three.
- [x] Defaults-only precheck fix released as `1.32.31` and installed on production (`uv add --no-sync --tag 1.32.31` + `uv sync --locked --inexact --no-install-project`; manifest/lock backed up as `*.before-afterglow-kolla-1.32.31-20261122T075117Z`; only the `afterglow-kolla` pin changed).

## 릴리스 준비

- [x] `npm run test:gate` 단계별 결과 — docs/catalog/JS/Kolla contract, 프런트엔드 단위, contract, functional(301 passed), `lint:backend` 통과. 백엔드 단위 15711 passed, 3 failed: `test_host_health`·`test_site_branding`은 저장소 루트의 gitignore된 로컬 `afterglow.conf`를 읽어서 실패하며, 해당 파일 없이 작업 트리 사본에서 41 passed로 확인했다.
- [x] 1.32.31 패치 릴리스 메타데이터, 이중 언어 CHANGELOG와 wheel 포함 확인(`precheck_keystone_reachability.yml`).
- [x] 정확한 SHA(`00e17ea658`) CI run 44998761745 통과 후 `1.32.31` 태그·GitHub Release 발행. 이미지 3종 `1.32.31`=`latest` 다이제스트·revision 라벨과 Helm `version`/`appVersion` 1.32.31 확인. `dev → main` 머지는 사용자 소유라 수행하지 않았다.
- [x] 운영 `kolla-ansible prechecks -i multinode --tag afterglow`: 기존 설정(`/v3`)과 일회성 `-e afterglow_operator_config_source=""`(기본값 경로, Keystone 루트는 컨트롤러 3대 모두 HTTP 300, `/v3`는 200) 모두 failed=0. `reconfigure`는 `latest`가 1.32.31 이미지로 옮겨져 롤링 교체가 되므로 실행하지 않았다.
