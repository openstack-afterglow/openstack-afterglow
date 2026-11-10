# kolla-toolbox clouds.yaml 병합 (Afterglow role)

## 배경

`deploy/kolla/ansible/roles/afterglow/tasks/toolbox_cli_auth.yml`은 `kolla_toolbox`의 `/var/lib/ansible/.config/openstack/clouds.yaml`을 `{"clouds": {"kolla": {...}}}` 하나로 **통째로 교체**했습니다. 그래서 Kolla 원본의 `kolla-admin-internal`, `kolla-admin`, `kolla-admin-system`, `kolla-admin-system-internal`, `kolla-octavia-internal` 항목이 사라졌습니다. Kolla의 keystone 서비스 등록과 mapping 등록이 `kolla-admin-internal`을 찾지 못해 실패합니다.

이 태스크는 `precheck.yml`에서 `deploy`, `reconfigure`, `upgrade`마다 실행되며, `cloud_shell` 또는 `manila`가 켜져 있으면 항상 실행됩니다. 태그 없이 실행하거나 `--tags afterglow`로 실행하면 덮어쓰기가 반복됩니다. `--tags keystone`만 실행하면 afterglow role은 실행되지 않습니다(`deploy/kolla/site.yml`의 `tags: afterglow`).

## 확인된 사실

- controller1 toolbox에는 `clouds.yaml`이 하나뿐입니다. `/etc/openstack/clouds.yaml`과 `/etc/kolla/clouds.yaml`은 없습니다. `HOME=/var/lib/ansible`이므로 openstacksdk가 읽는 파일은 이 하나입니다. controller2와 3은 아직 확인하지 않았습니다.
- 따라서 같은 파일 안에서 Afterglow의 `kolla` 항목과 Kolla 항목을 **병합**하는 것이 유효합니다. 전용 파일로 분리하면 `OS_CLIENT_CONFIG_FILE`을 모든 `--os-cloud=kolla` 호출부에 적용해야 하므로 범위가 커집니다.

## 변경

- `files/merge_toolbox_clouds.py`(신규): 기존 파일을 파싱해 `clouds.<name>` 항목만 교체하고 나머지 항목을 보존합니다. 파싱 실패나 잘못된 구조는 **덮어쓰지 않고 실패**합니다. 내용이 같으면 `unchanged`를 출력하고 파일을 다시 쓰지 않습니다. 원자적 교체, `0600`, `ansible` 소유를 유지합니다.
- `tasks/toolbox_cli_auth.yml`: 인라인 Python 대신 헬퍼를 `lookup('file')`로 실행하고 `{"name": "kolla", "entry": {...}}`를 stdin으로 넘깁니다.

## 범위 밖

- 이미 덮어쓰인 운영 파일을 복구하는 것은 이 패치의 범위가 아닙니다. 운영 복구는 운영자가 Kolla 원본을 다시 생성하거나 Kolla 항목을 백업에서 복원한 뒤 이 태스크로 `kolla` 항목만 병합하는 방식으로 진행합니다.
- 운영 배포, Kolla 실행, 커밋은 이 change에 포함하지 않습니다.
- Kolla keystone mapping 원본(schema 2.0 전환)과 SSO 매핑 정본 복구는 별도 change입니다.
