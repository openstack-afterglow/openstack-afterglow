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
- [ ] Defaults-only precheck fix is source-only; production still runs `afterglow-kolla==1.32.30`. Review and install a released package before claiming the no-operator-source path is live.

## 릴리스 준비

- [x] `npm run test:gate` 단계별 결과 — docs/catalog/JS/Kolla contract, 프런트엔드 단위, contract, functional(301 passed), `lint:backend` 통과. 백엔드 단위 15711 passed, 3 failed: `test_host_health`·`test_site_branding`은 저장소 루트의 gitignore된 로컬 `afterglow.conf`를 읽어서 실패하며, 해당 파일 없이 작업 트리 사본에서 41 passed로 확인했다.
- [x] 1.32.31 패치 릴리스 메타데이터, 이중 언어 CHANGELOG와 wheel 포함 확인(`precheck_keystone_reachability.yml`).
- [ ] 정확한 SHA CI 통과, 사용자 소유 main merge와 `1.32.31` 태그, 운영 `afterglow-kolla` 설치(별도 승인)는 미실행.
