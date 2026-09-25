# Tasks

## Palimpsest release

- [x] Root metadata, lock, release environment URL, package smoke, docs를 `palimpsest-client` 0.2.3으로 전환
- [x] Portable lanes, ruff, CLI reference, package build/install smoke 통과
- [x] `dev` push 및 dev→main PR 생성
- [x] PR #8 검사 통과 후 merge(`fc729e3b`), merge commit에 `v0.2.3` tag
- [x] Release run `36081630018` 성공: PyPI `palimpsest-client` 0.2.3 wheel/sdist와 GitHub Release `v0.2.3` 게시

## Afterglow operator

- [x] Operator manifest, promoter, installer, 계약 fixture를 `palimpsest-client`로 전환
- [x] 퇴역 `palimpsest-local` 잔존 시 installer 거부 및 회귀 테스트 추가
- [x] Operator/Kolla/deployment/architecture 문서 갱신
- [x] `v0.2.3` tag 기준 `uv.lock` 재해석 및 promoter `--check`
- [x] Kolla contract 26, promoter 5, `test:gate` 성공: backend 2951, frontend 1444/248 files, contract 132, functional 27, Ruff

## 운영 전환

- [ ] wireguard-dmslab Kolla 환경에서 `palimpsest-local` 제거 후 `palimpsest-client` 재설치
- [ ] `install.sh` 검증과 Palimpsest role 재적용
- [ ] Hub container health와 인증 경로 확인
