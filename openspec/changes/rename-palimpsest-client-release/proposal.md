# Palimpsest root 배포판을 palimpsest-client로 전환

## 문제

Palimpsest v0.2.2 release run `36077150178`은 artifact 검증과 native KVM proof를 통과했지만
PyPI publish에서 `400 Non-user identities cannot create new projects`로 실패했다. PyPI OIDC
교환은 성공했고, pending trusted publisher의 project 이름이 root metadata의
`palimpsest-local`과 달랐다. 사용자는 PyPI 배포판 이름을 `palimpsest-client`로 지정했다.

Afterglow Kolla operator는 `palimpsest-local` 배포판 이름으로 role version을 검증한다. 새
배포판은 같은 `share/kolla-ansible/ansible/roles/palimpsest` 파일을 설치하는데, operator sync는
`--inexact`라 기존 `palimpsest-local`을 제거하지 않는다. 두 배포판이 함께 남으면 이후 퇴역
배포판 uninstall이 현재 role 파일을 지운다.

## 해결

- Palimpsest root 배포판을 `palimpsest-client` 0.2.3으로 발행한다. import `palimpsest_local`,
  CLI `palimpsest`, role 파일, 저장된 domain/artifact marker, Hub 0.2.0은 그대로 둔다.
- Operator manifest/lock, tag promoter, installer 검증, 계약 fixture를 `palimpsest-client`
  `v0.2.3`으로 옮긴다.
- `install.sh`는 `palimpsest-local` metadata가 남아 있으면 link 생성 전에 거부하고, 제거 후
  `--reinstall-package palimpsest-client` 재동기화를 안내한다.
- 운영 Kolla 환경은 같은 절차로 전환하고 Palimpsest role 재적용 뒤 Hub health와 인증 경로를
  다시 확인한다.

## 범위 밖

Hub image/tag, Palimpsest Hub schema, Kolla role 동작, 다른 형제 서비스 버전은 바꾸지 않는다.
