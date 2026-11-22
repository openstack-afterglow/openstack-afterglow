# 작업 체크리스트

## 구현

- [x] 첫 targeted controller 식별과 앞선 fatal 확인 안내를 selection readiness fail message에 추가한다.
- [x] Kolla 배포 문서, changelog, architecture review summary를 갱신한다.

## 검증

- [x] `PATH=deploy/kolla/operator/.venv/bin:$PATH node --test scripts/kolla-runtime-contract.test.js` — 59 passed, including prior-play first-controller failure guidance and no false guidance for disabled/source-mode targets.
- [x] `ANSIBLE_ROLES_PATH=ansible/roles uvx --from 'ansible-core==2.19.0' ansible-playbook -i 'localhost,' -c local playbooks/afterglow.yml --syntax-check` — 통과.
- [x] `npm run docs:check` 및 `python3 scripts/check_architecture.py --staged` — 통과.
