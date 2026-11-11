# kolla-toolbox clouds.yaml 병합 (Afterglow role)

## 배경

`deploy/kolla/ansible/roles/afterglow/tasks/toolbox_cli_auth.yml`은 `kolla_toolbox`의 `/var/lib/ansible/.config/openstack/clouds.yaml`을 `{"clouds": {"kolla": {...}}}` 하나로 **통째로 교체**했습니다. 그래서 Kolla 원본의 `kolla-admin-internal`, `kolla-admin`, `kolla-admin-system`, `kolla-admin-system-internal`, `kolla-octavia-internal` 항목이 사라졌습니다. Kolla의 keystone 서비스 등록과 mapping 등록이 `kolla-admin-internal`을 찾지 못해 실패합니다.

이 태스크는 `precheck.yml`에서 `deploy`, `reconfigure`, `upgrade`마다 실행되며, `cloud_shell` 또는 `manila`가 켜져 있으면 항상 실행됩니다. 태그 없이 실행하거나 `--tags afterglow`로 실행하면 덮어쓰기가 반복됩니다. `--tags keystone`만 실행하면 afterglow role은 실행되지 않습니다(`deploy/kolla/site.yml`의 `tags: afterglow`).

- Kolla 2026.1의 `openstack_auth`는 CLI/API 호출에 필요한 전체 인증 사전이 아니라 bootstrap용 password만 제공한다. 기존 Afterglow 헬퍼는 이를 `clouds.yaml`의 `kolla.auth`로 그대로 넣어 `auth_url`을 빠뜨렸고, 실제 `share list`에서 `Missing value auth-url required for auth plugin password`가 재현됐다.
- Kolla가 생성한 `openstack_auth_cloud` 항목(현 배포 기본 `kolla-admin-internal`)에는 URL·사용자·프로젝트·도메인 정보가 있다. Kolla `service-ks-register`의 설치된 2026.1 구현은 각 `openstack.cloud` 요청에 `auth`와 `cloud: openstack_auth_cloud`를 함께 전달한다.
- Afterglow의 직접 `openstack.cloud` 호출도 `auth`와 `cloud`를 모두 전달해야 한다. `service-ks-register` 호출은 설치된 Kolla role이 cloud selector를 처리한다.
- toolbox 컨테이너와 설정 파일은 호스트별이다. 이전 구현은 `run_once`로 첫 controller에만 alias를 만들었다. 실제 controller2에서는 `kolla` alias가 없었고, controller3는 읽기 권한 거부로 확인하지 못했다.

## 변경

- `files/merge_toolbox_clouds.py`: 기존 `clouds.<source_cloud>`를 복제해 `clouds.kolla`를 만들고, `auth_overrides`(Kolla 2026.1에서는 password-only)를 병합한다. URL 없는 cloud나 없는 source는 fail-closed이며 기존 cloud 항목을 보존한다.
- `tasks/toolbox_cli_auth.yml`: 각 `afterglow` controller의 toolbox에서 source cloud를 alias로 만든다. `run_once`/단일 controller 위임을 제거한다.
- `tasks/config.yml`, `tasks/preconditions_keystone.yml`: 직접 `openstack.cloud` 모듈 호출에 `cloud: "{{ openstack_auth_cloud }}"`를 함께 전달한다. Kolla `service-ks-register`의 cloud 선택은 Kolla 2026.1 구현에 위임한다.
- `docs/deployment.md`와 `ARCHITECTURE.md`: Kolla 2026.1 cloud/auth 계약과 모든 controller의 준비 조건을 기록한다.
## 범위 밖

- 이미 덮어쓰인 운영 파일을 복구하는 것은 이 패치의 범위가 아닙니다. 운영 복구는 운영자가 Kolla 원본을 다시 생성하거나 Kolla 항목을 백업에서 복원한 뒤 이 태스크로 `kolla` 항목만 병합하는 방식으로 진행합니다.
- 운영 배포, Kolla 실행, 커밋은 이 change에 포함하지 않습니다.
- Kolla keystone mapping 원본(schema 2.0 전환)과 SSO 매핑 정본 복구는 별도 change입니다.
