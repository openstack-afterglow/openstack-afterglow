# 배포 가이드

**Language:** 한국어 · [English](en/deployment.md)

Afterglow는 Docker Compose(개발/소규모), Kubernetes(프로덕션), ArgoCD(GitOps) 세 가지 배포 방식을 지원합니다.

---

## 사전 요구사항

### OpenStack 서비스

| 서비스 | 필수 여부 | 용도 |
|---|---|---|
| Keystone | 필수 | 인증 |
| Nova | 필수 | VM 컴퓨트 |
| Glance | 필수 | 이미지 관리 |
| Cinder | 필수 | 블록 스토리지 |
| Neutron | 필수 | 네트워크 |
| Manila | 선택 | 공유 파일시스템 (OverlayFS 기능) |
| Octavia | 선택 | 로드밸런서 |

---

## Docker 없는 OCI-root VM 후보 (미배포)

별도 `Dockerfile` target `native-vm`은 Afterglow API·Notion worker·빌드된 SvelteKit, Node 22, MariaDB/client, Redis를 미리 설치합니다. BuildKit/Docker는 **빌드 호스트**에서만 사용하며 이미지 entrypoint는 `appuser`로 서비스 프로세스를 직접 실행합니다. 기존 Compose·Kolla 배포나 형제 Drover/Lumen/Waygate/Palimpsest Hub를 대체하지 않습니다.

```bash
docker buildx build --platform linux/amd64 --target native-vm \
  --output type=oci,dest=afterglow-native-amd64.oci.tar .
```

Linux amd64/KVM Palimpsest OCI-root의 검증된 kernel/config/packer, libvirt/KVM 권한과 **별도 승인된** 실행 호스트가 필요합니다. macOS Lima의 conventional cloud-image에 설치한 Docker Compose 앱과 다른 경로입니다. 현재 로컬 image smoke 성공은 실제 VM의 `/`·파일 소유권·retained-root persistence 증명이 아닙니다. OCI-root 부팅·인증된 OpenStack 기능은 아직 검증하지 않았으며, CI 프로젝트 member-only credential과 구체 자원 승인 전에는 신규 VM을 만들거나 관리자 자격으로 우회하지 않습니다.

런타임 계약:

- `/var/lib/afterglow` 전체를 UID 1000 소유로 영속화합니다. `credentials.json`·SQL/Redis 데이터·설정·로그를 함께 보존합니다. 초기화가 중단된 `mariadb.installing`이나 marker 없는 SQL 디렉토리는 보존하고 기동을 거부합니다. 재시도를 위해 기존 데이터를 삭제하지 않습니다.
- `/app/afterglow.conf`는 private state의 설정을 가리킵니다. 기존 설정·override는 덮어쓰지 않습니다. 처음에는 앱 암호화 키만 생성하므로 실제 Keystone URL·프로젝트·형제 서비스 설정은 운영자가 안전한 private 설정으로 제공해야 합니다. 자격을 이미지에 넣지 않습니다.
- SQL은 Unix socket만 사용하고 Redis는 암호 인증이 필요한 loopback 6379입니다. 공개할 서비스는 frontend 3080, API 8000뿐입니다. entrypoint의 `--frontend-origin`·`--api-origin`은 브라우저에서 접근하는 실제 origin을 지정합니다. 직접 외부 공개 대신 승인된 TLS ingress 또는 SSH tunnel을 사용합니다.
- HTTP `/health`·`/api/v1/health`가 모두 준비된 뒤 ready를 알립니다. 인증된 dashboard/OpenStack readiness와는 별도입니다. child 종료는 전체 실패이고 SIGTERM/SIGINT는 앱→datastore 순서로 종료합니다.
- 2026-10-02 arm64·emulated amd64 로컬 smoke는 UID 1000·cap-drop ALL·no-new-privileges에서 실제 API/frontend HTTP 200, 37개 schema table, SQL/Redis·키 보존, child 실패/복구, graceful 종료를 확인했습니다. amd64 OCI archive는 22 layers입니다. 상세 증거와 미검증 경계는 root `ARCHITECTURE.md`의 Native OCI-root VM candidate 절을 따릅니다.

### 일반 direct-Nova 디스크 (`native-cloud-vm`)

`Dockerfile --target native-cloud-vm`은 `native-vm`을 기반으로 Debian trixie kernel/initramfs, BIOS GRUB 모듈, systemd, cloud-init, sshd와 같은 supervisor를 `appuser`로 실행하는 `afterglow-native.service`를 추가합니다. guest에는 여전히 container engine이 없습니다. `--platform linux/amd64 --output type=tar`로 빌드한 뒤 Linux amd64 builder에서 root로 `scripts/export_native_cloud.py --rootfs ROOTFS.tar[.gz] --output DISK.raw --size-gib 8 --source-sha256 HEX`를 실행해 BIOS 부팅 raw 디스크와 `.sha256`·`.metadata.json` sidecar를 만듭니다. 운영 설정은 cloud-init `write_files`로 `/etc/afterglow/afterglow.conf`(0600)에 전달합니다. root prestart가 이를 한 번만 `appuser`로 `/var/lib/afterglow`에 복사하며 기존 설정은 바꾸지 않습니다. 로그인은 cloud-init `debian` 사용자와 Nova keypair로 하며, host key는 serial console에 출력됩니다.

국가 DB 경계: cloud root의 `/etc/afterglow`은 root:root `0700` cloud-init staging 디렉터리입니다. `appuser` API는 그 아래 파일을 읽을 수 없으므로 `[traffic_analytics].geoip_mmdb`를 이 경로 아래로 지정하지 마세요. 2026-10-15 OCI smoke에서 그렇게 mount한 complete MMDB는 `database_unavailable`이었습니다. Root-owned read-only `/usr/local/share/afterglow/geoip/country.mmdb`와 `TRAFFIC_ANALYTICS__GEOIP_MMDB`로 제공했을 때만 `offline_mmdb`/US·CA·KR이 확인됐습니다. 이 변경은 direct-Nova 디스크에 pinned DB를 넣거나 전달하는 경로를 추가하지 않습니다. 별도로 검토한 image/volume으로 제공하기 전에는 설정하지 않고 unconfigured로 표시합니다.

2026-10-06 SYSTEM 프로젝트 실기: 승인 baseline `ff007ed`와 native overlay(bundle `8f28a712…`)로 만든 디스크(sha256 `c8c33ab1…`)가 Nova(`cpu.2c_8g`, `ceph_hdd`)에서 직접 부팅됐습니다. systemd PID 1, `appuser` supervisor active, engine binary 없음, API/frontend HTTP 200, 37 tables, socket-only SQL·loopback-only Redis를 확인했습니다. 재부팅 뒤에도 MariaDB/Redis·Cinder data volume·CephFS marker가 유지됐고 RGW checksum 왕복도 통과했습니다. member 계정 password 로그인은 SYSTEM·member/reader·system admin 아님으로 확인했고, logout과 SYSTEM network 불변도 확인했습니다. 소유 자원은 모두 삭제하고 부재를 확인했습니다. 이 결과는 OCI root에 선언된 부팅 추가물을 더한 일반 cloud 디스크이며 protected OCI-root stage-1, untouched OCI 실행, 보안 동등성 증명이 아닙니다. 따라서 native OCI-root 변경의 task 6/7은 그대로 열려 있습니다.

## Docker Compose 배포

Compose 파일은 합쳐 쓰는 환경 overlay가 아니라 **각각 독립 실행하는 세 가지 계약**입니다. 항상 명시적인 `-f`로 선택합니다.

| 파일 | 실행 목적 | 통신·데이터 경계 |
|---|---|---|
| `docker-compose.yml` | published Afterglow frontend/backend 두 개만 실행 | Redis·DB·OpenStack·형제 서비스는 외부 설정 |
| `docker-compose.dev.yml` | 현재 Afterglow·Lumen·Waygate·Drover·Palimpsest 소스를 빌드해 개발 실행 | Compose service DNS, 기본 private local DB/cache/checkpointer; 명시한 DB URL은 외부 대상 허용 |
| `docker-compose.prod.yml` | GHCR 이미지를 pull·동기화해 운영 실행 | HAProxy TLS/LB, 일반 경로는 인증된 Keystone catalog endpoint; Palimpsest 패키지는 신뢰된 명시 URL 필수 |

Dev와 prod를 같은 project/volume에 겹쳐 실행하지 않습니다. 기존 로컬 project는 dev 전환 후에도 `afterglow-local-services`이며 데이터나 암호화 키를 다시 만들지 않습니다.

기능테스트도 `docker-compose.dev.yml`의 `test` profile을 사용합니다. `npm run test:functional`은 별도 `afterglow-test` project에서 전용 3307/5434/6380의 MariaDB/PostgreSQL/Redis 세 개만 실행하고 종료합니다. 테스트 데이터는 tmpfs이며 개발 앱·volume·키를 삭제하지 않습니다. Cloud 자격 증명 없는 테스트 단독 실행과 `--no-start`/`--keep` 사용법은 [기능테스트 가이드](testing.md#일회용-국소-기능테스트-환경-functional-lifecycle--ports)를 따릅니다.

### 1. 저장소 클론 및 설정

```bash
git clone git@github.com:openstack-afterglow/openstack-afterglow.git
cd openstack-afterglow
cp afterglow.conf.example afterglow.conf
cp .env.example .env
```

`afterglow.conf` 필수 항목 설정:

```toml
[openstack]
auth_url             = "https://keystone.example.com:5000/v3"
project_name         = "myproject"
project_domain_name  = "Default"
user_domain_name     = "Default"
region_name          = "RegionOne"

[app]
secret_key = "openssl-rand-hex-32-output"  # 반드시 32자 이상 random 값으로 변경

[nova]
default_network_id = "your-network-uuid"
```

기본 Compose backend는 `.env`를 선택적으로 읽지만 frontend에는 backend 시크릿을 주입하지 않습니다. Dev runner는 별도의 private random key를 생성·보존하며 insecure 기본 키 허용에 의존하지 않습니다. `.env.example`의 dev-only allow 플래그를 운영에 사용하지 마세요. Prod manifest는 이를 `0`으로 고정하고 실제 운영 키를 요구합니다.

### 애플리케이션 진단 로그 (`DEFAULT.debug`)

```toml
[DEFAULT]
debug = false # 애플리케이션 DEBUG 진단을 켜려면 true

[logging]
log_level = "INFO" # root/dependency 기본 로그 수준; debug와 별도
```

`[DEFAULT]`와 `debug`는 대소문자를 구분합니다. TOML boolean은 따옴표 없는 소문자
`true` / `false`만 사용합니다. `debug = True` 또는 `False`는 유효한 TOML이 아니며,
설정 로더·생성기는 오류를 내고 소문자로 자동 수정하지 않습니다. 섹션이나 키가 없는
기존 설정도 그대로 사용할 수 있으며 기본값은 `false`입니다.

실제 backend 프로세스에 주입된 `DEBUG` 환경변수(예: `DEBUG=true` 또는 `DEBUG=false`)가
병합된 TOML보다 우선합니다. 따라서 `DEBUG=false`는 TOML의 `debug = true`도 끕니다.
호스트 shell에 변수를 설정하는 것만으로 컨테이너에 전달되지는 않습니다. 기본/dev Compose
backend는 `.env`를 읽지만 prod/Kolla/Kubernetes에서는 명시적으로 backend 환경에 주입해야
합니다. manifest에는 TOML을 가리는 기본 `DEBUG=false` 환경변수를 추가하지 않습니다.

`debug = true`는 `app` namespace의 애플리케이션 로그만 DEBUG로 활성화합니다.
`[logging].log_level`(또는 `LOG_LEVEL`)은 root/dependency 기본 수준을 계속 제어합니다.
OpenStack/HTTP/SDK/SQL 및 `uvicorn.access`의 보호된 logger는 WARNING 제한을 유지합니다.
출력 handler도 이 제한을 적용하므로 하위 logger가 명시적으로 DEBUG를 설정해도
전파된 낮은 수준의 wire/access record를 출력하지 않습니다.
DEBUG는 HTML traceback이나 HTTP wire dump, 인증·인가 우회, insecure 모드 또는 시크릿
출력을 허용하는 스위치가 아닙니다. 진단은 method·등록된 route template·status·duration·
outcome과 module/function/line 같은 제한된 메타데이터이며 실제 URL path 값, query,
header, body, cookie를 기록하지 않습니다. 예외는 type과 제한된 function/line만 기록하며
예외 문자열·소스 줄·locals·chained cause는 제외합니다. 민감 key와 인식된 credential 패턴은
값 전체를 `***`로 마스킹합니다. 텍스트의 민감 assignment(`key`, `cephx_key`,
`kube_config`, API key/authorization 변형, headers/body 포함)는 뒤의 나머지 텍스트도
마스킹합니다. 공백·중첩 JSON·이스케이프 따옴표·여러 줄 값의 경계는 신뢰할 수 없으므로
안전한 구조는 문자열 덤프가 아닌 제한된 extra 메타데이터에 둡니다. 호출자는 정적 event
메시지와 코드가 소유한 제한된 메타데이터만 기록해야 합니다. 문자열 패턴 마스킹은
defense-in-depth이며 모든 임의의 사용자 텍스트·객체·설정 덤프를 안전하게 만드는 보장이
아닙니다. opaque 비문자열 메시지, dict/extra key와 builtin subclass는 객체의 문자열
표현을 호출하지 않고 제외합니다. 중첩 한도를 넘는 extra 값은 마스킹되지만, 이것을
request/response 전체 덤프의 허가로 해석하지 않습니다.

생성/배포 경로:

- `generate_k8s.py`: 병합된 `[DEFAULT].debug`를 ConfigMap의 `afterglow.conf`에
  소문자 TOML boolean으로 렌더링합니다. 생략 시 `false`를 제공합니다.
- `config2helm.py`: `[DEFAULT].debug`를 최상위 Helm `debug` boolean으로 변환합니다.
  차트 `values.yaml`의 기본값은 `false`이고 ConfigMap에 `[DEFAULT]`로 렌더링합니다.
  이전 values 파일에 키가 없어도 호환됩니다. 변환한 `logging.logLevel`, `logDirectory`,
  `maxBytes`도 ConfigMap의 `[logging]`에 렌더링되므로 DEBUG와 별개인 root 수준·파일 경로·
  회전 크기를 유지합니다. 생략 시 backend 기본값(`INFO`, `logs`, 52428800)을 사용합니다.
  Helm upgrade/ArgoCD 도구는 values를 전달하므로 별도 변환이 필요 없습니다.
- `setup.py`: Compose용 TOML과 setup K8s ConfigMap 모두 같은 renderer로
  `[DEFAULT].debug`를 보존하고, wizard의 미지정 값은 `false`입니다.
- Kolla: base에 `debug = false`를 제공합니다. private backend operator TOML에서
  `[DEFAULT]\ndebug = true`를 지정할 수 있습니다. sanitizer는 값을 보존하며 final
  Kolla overlay는 debug를 덮어쓰지 않습니다. public frontend projection에는 포함하지 않습니다.
- Compose manifest와 `scripts/local-services.mjs`는 TOML을 재직렬화하지 않고 mount/복사하므로
  변경하지 않습니다. Dev의 기존 `.local-services/afterglow.conf` snapshot은 원본 수정으로
  덮어쓰지 않으므로 실제 snapshot을 수정해야 합니다. 환경별 override에는 강제 debug 값을
  넣지 않습니다. 정적 `deploy/k8s-template/configmap.yaml`에도 기본 `false`를 제공합니다.

변경 후 해당 설정을 사용하는 프로세스를 재시작/재생성해야 합니다. 환경변수로 TOML 오류를
덮어 정상 설정처럼 취급하거나, 생성된 private 설정/로그를 시크릿과 함께 공개하지 않습니다.

### 1-b. 설정 오버라이드 (선택)

긴 옵션 섹션(GPU 디바이스 맵 등)은 별도 오버라이드 파일로 분리할 수 있습니다.  
`afterglow.conf`와 같은 디렉토리에 `afterglow.<name>.conf` 또는 `config.gpu.toml`을 두면 백엔드 기동 시 알파벳순으로 딥 머지됩니다. 브라우저 공개 projection인 `afterglow.frontend.conf`은 백엔드 오버라이드에서 제외됩니다.

**머지 규칙**: `dict`는 재귀 병합, `list`와 스칼라는 오버라이드 파일이 덮어씁니다.

```bash
# GPU 디바이스 맵 활성화 예시
cp config.gpu.toml.example config.gpu.toml
# config.gpu.toml 을 편집하여 실제 환경의 GPU PCI ID 반영
```

여러 오버라이드 파일을 동시에 사용할 수 있습니다:

```
afterglow.conf        ← 베이스 설정
config.gpu.toml       ← GPU 디바이스 맵 오버라이드 (레거시 이름도 계속 지원)
afterglow.openstack.conf  ← OpenStack 자격증명 오버라이드 (선택)
```

파일명 예시 처럼 알파벳순(`g` < `o`)으로 적용되며 뒤 파일이 앞 파일을 이깁니다.

### 1-c. 관리자 볼륨 삭제 Ceph RBD 검사 (선택)

`error_deleting` 볼륨 복구는 기본적으로 Cinder/Nova API만 사용합니다. RBD backend를 직접 확인하려면 아래 네 항목을 모두 설정해야 하며, 하나라도 빠지면 기능은 비활성입니다. 비활성 상태에서는 Cinder 삭제를 요청할 수 있지만 backend 삭제를 증명하지 못하므로 결과는 `backend_unverified`이고 성공으로 닫히지 않습니다.

```toml
[ceph]
rbd_conf_path = "/etc/ceph/ceph.conf"
rbd_keyring_path = "/etc/ceph/ceph.client.afterglow-rbd.keyring"
rbd_client_name = "client.afterglow-rbd"
rbd_cluster_fsid = "01234567-89ab-cdef-0123-456789abcdef"
rbd_command_timeout_seconds = 30

# Cinder volume.host의 `@`와 `#` 사이 backend 이름을 실제 RBD pool에 연결한다.
[ceph.rbd_volume_pools]
ceph = "volumes"
```

`rbd_cluster_fsid`는 `ceph fsid`와 정확히 같아야 합니다. 불일치·timeout·권한 거부·해석할 수 없는 CLI 응답은 모두 `unknown`이며 복구를 중단합니다. 각 backend 이름은 정확히 한 pool에 대응시킵니다. clone parent가 다른 pool에 있으면 그 parent pool의 read/class-read 권한도 추가해야 합니다.

CephX identity는 전용 `client.afterglow-rbd`를 사용하고 `client.admin`을 사용하지 않습니다. 필요한 권한 경계는 다음과 같습니다.

- monitor: cluster FSID와 RBD client metadata를 읽는 `profile rbd` 수준
- manager: 대상 volume pool의 `profile rbd-read-only` 수준
- OSD: 대상 volume/parent pool의 `rbd_` object read와 class-read, 대상 volume pool의 `rbd_id.` object write

Afterglow는 image data/header/trash를 삭제하지 않습니다. 쓰기는 누락된 `rbd_id.volume-<uuid>` 복원과, Cinder·RBD image/header/data/trash 부재가 모두 증명된 뒤 동일 object를 정리하는 경우뿐입니다. Ceph release별 RBD class method cap 요구가 다를 수 있으므로 운영 반영 전에 전용 identity로 `ceph fsid`, `rbd info`, `rbd status`, `rbd snap ls`, `rbd children`, `rbd trash ls`, `rados stat/getomapval/getxattr/ls`를 staging pool에서 실행해 권한을 검증합니다. 권한을 넓혀 오류를 숨기지 말고 필요한 pool/object prefix만 추가합니다.

배포별 파일 연결:

- Dev runner: `.local-services/ceph/ceph.conf`와 `.local-services/ceph/ceph.client.afterglow-rbd.keyring`을 만들면 `services:config/up`이 source를 0640으로 고정하고, 실제 파일 GID를 받은 non-root backend에만 `/etc/ceph/` read-only mount합니다. private `.local-services/afterglow.conf`의 `[ceph]` 경로·FSID·pool map도 위 값으로 설정해야 합니다.
- 직접 dev Compose: `AFTERGLOW_LOCAL_CEPH_CONF`, `AFTERGLOW_LOCAL_CEPH_KEYRING`에 host 파일 경로를 넣습니다.
- Prod Compose: `CEPH_RBD_CONF_FILE`, `CEPH_RBD_KEYRING_FILE`에 host 파일 경로를 넣고 container config는 `/etc/ceph/` 경로를 가리킵니다.
- Kolla: `afterglow_rbd_conf_source`, `afterglow_rbd_keyring_source`, `afterglow_rbd_cluster_fsid`, `afterglow_rbd_volume_pools`를 설정합니다. 두 source가 모두 있을 때만 mount됩니다.
- Kubernetes: private generation config의 `[ceph]`에 `rbd_conf_content`와 secret `rbd_keyring`을 추가한 뒤 `generate_k8s.py`를 실행합니다. ConfigMap의 `ceph.conf`와 Secret의 `ceph.client.afterglow-rbd.keyring`이 backend에 0400 read-only로 mount됩니다. repository의 빈 placeholder를 운영 key로 착각하지 않습니다.

배포 뒤 backend container의 non-root 사용자로 `rbd --version`, `rados --version`, `ceph fsid`를 확인합니다. 진단 API에서 `backend_fsid=present`와 mapped pool을 확인하되, 기존 Cinder 장애 볼륨을 자동 복구 검증 대상으로 사용하지 않습니다. Keyring 본문·CLI argv 전체·Ceph auth output은 로그나 이슈에 붙이지 않습니다.

### 관리자 호스트 관측과 트래픽 분석 운영

이 절은 [관리자 API](api/admin.md#호스트-건강-관측-host-health)의 host health, [인프라 토폴로지](api/admin.md#인프라-토폴로지와-호스트-관측), [트래픽](api/admin.md#트래픽-분석)의 **운영자가 준비하는 수집 경계**입니다. Afterglow는 node_exporter·observer·LLDP daemon·traceroute를 노드에 자동 설치하거나 방화벽·NIC·OpenStack 설정을 변경하지 않습니다. 관리자 UI는 [하이퍼바이저](/admin/hypervisors), [인프라 토폴로지](/admin/infrastructure-topology), [트래픽](/admin/monitoring/traffic), [로그인](/admin/monitoring/logins)입니다. [애플리케이션 자격 증명](/admin/application-credentials)과 [사용자 자격 증명](/admin/user-credentials)은 별도 caller-scoped Keystone API이며 observer/writer token을 대신하지 않습니다.

#### `[monitoring]` 호스트 관측 설정

| 키 | 기본값·범위 | 운영 의미 |
|---|---|---|
| `host_healthcheck_enabled` | `true` | main-process lifespan의 nominal 10초 node_exporter collector 활성화 |
| `host_healthcheck_targets` | `[]`, 최대 64개 | `{name,address,role,port?}`. role은 `compute/controller/storage`, port 기본 9100·1–65535 |
| `infrastructure_topology_enabled` | `false` | observer report/job API와 관리자 topology 활성화 |
| `infrastructure_topology_observers` | `[]`, 최대 256개 | `{host_id,token,addresses?}` per-host 신원. host_id/token 및 등록 주소의 소유자는 유일해야 함; host당 canonical literal IPv4/IPv6 최대 32개 |
| `infrastructure_topology_trace_targets` | `[]`, 최대 16개 | 관리자 요청으로 실행할 literal unicast IP allowlist. 중복·DNS·CIDR·loopback/link-local/multicast/unspecified 금지 |
| `infrastructure_topology_peer_targets` | `[]`, 최대 64개 | `{source_host_id,target_host_id,address,port?}` directed TCP tuple. port 기본 9100 |
| `infrastructure_topology_retention_seconds` | `3600`, 300–86400 | Redis observation 및 trace 보존 TTL/표시 cutoff; NIC history 최대 60표본, trace history 최대 20개 |

```toml
[monitoring]
host_healthcheck_enabled = true
host_healthcheck_targets = [
  { name = "controller-1", address = "controller-1.example.org", role = "controller", port = 9100 },
  { name = "storage-1", address = "storage-1.example.org", role = "storage", port = 9100 }
]
infrastructure_topology_enabled = true
infrastructure_topology_observers = [] # 실제 host/token 목록은 backend 전용 Secret으로 주입
infrastructure_topology_trace_targets = [] # 승인한 literal IP만 운영자가 채움
infrastructure_topology_peer_targets = []  # 승인한 source→target IP/port만 운영자가 채움
infrastructure_topology_retention_seconds = 3600
```

`host_healthcheck_targets`의 name은 1–253자의 영문/숫자로 시작하는 영문·숫자·`_`·`.`·`-` 이름이며 동일 role/name(대소문자 무시)은 중복할 수 없습니다. Bare address DNS/IP만 허용합니다. URL·path·query·인증 정보, local/link-local/metadata/special 주소 및 그런 주소를 반환하는 DNS는 거부합니다. Private 관리망 IP는 허용되며 DNS의 모든 응답을 검사한 뒤 선택한 IP로 probe를 고정합니다. Compute는 Nova `host_ip`, controller는 scheduler/conductor host DNS로 자동 발견하고 설정은 동일 identity의 주소/포트를 override합니다. Nova에 없는 controller와 storage는 명시적으로 추가해야 하며 storage heartbeat는 미관측입니다.

Collector는 인증 없는 **관리망 HTTP `/metrics`**만 읽습니다. 전용 node_exporter를 설치하고 backend에서 해당 주소/포트로만 접근 가능하도록 운영자가 제한하세요. Public internet에 exporter를 공개하지 않습니다. TLS/basic-auth exporter 또는 Prometheus 서버를 대신 조회하는 계약은 아닙니다. NIC 주소를 표시하려면 exporter의 `--collector.netdev.address-info`가 필요하며 미제공 주소는 null입니다. Probe당 3초·동시 8개·body 2 MiB, snapshot staleness 30초, metric history 600초/최대 60 points는 코드의 고정 제한이지 추가 설정 key가 아닙니다.

모든 backend replica는 같은 cloud 설정과 Redis primary/DB/namespace를 공유해야 합니다. Redis 30초 lease를 5초마다 갱신한 단일 소유자만 probe/discovery를 하고 fenced publication을 사용합니다. Redis 장애를 process-local collection으로 우회하지 않으며 API는 미수집/stale/unknown을 그대로 보여줍니다. Nova heartbeat, Afterglow→exporter 연결, observer의 directed peer 연결은 서로 다른 증거입니다.

Observer token은 **호스트별 서로 다른 32–256자의 URL-safe random 문자열**(`A–Z`, `a–z`, `0–9`, `_`, `-`)을 운영자의 secret 생성/배포 경로에서 준비합니다. 실제 token을 예시·명령 인자·로그·공개 frontend 설정에 넣지 않습니다. Backend 환경변수 `MONITORING_INFRASTRUCTURE_TOPOLOGY_OBSERVERS`에 `{host_id,token,addresses}` 객체의 **JSON 배열**을 Secret으로 주입하면 `[monitoring].infrastructure_topology_observers`를 override합니다. `addresses`는 실제 host 소유권을 검토한 canonical literal 주소만 등록하며 다른 host와 공유하거나 IPv4-mapped IPv6 alias로 중복 등록하지 않습니다. 각 Linux 호스트에는 자기 token 하나만 배포하고 frontend/browser 및 flow collector에는 어느 token도 전달하지 않습니다. Backend 설정 변경·회수 뒤 해당 프로세스를 재시작하여 반영합니다.

`host_id`는 `compute:compute-1`, `controller:controller-1`, `storage:storage-1`처럼 role과 **소문자 inventory 이름**의 정확한 값입니다. Observer가 hostname에서 추정하지 않습니다. Peer의 source는 configured observer여야 하고 target은 다른 host_id여야 합니다. Source/target 쌍은 유일해야 하며 address는 literal unicast IP, port는 1–65535입니다. Target host_id를 선언한 것만으로 그 IP의 실제 소유권·물리 연결을 자동 증명하지 않습니다. 운영자가 host/주소 매핑과 허용 통신 방향을 검토해야 합니다.

#### 각 Linux 호스트에서 observer 실행

Linux와 **Python 3.12+**(stdlib만 사용), JSON 출력을 지원하는 iproute2의 `ip`, 읽을 수 있는 `/proc/net/dev`·boot_id·sysfs가 필요합니다. Trace를 사용할 때는 `-n/-q/-m/-w/-4/-6`를 지원하는 Linux `traceroute`를 사전 설치합니다. LLDP는 선택 사항으로 기존 lldpd의 이웃을 읽으며 **현재 스크립트가 실행하는 명령은 `lldpcli -f json show neighbors`**입니다. `lldpctl`만 있는 설치는 충분하지 않으므로 같은 패키지의 `lldpcli` 지원을 확인하세요. Tool 부재는 `unsupported`, 잘못된/과대/실패 출력은 `error`이며 자동 설치·scan·packet capture·다른 도구 fallback은 없습니다.

전용 최소 권한 사용자로 먼저 passive 읽기·`lldpcli` socket 접근·승인된 TCP/UDP outbound가 가능한지 확인합니다. 기본 실행을 root로 하거나 전체 NIC/방화벽 변경 권한을 주지 않습니다. 필요한 경우 배포판의 traceroute 실행 권한 및 LLDP 읽기 group만 별도로 검토하고, 권한 부족을 전체 관리자 권한으로 숨기지 않습니다. 보고 시간 검증과 counter rate를 위해 호스트와 backend의 clock을 동기화하세요.

```bash
# 승인된 스크립트를 해당 호스트에 배포한 뒤 전용 사용자로 1회 보고
python3 scripts/host_observer.py \
  --base-url https://console.example.org \
  --host-id compute:compute-1 \
  --token-file /etc/afterglow/host-observer.token \
  --once

# 동일 신원으로 계속 실행. TEST-NET 목적지는 문법 예시일 뿐 실제 도달 검증 대상 아님
python3 scripts/host_observer.py \
  --base-url https://console.example.org \
  --host-id compute:compute-1 \
  --token-file /etc/afterglow/host-observer.token \
  --interval 10 \
  --trace-target 192.0.2.1
```

| CLI / 환경 | 계약 |
|---|---|
| `--base-url` | 검증된 **HTTPS origin**, 선택 deployment path prefix. `/api/v1` suffix·query·fragment·userinfo 없음 |
| `--host-id` | backend에 등록된 정확한 host ID |
| `--token-file` | regular·nonsymlink 파일, 실행 사용자가 소유하고 **정확히 0600**; 마지막 newline 하나만 허용 |
| `HOST_OBSERVER_TOKEN` | token-file 생략 시 secret 환경 주입 대안. Child command에는 전달하지 않음; `--token` 인자는 없음 |
| `--ca-file` | 사설 CA를 쓸 때 신뢰할 CA bundle. 생략하면 system CA; hostname 검증 유지 |
| `--interval` | 기본/최소 10초, 최대 3600초. Slow cycle 중복·catch-up burst 없음 |
| `--once` | report와 poll 한 cycle 및 가능한 trace result 제출 후 종료 |
| `--trace-target` | 반복 가능한 local literal-IP allowlist. 생략하면 trace 실행 안 함; 서버 target 허용도 별도로 필요 |

HTTP·insecure TLS·redirect·proxy 환경 전달은 지원하지 않습니다. Passive command는 1.5초/256 KiB 출력, API body/response도 256 KiB, trace는 16 hops/40초 deadline으로 제한합니다. HTTPS 작업은 bounded이며 origin DNS는 OS resolver timeout을 따릅니다. 정상 mode의 단일 trace worker는 passive report와 peer admission을 계속 진행하고 busy poll에 `claim=false`를 사용합니다. Trace 접수는 90초 job 만료·host당 60초 rate limit을 가지며 임의 반복 측정/역방향 진단을 하지 않습니다.

Peer targets는 **매 cycle authenticated poll**에서 받은 정확한 IP/port만 사용합니다. 최대 8 workers·각 3초·batch 8초와 cleanup으로 제한하고 미완료 probe는 unknown입니다. Admission 실패 시 cached tuple은 최대 20초 동안 unknown으로만 보존하며 재probe하지 않습니다. 물리 링크는 LLDP 증거로만 표시하고 neighbors/routes·NIC counters·directed TCP reachability·outbound trace를 별도로 검토하세요. `*` hop을 장애 위치로 단정하거나 target IP만 보인 trace를 reached로 표시하지 않습니다.

Afterglow는 daemon/service unit도 자동 설치하지 않습니다. 운영자가 승인한 supervisor로 실행·재시작/Secret 회수를 관리하고 `--once` 결과와 관리자 snapshot의 freshness/source state를 확인합니다. Fixed diagnostic code만 수집하며 token·명령 출력·API 오류 body를 troubleshooting 로그에 복사하지 않습니다.

#### 별도 승인된 passive flow collector 설치

`scripts/flow_collector/`는 기존 observer와 **별도 권한 경계**입니다. 운영자가 host·주소·physical NIC 관측 지점과 설치를 승인한 뒤에만 사용합니다. Linux ≥5.8의 `CAP_BPF` 모델, 배포판 `python3-bpfcc`/`libbpfcc`(PyPI `bcc` 아님), Clang/LLVM, **현재 실행 kernel과 정확히 일치하는 distro headers**와 지원되는 socket-filter helper가 필요합니다. BTF 존재나 다른 노드의 성공은 해당 노드 qualification이 아닙니다.

Registry JSON은 `host_id`, `hosts=[{id,addresses}]`, `interfaces=[{name,ifindex,mac}]`, `interval_seconds`를 포함합니다. 한 collector는 최대 128hosts/1024주소/host당32주소/8NIC, interval1–10초입니다. Local host 및 peer 주소는 backend 등록 소유권과 일치해야 합니다. NIC는 sysfs의 PCI/device·iflink 근거, 안정된 ifindex와 unicast MAC으로 검증하며 bond/bridge/VLAN/tunnel/virtual NIC를 physical 관측점으로 대신 지정하지 않습니다. 예시의 TEST-NET 주소와 MAC을 실제 registry로 그대로 쓰지 않습니다.

승인한 source bundle을 **root-owned·group/world 쓰기 불가·nonsymlink ancestry**의 설치 staging 경로로 배포하고, registry도 동일한 보호 ancestry의 absolute regular·single-link root-owned0600 파일로 준비합니다. 개발 checkout이나 `/tmp`에서 root import를 실행하지 않습니다. `install.sh`는 source/config/destination ancestry와 소비 inode를 검증한 뒤 source를 명시적으로 읽어 import하며 cwd나 unchecked `__pycache__`를 실행하지 않습니다.

```bash
# /opt/afterglow-flow-source는 운영자가 보호·검토한 source bundle의 예시 경로
sudo sh /opt/afterglow-flow-source/install.sh /etc/afterglow-flow-reviewed/collector.json
# Installer는 설치만 하며 start/enable하지 않는다. unit/config 검토와 별도 승인 후:
sudo systemctl daemon-reload
sudo systemctl enable --now afterglow-flow-collector.service
```

설치 대상은 `/opt/afterglow-flow`, `/etc/afterglow-flow/collector.json`, `afterglow-flow-collector.service`입니다. Collector는 root로 실행하되 bounding/ambient/effective capability는 **CAP_BPF + CAP_NET_RAW만** 허용하고 token은 갖지 않습니다. `CAP_NET_ADMIN`/`CAP_SYS_ADMIN` fallback은 없습니다. Protocol0 socket에 항상0을 반환하는 BPF filter를 붙이고 lock한 뒤 bind합니다. Fixed L2/VLAN·IPv4/IPv6 header와 `skb->len`만 계수하고 bounded non-LRU per-CPU1024-row map을 읽습니다. `recv`/`send`, payload/PCAP, promiscuous membership, TC/XDP/qdisc, NIC/route/firewall/offload 변경을 하지 않습니다.

Unit의 `ProtectKernelModules=yes`는 `/usr/lib/modules`와 build symlink 접근을 가립니다. 현재 unit은 **`Environment=BCC_KERNEL_SOURCE=/usr/src/linux-headers-%v`**로 matching distro headers를 명시합니다. 다른 배포판은 실제 header 경로를 검토해야 하며 오류를 capability 추가·module protection 해제로 숨기지 않습니다. `MemoryDenyWriteExecute`, no-new-privileges·seccomp·host namespace와 나머지 hardening을 유지합니다.

Handoff는 `/run/afterglow-flow`0750 root:`afterglow-flow-read`, atomic `snapshot.json`0640 root regular·single-link inode입니다. `observer-flow-read.conf`를 **실제 기존 observer unit**의 drop-in으로 설치해 `SupplementaryGroups=afterglow-flow-read`와 read-only 경로만 추가합니다. 기존 `ExecStart`의 HTTPS/host/token/CA/interval/trace allowlist는 보존하고 `--flow-snapshot-file /run/afterglow-flow/snapshot.json`만 덧붙입니다. Fresh snapshot을 확인한 뒤 observer를 재시작하며 **nonroot/CapEff0/NoNewPrivs1/Seccomp2**는 유지합니다. Observer는 directory-FD로 ancestry·정확0640·소유권·single-link를 검사하며 누락/변조/stale/overflow는 flow-source error이지 기존 passive 보고 전체의 폐기가 아닙니다.

표시되는 `linux_skb_header_counter`는 Linux AF_PACKET 관측점의 skb 수/길이입니다. GRO/GSO·VLAN offload·관측 지점은 coverage에 영향을 주며 **물리 wire packets가 아닙니다**. 첫 표본·collector/boot/NIC identity 변경·counter reset·stale·overflow·오류는 unknown/null이지0이 아닙니다. 유효한 연속 표본의 변화0만 실측0입니다. NIC 전체 RX/TX를 peer에 배분하거나 여러 NIC·양 endpoint·switch counters를 합산하지 않습니다. Collector를 stop/disable하거나 observer의 snapshot 옵션을 제거하면 미계측 상태로 돌아가며 남은 파일을 fresh로 가장하지 않습니다.

#### `[monitoring.infrastructure_fabric]` switch/port 관측

Backend는 **명시적으로 등록한 literal management endpoint**에만 read-only SNMPv3 authPriv GET/GETBULK를 실행합니다. IF-MIB/IF-X-MIB의 counters·ifIndex/ifName/ifType/ifConnectorPresent·discontinuity와 LLDP-MIB·sysUpTime/engine boot/chassis identity를 읽습니다. LLDP 광고 management 주소는 polling 권한이나 target이 아니며 discovery/scan·SNMP SET·default/public community 추측은 없습니다.

| Typed setting | 기본값·범위 |
|---|---|
| `revision` | 0–`2**53-1`; targets가 있으면 양수. source·credential 변경과 disable을 포함한 **모든 편집마다 증가** |
| `targets` | 최대32; backend 전용 Secret/env `MONITORING_INFRASTRUCTURE_FABRIC__TARGETS`의 JSON 배열 권고 |
| `poll_interval_seconds` / `freshness_seconds` | 10(5–300) / 30(5–600), freshness ≥ interval |
| `timeout_seconds` / `retries` / `concurrency` | 2(0.1–10) / 1(0–2) / 4(1–8) |
| `poll_budget_seconds` | 30(1–120) |
| `max_ports` / `max_neighbors` / `max_varbinds` | 256(1–1024) / 256(1–1024) / 16384(256–65536) |
| `retention_seconds` | 3600(10–86400), freshness의 최소2배 |

Target마다 `id`, `name`, expected `chassis_id`, `management_ip`, `username`, protected `auth_key`/`priv_key`가 필요하며 identity/chassis/endpoint는 유일해야 합니다. `port=161`, `auth_protocol=sha256`(sha384/sha512/sha1 지원), `priv_protocol=aes128`, `context_name=""`가 기본값입니다. Secret target 배열을 public ConfigMap/frontend projection·command argv·logs에 넣지 않습니다. Helm은 `monitoring.infrastructureFabric.*`와 `secrets.infrastructureFabricTargets`를 분리하고 Kolla는0600 backend operator TOML 또는 protected backend Secret을 사용합니다. Revision을 내리는 대신 rollback 설정에도 새 revision을 부여하여 lease/generation fence를 갱신합니다.

측정된 cable join은 **ifType6 + ifConnectorPresent1**인 physical port, actual chassis, 모호하지 않은 exact port alias와 physical host NIC evidence가 함께 맞을 때만 허용합니다. LLDP localPortNum은 ifIndex가 아닙니다. Logical/LAG/unknown port·bond 광고·불명확 alias는 cable rate로 승격하지 않고 진단 근거만 남깁니다. Uptime wrap 뒤에도 discontinuity를 보존하며 reboot/identity/reset/stale·누락 packet component는 rate null입니다. Cumulative uint64는 decimal string, rate는 bounded number로 처리합니다. Switch port counters는 해당 port 전체 관측이지 특정 host peer traffic의 대체 측정이 아닙니다.

현재 운영 prerequisite는 **승인된 management endpoint 또는 jump 경로**, read-only SNMPv3 authPriv view, operator-side0600 credential-file의 실제 위치입니다. 사용자에게 물리 switch/port와 Afterglow/collector-only rollout 승인은 받았지만 이 입력은 아직 확보되지 않았습니다. LLDP로 관측한 SG3210X-M2/SG3428X-M2의 광고 주소 `192.168.0.2/.3`는 operator/controller1에서 HTTP/HTTPS timeout이었으며 authorized/reachable 관리 대상으로 단정하지 않습니다. 실제 switch counters·port 매핑·운영 수용은 이 prerequisite를 확보한 뒤 별도 검증해야 합니다.

#### 트래픽 분석 설정

| `[traffic_analytics]` 키 | 기본값·범위 | 운영 의미 |
|---|---|---|
| `enabled` | `false` | Backend HTTP 집계 및 frontend ingest 활성화 |
| `retention_days` | `30`, 1–30 | UTC hourly bucket 시작부터 Redis 보존기간. 늦은 event로 연장하지 않음 |
| `geoip_mmdb` | `""` | backend가 읽을 수 있는 complete offline DB-IP IPv4/IPv6 country MMDB 경로. 미설정은 unconfigured/XX |
| `cluster_cidrs` | `[]`, 최대128 | 검토한 실제 cluster canonical CIDR만 internal로 분류; RFC1918 전체를 자동 신뢰하지 않음 |
| `backend_trusted_proxy_cidrs` | `[]`, 최대128 | backend analytics만의 exact socket-peer/XFF trust |
| `frontend_trusted_proxy_cidrs` | `[]`, 최대128 | frontend reporter evidence를 해석하는 backend analytics만의 exact proxy trust |
| `site_country` | `""` | 운영자가 지정한 서비스 인입 국가. 대문자 ISO-3166 alpha-2를 사용하며 `XX` 금지; 빈 값은 미설정 |
| `hmac_key` | `""` | IP identity HMAC용 backend 전용 secret |
| `frontend_ingest_key` | `""` | 별도 frontend server writer용 bearer secret |

Enabled일 때 두 secret은 **각각 최소 32자이며 서로 달라야** 합니다. Backend Secret 환경 `TRAFFIC_ANALYTICS__HMAC_KEY`, `TRAFFIC_ANALYTICS__FRONTEND_INGEST_KEY`로 주입하고 public TOML/이미지/브라우저 `PUBLIC_*`에 넣지 않습니다. Writer key는 frontend server와 backend ingest만 공유하고 HMAC key는 backend에만 둡니다. HMAC key 교체는 이미 보존된 HLL과 새로운 identity의 연속성을 끊으므로 변경 시 기간 비교·unique 해석을 재검토하세요.

```toml
[traffic_analytics]
enabled = true
retention_days = 30
geoip_mmdb = "/etc/afterglow/geoip/country.mmdb"
cluster_cidrs = [] # 실제 승인 CIDR로 채움; canonical network만, /0 금지
backend_trusted_proxy_cidrs = [] # 실제 ingress peer만, 인증 proxy trust와 별도
frontend_trusted_proxy_cidrs = []
site_country = "KR"
# hmac_key / frontend_ingest_key 실제 값은 backend Secret 환경에서 주입
```

`site_country`는 `coverage.site_country`로 반환하며 빈 값은 null입니다. 현재 validator는 빈 값 또는 `XX`가 아닌 대문자 영문 2자리 형식을 검사하므로 **실제 ISO-3166 국가 코드 선택은 운영자의 책임**입니다. 관리자 세계 지도는 client-country→service-location 논리적 접속 흐름만 그리며 GeoIP 위치를 실제 network route·LLDP·traceroute 증거로 사용하지 않습니다. 서비스 국가를 설정해도 미확인 client IP에 국가를 만들어 주지 않습니다.

Complete [DB-IP IP to Country Lite MMDB](https://db-ip.com/db/download/ip-to-country-lite)를 운영자가 사전에 provision하고 provider release·source URL·**압축 해제된 database의 SHA-256**을 보존합니다. CSV 범위표를 CIDR 표로 간주하거나 행/국가 일부를 잘라 넣지 않습니다. 2026-10 qualification dataset은 8,348,509bytes, SHA-256 `dbd70ccfa2a13627eaf4913d19920a1a229f1b3c5439ac01c509995b6364202a`, build metadata version `2026-10-01`이며 다른 release의 pin으로 재사용하지 않습니다. 압축 archive의 checksum과 database checksum은 다릅니다. Lite의 **CC BY4.0 attribution** `IP Geolocation by DB-IP (https://db-ip.com), CC BY 4.0`을 결과 화면/coverage에 유지합니다. Runtime download·외부 IP lookup/IP 전송은 없습니다. 미설정·DB 오류·주소 누락·nonglobal·DB 미일치를 `XX`와 별도 사유로 표시하고 `site_country`로 대체하지 않습니다.

배포 경로(backend read-only, 모든 replica가 같은 bytes/revision 사용):

- Compose 세 manifest: `TRAFFIC_ANALYTICS_GEOIP_MMDB_FILE`에 검토된 absolute host MMDB 파일을 지정하면 `/etc/afterglow/geoip/country.mmdb:ro`로 mount합니다. `[traffic_analytics].geoip_mmdb` 또는 `TRAFFIC_ANALYTICS__GEOIP_MMDB`도 이 container 경로와 맞춥니다. 기본 `/dev/null` mount는 국가 DB가 아닙니다. Dev runner 사용 시 실제 private snapshot/env에 반영합니다.
- Kolla: `afterglow_traffic_analytics_geoip_mmdb_source` + `afterglow_traffic_analytics_geoip_mmdb_sha256`를 함께 제공합니다. 기본 target-host `afterglow_traffic_analytics_geoip_mmdb_runtime_path={{ afterglow_runtime_config_dir }}/traffic-country.mmdb`, container `afterglow_traffic_analytics_geoip_mmdb_path=/etc/afterglow/geoip/country.mmdb`입니다. Config/start tasks는 absolute path·regular/nonsymlink/readable·0<size≤64MiB·lowercase64hex pin 일치를 요구합니다. Root-owned0644 copy를 backend에 read-only mount하고 final TOML에 경로를 연결하며 source/pin/installed checksum을 restart identity에 포함합니다. Source가 비어 있으면 별도 operator MMDB 경로를 덮어쓰지 않습니다. 자세한 필드는 [Kolla guide](../deploy/kolla/README.md#offline-country-mmdb-and-observation-settings)를 따릅니다.
- Helm: `trafficAnalytics.geoipExistingClaim`에 **사전 provision한 PVC**를 지정하고 `trafficAnalytics.geoipMmdb=/etc/afterglow/geoip/country.mmdb`를 함께 지정합니다. PVC root에 `country.mmdb`가 있어야 하며 `/etc/afterglow/geoip`에 backend 전용 read-only mount합니다. 다른 path 조합은 template에서 거부합니다. PVC 생성/download/checksum 검증은 chart가 대신하지 않습니다. 스케줄되는 모든 backend replica가 같은 pinned dataset을 읽을 수 있는 storage/access mode가 필요합니다.
- 정적 Kubernetes: `deploy/k8s-template/overlays/traffic-country-mmdb`는 `afterglow-country-data`라는 existing PVC를 backend에만 read-only mount하고 `TRAFFIC_ANALYTICS__GEOIP_MMDB`를 설정합니다. 해당 namespace의 PVC를 먼저 provision합니다. `generate_k8s.py`는 TOML 경로를 렌더링하므로 생성 manifest에도 실제 PVC mount를 명시해야 하며 path만 설정하는 것으로 파일을 만들지 않습니다.

Lookup는 memory-mapped reader를 재사용하므로 dataset 교체 뒤 backend process를 rollout/restart합니다. 운영자는 mount 전 pin을 검증하고 기존 dataset/metadata/pin을 복구용으로 보존합니다. 권한·파일 오류를 빈 DB 또는 다른 provider fallback으로 숨기지 않습니다.

Frontend **서버 프로세스** 환경은 다음과 같습니다.

| 환경변수 | 값·주의 |
|---|---|
| `TRAFFIC_ANALYTICS_INGEST_URL` | backend의 `/api/v1/monitoring/traffic/events` 전체 URL. Frontend server가 실제 도달하는 internal HTTP 또는 HTTPS 경로 사용; userinfo/query/fragment 금지 |
| `TRAFFIC_ANALYTICS_INGEST_KEY` | backend `frontend_ingest_key`와 동일한 secret, 최소 32자 |
| `TRAFFIC_ANALYTICS_PEER_IS_SOCKET` | **정확히 `true`**, `ADDRESS_HEADER` 미설정일 때만 adapter `getClientAddress()`를 원래 socket peer로 증명; 아니면 peer_unverified |

URL/key가 없거나 invalid면 frontend reporter는 비활성입니다. `ADDRESS_HEADER`는 unset으로 유지하고 `XFF_DEPTH`나 기존 client-address trust 스위치로 provenance를 대신하지 않습니다. Reporter는 schema_version2의 bounded `peer_ip`/`peer_verified`/`forwarded_for` evidence만 보호된 writer 경로로 전달합니다. 최종 국가/origin 판정은 backend의 `frontend_trusted_proxy_cidrs`가 맡습니다. Malformed/과대 XFF는 원문을 자르거나 부분 신뢰하지 않고 invalid evidence로 처리합니다. 원본 peer가 allowlist 밖이면 위조 헤더는 주소 권한을 얻지 않습니다.

Backend는 **`uvicorn app.middleware.traffic_address:create_app --factory --no-proxy-headers`**로 실행합니다. 가장 바깥 wrapper가 원래 TCP peer를 private ASGI extension에 보존한 뒤 안쪽 `ProxyHeadersMiddleware`만 기존 **`FORWARDED_ALLOW_IPS`**로 인증/URL scheme 주소 rewrite를 수행합니다. Outer Uvicorn `--proxy-headers` 또는 `app.main:app` 직접 실행으로 먼저 rewrite하면 analytics provenance를 잃어 unknown이 됩니다. `backend_trusted_proxy_cidrs`/`frontend_trusted_proxy_cidrs`는 이 인증 trust 및 `TRUSTED_PROXIES`/rate-limit/session binding과 독립입니다. Exact proxy와 전체 bounded XFF chain을 검증하고 오른쪽의 trusted hop만 제거합니다. Canonical CIDR·/0 금지·각128개 한도를 지키며 인터넷 전체나 모든 private 대역을 신뢰하지 않습니다. Cluster CIDR에 속한 검증 주소만 internal, 그 밖의 global 주소만 external, 나머지는 unknown입니다. `/api/monitoring`, UA, HTTP status, proxy 경유 여부만으로 origin을 정하지 않습니다.

Frontend reporter는 SSR/server 요청만 보내고 backend 요청과 별도 집계합니다. Browser-only SPA 이동·CDN/static bypass·edge request는 누락되며 정상 화면이라도 관측 coverage가 완전하지 않을 수 있습니다. Writer는 2 KiB·±120초 event만 수락하며 frontend 16 inflight/2초 deadline·backend Redis write 250 ms 제한에서 실패한 보고가 원래 사용자 응답을 막지 않습니다. `available/partial/unavailable/disabled`, drop counts·geo state·observed interval을 같이 확인하고 빈 store/null을 정상 0으로 취급하지 않습니다.

원문 IP는 frontend→backend 보호된 전송 및 메모리 계산에만 필요합니다. Durable 집계는 IP HMAC의 HLL 추정치와 country/고정 route/origin별 수치이며 사람이 아니고 packet bandwidth가 아닙니다. Request/response body, cookie, user agent, token, raw IP, URL/query는 분석 저장소에 보관하지 않습니다. 중복 방지 UUID만 bounded Redis table에 TTL 300초로 남습니다. MMDB/secret mount·Redis 접근·로그 정책도 이 경계에 맞춰 운영하고 request payload를 별도 수집하는 것으로 확대하지 않습니다. 로그인 모니터링은 기존 ActivityLog와 session store를 읽을 뿐 실패 로그인 수집을 추가하지 않으며, Redis/SQL 보존 정책 밖 이력·현재 온라인 상태를 보장하지 않습니다.

#### 설정 migration·rolling 순서·rollback

이 관측 변경은 **SQL migration이 없습니다**. 기존 Redis primary/DB/namespace·hourly bucket/HLL/dedupe/history와 HMAC/writer/observer·app encryption/auth key를 보존합니다. 과거에는 raw IP가 없으므로 기존 bucket은 `legacy_unclassified`로 표시하며 국가/origin을 소급 판정하거나 store를 flush하지 않습니다. Config 모델은 `extra="forbid"`이므로 `geoip_csv`, `trust_frontend_client_address` 등 obsolete TOML key를 base와 모든 active override에서 제거해야 합니다. Merge는 삭제를 표현하지 않으므로 새 override를 덧씌우는 것만으로 해결되지 않습니다. 이전 frontend `TRAFFIC_ANALYTICS_TRUST_CLIENT_ADDRESS` 및 Kolla `afterglow_traffic_analytics_trust_client_address`도 사용하지 않고 현재 socket-peer contract로 전환합니다.

1. Original private inputs/env·generated layers·image digests·Redis history/기존 key·MMDB bytes/pin·collector/observer unit/config을 보호된 복구 지점에 보존합니다. 실제 proxy chain, cluster 주소 소유권, PVC access와 각 host의 headers/capability 조건을 먼저 승인합니다.
2. Complete dataset을 provision하고 새 key가 아닌 **기존 key**를 유지한 정리된 TOML·Secret·factory launcher를 준비합니다. Kolla는 Afterglow-only genconfig→pull→prechecks 후 승인된 controller별 reconfigure를 사용하며 sibling/stock service·inventory·network를 바꾸지 않습니다.
3. **Backend reader/API/factory를 먼저**, 그 다음 frontend schema-v2 reporter, 그 다음 확장 observer/collector를 전환합니다. Old observer의 flow 미제공은 unsupported이고 old frontend event는 legacy-unclassified로 유지합니다. 신/구 backend writer가 섞인 동안 전체 origin coverage를 선언하지 않으며 모든 backend/API 및 해당 worker 설정 consumer가 새 config를 읽은 뒤 frontend/new observation을 활성화합니다. 실제 운영 mixed-version·rollback 호환성은 별도 qualification 전에는 보장하지 않습니다.
4. 승인된 별도 collector 설치/start와 fresh read-only handoff 후 observer를 전환합니다. LLDP 도구/read socket 및 switch credential/view는 독립 prerequisite입니다. 새로운 fabric source·credential·disable마다 revision을 증가시키고 모든 backend에 동일 revision을 배포합니다. Rollout 후 direct/untrusted 헤더·HTTPS redirect·writer/observer/admin 인가·fresh/reset/stale/unknown과 기존 history를 각각 확인합니다.

Rollback은 새 collector를 먼저 stop/disable하고 old observer command/drop-in을 복원한 뒤 frontend writer를 호환 버전으로 내리거나 수집을 중지합니다. 보호된 old TOML/env/launcher/MMDB bytes+pin과 image를 함께 복원하여 backend/API/설정 consumer를 되돌립니다. New-only TOML을 old binary에 남기지 않으며 이미지 downgrade만으로 config 호환을 보장하지 않습니다. 새 binary를 유지하며 fabric 설정을 되돌릴 때는 **이전 값 + 더 높은 revision**을 사용합니다. Redis/history·키·volume·system Python·network를 삭제/재생성하지 않으며 별도 schema migration의 rollback과 혼동하지 않습니다. 기존 배포1.30.x 수용 기록은 해당 시점의 역사적 증거로 유지하고 이 기능의 새 운영 수용으로 승격하지 않습니다.

### 2. 기본 서비스 시작

```bash
# frontend/backend만 실행. 먼저 외부 DB·Redis 및 인증 설정을 준비한다.
docker compose -f docker-compose.yml up -d
```

### 3. 현재 형제 소스를 포함한 로컬 서비스 스택

로컬 개발은 아래 root 명령으로 `afterglow-local-services` **한 project만** 실행합니다.
`docker-compose.dev.yml` 하나가 frontend `3080`, backend `8000`과 필수 sibling 서비스를
기본 실행합니다. 기존 `afterglow` project의 컨테이너가 남아 있으면 시작 전에 거부합니다.
Runner는 다른 project를 자동 삭제하지 않습니다.

사전 조건은 다음과 같습니다.

- Docker Compose **2.24 이상** (optional env file 지원).
- Python **3.12 이상**과 이 checkout의 `afterglow.conf`, `.env`. Python은 `backend/.venv/bin/python`을 우선 사용하고, 없으면 `python3`를 사용합니다.
  root 원본은 변경하지 않습니다. 첫 실행은 `afterglow.conf`를 private
  `.local-services/afterglow.conf`로 복사하고, 별도 JWT/암호화/service key를
  `.local-services/secrets.json`에 생성합니다. 디렉터리는 0700, config snapshot은 0640이며
  snapshot을 mount하는 서비스에만 파일의 실제 GID를 `group_add`로 전달합니다. Linux에서도
  image의 non-root UID를 바꾸지 않고 읽을 수 있습니다. 키와 `compose.env`는 0600으로 유지하고,
  모든 private 파일은 Git과 Docker build context에서 제외합니다. 이후 실행은 snapshot과 키를 보존합니다.
  `services:config`/`services:up`은 이 입력을 `.local-services/compose.env`(0600)에도 저장하여
  명시적인 dev Compose 명령에서 재사용합니다. 이 파일에도 비밀이 있으므로 출력·커밋하지 않습니다.
  OpenStack 인증은 local snapshot의 실제 자격 증명을 사용합니다. 로컬 DB가 격리되어도
  OpenStack 자체는 실제 환경이므로 smoke는 resource mutation이나 provider completion을 하지 않습니다.
- Drover readiness에는 dedicated service project UUID가 필요합니다. `.local-services/afterglow.conf`의 `[openstack] service_project_id` 또는 `.env`의 `OS_SERVICE_PROJECT_ID`로 명시합니다. 시작 전에 누락을 거부하고, admin 프로젝트로 fallback하지 않습니다.
- 로컬 Drover API/worker/migration은 `SENTINEL_ENABLED=false`, `SENTINEL_HOSTS` 빈 값으로 고정하여 private TOML의 운영 Sentinel 설정을 상속하지 않습니다. 실제 cache client도 local Redis를 사용하며 runner가 이 격리를 검사합니다.
- Kubernetes 환경에서 복사한 public OpenStack 경로가 로컬 Docker에 맞는지는 별도로 확인합니다. VPN/internal catalog 접근이 가능한 로컬 환경은 snapshot의 `[openstack] auth_url`에 검증한 versioned internal Keystone URL을, `interface`에 `internal`을 지정할 수 있습니다. 원본 설정과 secret은 보존하고 snapshot 변경 전 `.local-services/backups/`에 mode 0600 백업을 둡니다. Internal 경로도 503이면 상류 OpenStack 장애이며 로컬 재배포나 timeout 연장으로 정상 처리하지 않습니다.
- 현재 소스 build 모드에는 sibling checkout `../lumen`, `../drover`, `../waygate`,
  `../palimpsest`가 필요합니다. 앞의 세 checkout에는 `docker/Dockerfile`, Palimpsest에는
  `docker/hub/Dockerfile`이 있어야 합니다. 이 Dockerfile은 `hub/src`와 Hub package metadata를
  복사하므로 Compose는 `../palimpsest` repository root를 build context로 사용합니다.
- Backend source build는 BuildKit `TARGETARCH`의 `amd64` 또는 `arm64`에 맞는 OpenTofu archive를 선택합니다. Release archive는 일시적 GitHub 5xx에 bounded retry를 적용하고 공식 release manifest에서 고정한 SHA-256과 일치해야 설치됩니다. 지원하지 않는 architecture는 명시적으로 실패하며, OpenTofu download stage는 대용량 runtime package 설치와 분리됩니다.
- 격리된 개발 DB에 실제 provider key를 추가하려면 해당 Lumen 관리 UI/API에 등록합니다.
  운영 snapshot의 암호문을 평가하려면 승인된 경로로 원래 암호화 키도 준비해야 합니다.
  키 없는 metadata/context-preview 성공은 실제 provider completion 검증이 아닙니다.

**서비스별 DB URL 계약**은 다음 다섯 입력입니다. Shell 값이 선택한 Compose env-file보다
우선합니다. Runner의 `services:config/up`은 `.env`를 선택하고, 직접 Compose는
`--env-file`로 명시한 파일(생략하면 자동 `.env`)을 사용합니다. Shell의 명시적 빈 값도
env-file 값을 덮어쓰며, dev에서는 unset/empty일 때 아래 local fallback을 사용합니다.

| Compose 입력 | dev unset/empty fallback |
|---|---|
| `AFTERGLOW_DATABASE_URL` | `mysql+aiomysql://afterglow:dev@afterglow-mariadb:3306/afterglow` |
| `WAYGATE_DATABASE_URL` | `mysql+aiomysql://waygate:dev@service-mariadb:3306/waygate` |
| `DROVER_DATABASE_URL` | `mysql+aiomysql://drover:dev@service-mariadb:3306/drover` |
| `LUMEN_DATABASE_URL` | `mysql+aiomysql://lumen:dev@service-mariadb:3306/lumen` |
| `PALIMPSEST_DATABASE_URL` | `mysql+asyncmy://palimpsest:dev@service-mariadb:3306/palimpsest` |

최소/prod Compose는 nonempty `AFTERGLOW_DATABASE_URL`이 필수이며 local fallback을
사용하지 않습니다. Sibling profile을 실행할 때는 해당 서비스 URL도 준비합니다.
각 서비스의 API·worker·migration/bootstrap은 **같은 서비스 DB**를 사용하며 위 입력이
컨테이너의 `DATABASE_URL`로 전달됩니다. 일반 `DATABASE_URL`은 이 다섯 Compose 목적지를
선택하는 입력이 아닙니다. Kubernetes/Kolla의 기존 runtime secret 이름과는 구분합니다.

`services:config/up`은 외부 DB 목적지를 허용하고 resolved URL을 private
`.local-services/compose.env`(0600)에 보존합니다. URL·비밀번호나 전체 resolved config를
출력·커밋하지 않습니다. 재사용 시에도 shell 값이 이 파일보다 우선하므로 대상 선택을
승인된 비밀 관리 경로에서 확인한 뒤 실행합니다. `services:config`는 입력 준비이며
DB 호환성 검증이 아닙니다. `services:up`은 선택한 DB에서 migration/bootstrap과 실제
API·worker를 실행하므로 외부 URL 설정만으로 live write 승인이 생기지 않습니다.

기본 local MariaDB/PostgreSQL은 host port를 공개하지 않습니다. Redis와 Lumen
checkpointer는 별도 local 대상이며, 시작 전 cache·volume/network·mount·loopback 경계를
검사하고 implicit `docker-compose.override.yml`은 읽지 않습니다. API health와
migration 완료는 대시보드·OpenStack 통신이나 운영 schema 호환성의 증거가 아닙니다.

이미 빌드한 이미지로 복구할 때도 먼저 private 입력을 준비하고 명시적으로 사용합니다.
키와 볼륨은 보존하지만 선택 DB에서 migration/bootstrap을 실행할 수 있으므로,
외부 대상은 아래 평가와 기존 실행 승인이 선행되어야 합니다.

```bash
npm run services:config
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml up -d --no-build --wait
```

외부 DB를 가리킨 Palimpsest bootstrap의 exit 0은 운영 무변경 증거가 아닙니다.
Bootstrap은 설정된 DB에 `create_all`을 실행하므로 누락된 테이블·index·constraint를
생성할 수 있습니다. 과거 실행의 효과는 별도 read-only 운영 검토 대상이며, 복구를 위해
운영 bootstrap을 다시 실행하거나 migration ledger/credentials를 변경하지 않습니다.

#### 외부 DB timeout과 Docker subnet 겹침

Image build 성공 뒤 migration/bootstrap의 DB connect가 timeout이면 build 실패와
구분합니다. 먼저 원래 실패 container의 exit/OOM/시각·sanitized DB host와 log를
보존하고 host TCP와 실제 container TCP를 비교합니다. 현재 `compose config`의
선택 입력은 이미 생성된 container 입력과 다를 수 있으며 비밀번호·전체 env는
출력하지 않습니다.

Host는 연결되는데 container가 실패하면 모든 Docker bridge의 IPAM subnet을
VPN/OpenStack DB route와 비교합니다. 2026-10-11에는 완료된 Lumen QA bridge의
`172.30.0.0/16`이 외부 DB 대역과 겹쳤습니다. 사용자 승인 뒤 해당 bridge만
검증된 비중복 대역으로 옮겨 세 기존 datastore의 ID·PID·StartedAt·host port·mount와
DNS alias를 보존했고, 실제 dev container의 controller/VIP TCP와 SELECT-only 인증을
확인했습니다. 새 대역은 환경의 모든 Docker/host/VPN route와 비교하여 정하며
특정 사설 대역을 모든 머신의 안전한 기본값으로 취급하지 않습니다.

네트워크 복구는 schema/writer 호환성 승인이 아닙니다. 운영 URL을 선택한
`up --build` 재시도는 migration/bootstrap·writer를 실행할 수 있으므로 아래
snapshot·키·양방향 호환성과 기존 운영 실행 승인을 먼저 충족합니다. 기존 DB·volume을
삭제하거나 전체 network prune, 타 project 중지, 인증/에러 우회로 복구하지 않습니다.

#### 운영 데이터와 양방향 호환성 평가

외부 DB를 허용하는 이 정책은 과거의 무조건 local-only 정책을 대체합니다. 기존
architecture/release 장애 기록은 당시의 기록으로 보존하며, 이 변경으로 과거 실행이
안전했다고 재해석하지 않습니다. **운영과 같은 URL은 같은 DB를 직접 공유하는 것**이지
동기화/replication이나 자동 데이터 복사가 아닙니다. 운영 DB를 개발 평가 대상으로
시작하지 말고, 승인된 격리 환경에 복원한 production snapshot을 우선 사용합니다.
개발 qualification은 disposable 대상에서 수행하고 운영 DB를 조회·변경하지 않습니다.
현재 운영 증거는 운영자가 승인된 경로로 제공한 자료로 평가합니다.

1. 운영자가 제공한 현재 배포 source SHA·image revision/digest와 후보 버전을 비교합니다.
   Schema 증거의 시점·대상을 기록하고 각 서비스 manifest의 logical ID·SQL 경로·SHA-256을
   적용 ledger 및 실제 schema와 대조합니다. Afterglow는 `backend/migrations/manifest.txt`,
   Drover/Lumen/Waygate는 각 sibling의 `<service>/migrations/manifest.txt`가 기준입니다.
   알 수 없는 ledger 항목, 더 최신 schema 또는 checksum drift를 자동 호환으로 취급하지
   않습니다. 증거가 없으면 운영 qualification 미확인으로 명시합니다.
2. Pending migration의 DDL·backfill·constraint·삭제/변환·lock 영향을 검토하고 승인 범위를
   정합니다. 현재 Compose one-off는 `python -m drover.scripts.migrate --apply`,
   `python -m lumen.scripts.migrate --apply`, `python -m waygate.scripts.migrate --apply`와
   `palimpsest-hub-bootstrap`입니다. 앞의 세 runner는 manifest checksum과
   `schema_migrations`를 검사하지만 **`--apply` 없이도 ledger 테이블을 생성할 수 있어
   read-only 운영 검사 명령이 아닙니다**. Lumen apply에는 history backfill/검증도 있습니다.
   Palimpsest bootstrap은 `Base.metadata.create_all`이며 기존 테이블 변경을 수행하는
   migration이나 schema 호환성 판정이 아닙니다. Exit 0만으로 승인/무변경을 주장하지 않습니다.
3. 복원한 disposable DB에서 후보 writer/이전 schema와 이전 배포 writer/후보 schema의
   read/write·암호문 복호화·제약·데이터 의미를 **양방향** 검증합니다. 실패 시 필요한
   migration/중지 순서를 기록하고, API와 worker의 mixed-version 및 rolling upgrade 중
   queue payload·동시 writer 동작도 검증합니다. 새 빈 DB 테스트 성공으로 대체하지 않습니다.
4. 원래 ciphertext 키와 key 식별/rotation 상태를 승인된 비밀 경로로 보존합니다. 현재
   dev runner가 생성하는 local 키는 외부 DB 암호문과 호환된다는 증거가 아닙니다.
   다섯 URL만 설정해도 외부 키, Redis, PostgreSQL 또는 Palimpsest CAS/blob를 자동으로
   가져오지 않습니다. Lumen durable checkpointer·필요한 memory PostgreSQL, Redis
   queue/cache/session과 CAS 참조/실제 blob의 일관된 복원·격리도 별도 확인합니다.
5. 운영 snapshot과 평가 DB의 engine/version·charset·collation·`sql_mode`를 비교하고,
   DB뿐 아니라 관련 key/checkpointer/Redis/CAS의 backup+restore를 실제 시험합니다.
   DDL implicit commit·backfill·삭제 데이터 때문에 image downgrade만으로 schema/data가
   돌아오지 않을 수 있습니다. 복구 시점·허용 데이터 손실·writer 정지 순서·rollback 제한을
   명시하고 검증하지 않은 downgrade를 약속하지 않습니다. 기존 live write/migration 승인,
   volume·key 보존과 `down --volumes`/prune 금지는 그대로 적용합니다.

전체 dashboard가 필요 없는 서비스 개발은 아래와 같이 선택적으로 실행합니다.

```bash
npm run services:config -- --only lumen,palimpsest
npm run services:up -- --only lumen,palimpsest
```

`--only`는 `lumen`, `waygate`, `palimpsest`의 comma-separated 선택을 받으며 선택한 API/worker·migration/bootstrap와 필요한 local datastore만 시작합니다. 기존 canonical project·port·volume·key를 그대로 사용하고 이미 실행 중인 다른 service를 종료하거나 orphan을 삭제하지 않습니다. 선택하지 않은 sibling checkout·Drover service-project·Waygate callback 검사는 하지 않습니다. `--only lumen`은 ordinary Lumen API key로 검증할 수 있어 OpenStack credential을 config 사전 조건으로 요구하지 않습니다. Hub는 genuine Keystone 인증과 system-admin 확인에 실제 service credential이 필요합니다. Waygate를 선택하면 기존 VM-reachable `WAYGATE_PUBLIC_BASE_URL` 요구는 유지됩니다.

`npm run services:verify -- <lumen|waygate|palimpsest>`는 Docker 기동·전체 config와 독립적이며 `<SERVICE>_API_BASE_URL`로 로컬 프로세스나 별도 HTTP(S) 테스트 endpoint를 직접 지정합니다. 기본 모드는 인증된 read-only 연결 확인입니다. `--exercise`만 provider 또는 run-owned client/blob mutation을 수행하며 필수 scope·model·server·artifact 및 정리를 검증합니다. URL/auth/project 입력, 서비스별 시나리오와 미검증 경계는 [Service-real 가이드](testing.md#독립-서비스-실제-로직-검증-service-real)를 따릅니다. 기존 `services:smoke`의 full-stack/read-only dashboard 경로는 그대로 유지합니다.

```bash
# 현재 sibling source와 Afterglow source를 build하고, migration/bootstrap 뒤 API+worker를 시작
npm run services:up

# migration/API readiness, Lumen billing 계약, BFF/context와 실제 대시보드 summary/quotas 확인
# 아래 BFF 검사는 shell에만 둔 short-lived Afterglow access token과 해당 사용자가 소유한
# conversation 및 model ID/이름이 필요하다. token 값은 출력되지 않는다.
export AFTERGLOW_SMOKE_TOKEN='<short-lived-afterglow-access-token>'
export LUMEN_SMOKE_MODEL_ID='<active-lumen-model-id>'
export LUMEN_SMOKE_CONVERSATION_ID='<conversation-owned-by-the-smoke-user>'
# 필요할 때만 token의 허용된 project UUID를 지정
export AFTERGLOW_SMOKE_PROJECT_ID='<project-uuid>'
npm run services:smoke

# 이 project만 정지한다. named volumes, 이미지, 다른 Compose project는 보존한다.
npm run services:down
```

`services:smoke`는 migration/bootstrapping container의 successful exit, worker의 running
state, backend/frontend와 모든 service API endpoint를 확인합니다. Drover는 실제
`/v1/health/ready`로 DB·Redis·migration ledger·Keystone service credential readiness를
확인합니다. 인증 BFF는 Waygate/Drover/Palimpsest discovery와 각 service의 read-only list
endpoint, Lumen `/chat/models`를 통과한 뒤 model provider를 호출하지 않는 read-only
`context-preview`를 호출하고 현재 breakdown 계약과 완료된 토큰 합계를 검증합니다.
추가로 Lumen OpenAPI의 `billing_admin_key`와 bulk billing GET 계약을 검사하여 구 API 연결을
거부합니다. 마지막에는 cache를 사용하지 않는 dashboard overview summary/quotas와
`k3s-stats`를 모두 조회합니다. Drover 통계는 HTTP 200만으로 통과하지 않고
`available: true` 및 유효한 total/active 수가 있어야 합니다. SDK가 보내는 기존 Keystone
token의 project scope도 보존되어야 하므로, 기본 project가 있는 관리자 계정의 성공만으로
일반 사용자 통신을 검증했다고 판단하지 않습니다. 하나라도 실패하면 smoke는 nonzero로
종료합니다. 예를 들어 Nova가 503이면 다른 service BFF가 정상이어도 전체 smoke는 실패합니다.
model 또는 conversation이 없는 새 환경에서는 provider/model metadata와 smoke 사용자의
conversation을 먼저 정상 **로컬** 관리 UI/API로 준비해야 하며, runner는 이를 만들지 않습니다.

각 HTTP smoke 요청의 deadline은 30초입니다. 실제 Keystone 확인을 포함하는 readiness에
더 짧은 별도 deadline을 덧씌우지 않으며, timeout이나 비정상 응답을 성공으로 바꾸거나
자동 재시도하지 않습니다. Provider key가 없는 모델 metadata/context-preview 성공은
실제 Sonar completion이나 검색 출처 반환의 성공 증거가 아닙니다.

현재 sibling source가 없으면 `services:up`은 시작 전에 중단합니다. 오래된 이미지로
fallback하는 개발 모드는 없습니다. Published image 실행은 prod manifest를 사용합니다.

```bash
# private 입력 준비 후 직접 dev Compose 사용
npm run services:config
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml up -d --build --wait

# 이미 실행 중인 dependency는 유지하고 Afterglow frontend/backend만 재빌드·재생성
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml \
  up -d --no-deps --force-recreate --build backend frontend

# 기존 선택적 개발 모니터링 profile
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml --profile monitoring up -d
```

Lumen migration이 `ModuleNotFoundError: lumen_plugin_api`로 SQL 실행 전에 종료되면 sibling Lumen의 workspace dependency/lock/runtime source가 일치하는 이미지인지 확인합니다. 현재 Lumen Docker build는 `uv sync --locked`와 최종 non-root runtime의 migration CLI import 검사를 수행합니다. 컨테이너에 임시 package를 설치하거나 migration ledger/volume을 삭제하지 말고, `lumen-api`/`lumen-worker`를 중지하고 local schema를 백업한 뒤 source build → migration → API/worker 시작 순서로 복구합니다. `npm run services:up`은 같은 dev manifest와 project를 사용해 전체 local readiness를 확인합니다.

### 로컬 서비스 포트와 경계

| 서비스 | Loopback port | 확인 경로 | 비고 |
|---|---:|---|---|
| frontend | 3080 | `/health` | 유일한 로컬 UI 주소 |
| Afterglow BFF | 8000 | `/api/v1/health` | 기본 local DNS, 명시 endpoint override 가능 |
| Redis | 6379 | container 내부 `redis:6379` | Compose project별 volume |
| Waygate API | 8010 | `/v1/health` | API + worker |
| Drover API | 8011 | `/v1/health/ready` | API + worker + migration |
| Lumen API | 8012 | `/v1/health` | API + worker + checksum migration |
| Palimpsest Hub | 8020 | `/v1/health` | API + worker + bootstrap |
| service-mariadb | 공개 안 함 | Compose healthcheck | 로컬 service schemas 전용 |
| afterglow-mariadb | 공개 안 함 | Compose healthcheck | Afterglow schema bootstrap 전용 |
| lumen-postgres | 공개 안 함 | Compose healthcheck | API·worker 공통 durable checkpointer |

이전 alternate port(`13080`/`18000`/`1801x`) 스택은 더 이상 별도로 운영하지 않습니다.
기존 `afterglow`에서 전환할 때는 소유권을 확인한 컨테이너와 앱 이미지만 제거하고 named
volumes·설정·키와 다른 프로젝트는 보존합니다. `docker system prune`이나 `down --volumes`는
사용하지 않습니다. 정상 운영 중 정지는 `npm run services:down`으로 이 project에만 한정합니다.

### 로컬 API endpoint 선택과 원격 OpenStack

Keystone·Nova·Neutron 등 실제 OpenStack은 원격 클라우드를 그대로 사용합니다. 독립 서비스만
로컬로 연결하려면 `SERVICE_WAYGATE_INTERNAL_URL`, `SERVICE_DROVER_INTERNAL_URL`,
`SERVICE_LUMEN_INTERNAL_URL`, `SERVICE_PALIMPSEST_INTERNAL_URL` 또는 `[services]`의
동명 `*_internal_url`을 설정합니다. BFF와 Drover/Waygate SDK에 함께 적용됩니다.

Dev runner는 shell/`.env` → nonempty `.local-services/afterglow.conf` → Compose DNS를
선택합니다. 일반 경로는 명시적 빈 환경 변수로 해당 서비스만 카탈로그로 돌립니다. 기존 private
snapshot은 원본 설정 변경으로 덮어쓰지 않습니다. `services:config`는 선택값을 private
`compose.env`에 보존하고 `services:up`은 새 환경을 반영합니다. 기본·운영 실행의 일반 경로는
override가 없으면 카탈로그를 사용합니다. 아래 패키지 예외와
[주소 예시와 우선순위](openstack-service-catalog.md#로컬-direct-서비스-엔드포인트-오버라이드-direct-service-endpoint-overrides)를 따르세요.

**Palimpsest 패키지 예외:** 허용된 native package key 경로와 브라우저 package BFF는
신뢰된 nonempty `SERVICE_PALIMPSEST_INTERNAL_URL` 또는 `[services] palimpsest_internal_url`이
필수입니다. 환경 변수가 TOML보다 우선하며 최종 URL이 없거나 빈 값이면 패키지 요청은 **503**입니다.
카탈로그·관리자 자격 증명으로 endpoint를 탐색하거나 토큰을 교환하지 않습니다. Native key는 그대로,
브라우저 요청은 원래 사용자/프로젝트의 Keystone 토큰으로 Hub에 전달합니다. 일반 legacy JWT Hub
경로의 기존 카탈로그 동작은 유지합니다. 운영 URL은 **HTTPS**여야 하며 패키지 프록시는 redirect를
거부하고 다운로드를 스트리밍하며 응답에 `Cache-Control: private, no-store`를 적용합니다.

읽기 쉬운 namespace는 등록 전에 Hub 운영자가 `PALIMPSEST_HUB_PACKAGE_NAMESPACE_BINDINGS`로
정확한 Keystone project UUID/ID에 바인딩해야 합니다. ID는 opaque 값이므로 대소문자·하이픈을
정규화하거나 project 표시명에서 추론하지 않습니다. 복사할 참조의 `package_authority`는 Hub의
신뢰된 HTTPS `PALIMPSEST_HUB_PACKAGE_PUBLIC_ORIGIN`에서 제공하며, 내부 서비스 URL이나 브라우저
origin에서 추론하지 않습니다. Public origin이 없으면 authority는 `null`이며 대체 host를 만들지 않습니다.

`LUMEN_MCP_CONTROL_PLANE_URL`은 Lumen이 Afterglow를 호출할 주소입니다. 브라우저의
`PUBLIC_API_BASE`와 Waygate callback origin은 별도입니다. 전체 local stack을 준비하거나
Waygate API/worker를 시작할 때는 `WAYGATE_PUBLIC_BASE_URL=https://waygate.example.com`처럼
gateway VM에서 도달 가능한 HTTP(S) origin을 명시해야 합니다. `services:config`는 검증된 값을
private `compose.env`에 보존하고 Compose가 이를 `WAYGATE_CALLBACK_BASE_URL`로 전달합니다.
새 VM callback은 이 origin의 direct Waygate `/v1/servers/.../agent` 경로를 사용합니다.
개발 컨테이너 DNS, `localhost`, loopback 주소와 Afterglow BFF 경로를 사용하지 않습니다.
Waygate가 이미 실행 중일 때 `--no-deps`로 frontend/backend만 재생성하는 명령은 이 값 없이도
manifest를 parse할 수 있지만, 빈 값으로 Waygate 자체를 시작하면 service startup validation이
fail-closed합니다.

### 4. 운영 이미지와 TLS HAProxy

Prod는 `afterglow-production` project에서 frontend/backend, private persistent Redis,
HAProxy **3.2**를 기본 실행합니다. 앱 컨테이너는 host port를 열지 않고 HAProxy만
80/443 및 선택 서비스용 TLS listener 8010/8011/8012/8020을 공개합니다. `/api/`,
`/v1/`, `/.well-known/`, API docs는 backend, 나머지는 frontend로 전달합니다.
SSE와 WebSocket 연결은 유지하며, 외부 `X-Forwarded-*`는 edge에서 덮어씁니다.

HTTPS 요청의 slash 정규화307이 `Location: http://...`를 반환하면 경로를 고치거나 redirect를 끄지 말고 기존 `FORWARDED_ALLOW_IPS`를 확인합니다. 현재 backend launcher는 `app.middleware.traffic_address:create_app --factory --no-proxy-headers`로 원래 socket peer를 먼저 보존하며, **안쪽** Uvicorn `ProxyHeadersMiddleware`만 같은 환경 변수로 인증/HTTPS scheme을 rewrite합니다. 바깥 `--proxy-headers`를 다시 켜지 않습니다. Kolla의 `afterglow_backend_forwarded_allow_ips`는 loopback 및 `loadbalancer` inventory API IP를 유지합니다. 별도 ingress는 실제 proxy peer IP/CIDR만 override하며 host network에서 `*`를 쓰지 않습니다. Prod Compose의 기존 `FORWARDED_ALLOW_IPS=*`는 host port가 없는 private app network 계약으로 보존하며 analytics CIDR allowlist로 대체하거나 확대하지 않습니다.

Kubernetes 생성기의 `[app].trusted_proxies`와 Helm의 `app.trustedProxies`는 backend `FORWARDED_ALLOW_IPS`로 전달됩니다. 실제 Ingress peer 범위를 명시해야 하며 기본값은 loopback 전용입니다. 정적 ConfigMap은 해당 환경 변수 key와 인라인 `trusted_proxies`를 함께 맞추고 backend를 rollout합니다. 검증은 공개 HTTPS slash URL의307 Location이 HTTPS인지, query/method가 보존되는지, 정규화 URL의 인증 거부가 유지되는지와 direct HTTP·비신뢰 peer의 위조 헤더 무시를 구분합니다. 공개 `ORIGIN`/OAuth URL은 내부 HTTP service URL과 별개입니다.

국가/origin 분석의 `backend_trusted_proxy_cidrs`·`frontend_trusted_proxy_cidrs` 및 `cluster_cidrs`는 **별도의 관측 권한**입니다. 기존 `FORWARDED_ALLOW_IPS` 변경이 분석 허용 목록을 채우지 않으며 그 역도 마찬가지입니다. Frontend adapter는 `ADDRESS_HEADER` 없이 socket peer를 보존하고 `TRAFFIC_ANALYTICS_PEER_IS_SOCKET=true`로 증명합니다. 실제 edge header overwrite와 전체 chain을 검토한 뒤 source별 analytics CIDR만 지정합니다.

운영 주의사항: Uvicorn이 HAProxy 등의 리버스 프록시 IP를 신뢰하게 되면, 프록시가 주입하는 `X-Forwarded-For`가 Uvicorn의 클라이언트 IP로 해석됩니다. 기존에 프록시가 비신뢰 상태여서 프록시 내부 VIP/IP 대역으로 발급되었던 세션 토큰은, `token_ip_binding_mode = "subnet"` 활성화 시 프록시 전환 직후 클라이언트 실제 공인 IP와의 서브넷 불일치로 401(토큰 출처 불일치)이 발생하여 재로그인이 요구될 수 있습니다. 이는 의도된 보안 바인딩 동작입니다.

운영자가 별도 mode 0600 env 파일에 `SECRET_KEY`, `OS_PASSWORD`, `AFTERGLOW_DATABASE_URL`,
HTTPS `ORIGIN`, HTTPS `PUBLIC_API_BASE`, 절대 경로 `TLS_CERTS_DIR`를 설정합니다.
`afterglow.conf`에는 해당 환경의 Keystone URL·사용자·domain/project 등 나머지 설정을
준비합니다. 인증서 디렉터리에는 실제 도메인에 유효한 certificate chain과 matching
unencrypted private key를 포함한 PEM을 둡니다. Mount는 read-only이고 인증서가
없거나 잘못되면 HAProxy가 시작하지 않습니다. 자동 self-signed 발급은 없습니다.

```bash
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml pull
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml up -d --no-build --wait

# Docker DNS round-robin pool: frontend/backend 각각 최대 10 replicas
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml up -d --no-build --wait --scale frontend=2 --scale backend=2
```

이미지 registry 기본값은 `ghcr.io/openstack-afterglow`입니다. 배포 시 검토한 `IMAGE_TAG`
또는 개별 service tag를 고정하세요. `AFTERGLOW_BACKEND_IMAGE`, `AFTERGLOW_FRONTEND_IMAGE`,
`AFTERGLOW_WORKER_IMAGE`, 각 sibling의 `*_API_IMAGE`/`*_WORKER_IMAGE`에는 tag 또는 digest를
포함한 **완전한 image reference**를 지정할 수 있습니다. 현재 Afterglow CI는 amd64를
발행하므로 ARM에서 published 이미지를 실행하려면 호환 manifest 확인 또는 명시적
`DOCKER_DEFAULT_PLATFORM=linux/amd64` emulation이 필요합니다. Dev 소스 빌드는 native입니다.

Backend와 Notion worker가 사용하는 `afterglow-crypto`의 정본은 이 저장소의
`services/afterglow-crypto`입니다. uv는 이를 regular path distribution으로 설치하므로
최종 image가 build-context source path를 필요로 하지 않습니다. Worker image를 게시하기
전에는 실제 배포 architecture로 build한 뒤 최종 image 안에서 다음 smoke를 실행합니다.

```bash
docker buildx build --platform linux/amd64 --target worker --load \
  -t afterglow-worker:test .
npm run test:worker:image -- afterglow-worker:test
```
Notion worker는 SIGTERM/SIGINT에서 대기·동기화 task를 취소하고 스케줄러와 DB 연결을
정리합니다. 배포 전에는 최종 이미지의 기본 `python -m app.notion_worker` 명령을 격리해서
실행하고, 초기 대기 또는 동기화 확인 사이클 뒤 정상 `docker stop`이 timeout 내 exit 0으로
끝나는지도 확인하세요. Crypto smoke 성공과 실제 Notion 동기화 성공은 별도 증거입니다.



일반 경로의 기본 운영은 이미 설치된 형제 서비스의 **Keystone internal catalog endpoint**로
통신합니다. 운영 backend/Notion worker는 unset endpoint를 덮어쓰지 않으므로 TOML 또는 카탈로그를
사용합니다. 명시적인 `SERVICE_*_INTERNAL_URL`/TOML override는 신뢰된 **HTTPS** URL만
허용하고 일반 경로의 빈 환경 변수는 카탈로그를 선택합니다. 위 Palimpsest 패키지 경로에는
신뢰된 nonempty URL이 필수이며 없으면 503입니다. 같은 호스트에 형제 서비스를 이미지로
설치해야 할 때만 `--profile waygate`, `--profile drover`, `--profile lumen`,
`--profile palimpsest`를 명시합니다. 이 API·worker는 각각 migration/bootstrap 완료 뒤
시작합니다. `--profile notion`은 선택적 Notion worker입니다.

- 각 sibling의 외부 운영 DB URL, Keystone service credentials, callback URL과 기존
  암호화 키를 준비합니다. Dev의 `dev` DB 계정이나 local snapshot을 복제하지 않습니다.
- Drover는 `DROVER_OS_SERVICE_PROJECT_ID`에 전용 service project UUID가 필요합니다.
- Lumen은 `LUMEN_CHECKPOINTER_POSTGRES_URL`, `LUMEN_ENCRYPTION_KEY`, 공유
  `LUMEN_MCP_SERVICE_TOKEN`과 catalog에 공개한 Afterglow endpoint인
  `LUMEN_MCP_CONTROL_PLANE_URL`을 설정합니다. `http://backend:8000`은 운영 값이 아닙니다.
- 선택 API catalog URL은 운영 DNS·인증서에 맞는 `https://<service-host>:8010/v1` 등
  HAProxy listener를 가리켜야 합니다. 이 Compose는 Keystone catalog를 자동 변경하지
  않습니다. Profile을 끈 서비스는 HAProxy 시작을 막지 않으며 해당 listener만 503입니다.

---

## kolla-ansible 배포

Afterglow와 Lumen은 Kolla 배포 호스트에서 표준 명령으로 함께 배포합니다.
최초 한 번 [Kolla 설치·설정 가이드](../deploy/kolla/README.md)에 따라 다음을 준비합니다.

- `/etc/kolla/multinode`의 `afterglow`, `lumen` 그룹과 기존 OpenStack inventory
- 실제 Kolla 가상 환경에 설치한 root 역할 패키지 네 개가 [`deploy/kolla/operator/uv.lock`](../deploy/kolla/operator/uv.lock)의 `drover`·`lumen`·`waygate`·`palimpsest-client` 릴리즈 tag/version과 일치할 것. 이미지 tag나 source checkout 버전만으로 설치된 역할 버전을 판단하지 않습니다.
- `/etc/kolla/config/afterglow/globals.yml` 및 `secrets.yml`, globals.d 연결
- 기존 MariaDB·Valkey, Lumen PostgreSQL 설정, 고정 이미지와 API 공개 경로
- 대상 호스트에서 암호 입력 없이 sudo를 사용할 수 있는 배포 SSH 계정
- stock `site.yml`에 서비스 플레이북을 연결하는 `deploy/kolla/install.sh`

Afterglow 역할은 저장소로 연결되며 Lumen 역할은 wheel이 소유합니다.
설치기는 역할을 임의 복제하거나 기존 비밀값을 샘플로 덮어쓰지 않습니다.

```bash
source /etc/kolla/.venv/bin/activate
cd /etc/kolla
kolla-ansible deploy -i multinode
```

이 명령은 활성화된 stock OpenStack 서비스도 실행합니다. Afterglow/Lumen만
설정 반영할 때는 같은 명령에 `--tags afterglow,lumen`을 추가합니다.
custom service와 HAProxy 플레이에 `become: true`가 선언되어 있어 별도
`--become`, `-p`, `-e @...` 인자가 필요하지 않습니다.

```bash
kolla-ansible prechecks -i multinode --tags afterglow,lumen
kolla-ansible reconfigure -i multinode --tags afterglow,lumen
```

### 볼륨 자동 백업의 다중 컨트롤러 실행

- 이 dispatcher를 포함한 동일 backend 소스를 모든 replica에 적용하고, 같은 Redis/Valkey primary·logical DB와 기존 `afterglow:auto_backup` namespace를 사용합니다. Controller마다 독립 Redis를 띄우면 분산 조정이 되지 않습니다. 기존 Redis/Sentinel 설정 경로를 유지하며 새 scheduler 설정·cron·worker service를 추가하지 않습니다.
- 각 API process의 hostname/PID/random incarnation은 자동 생성됩니다. 리더 하나만15초 정책 스캔을 수행하고, 새 작업·사라진 소유자의 작업을 살아 있는 process들의 배정 개수 기준으로 분배합니다. 정상 pending/active 소유권은 유지하며 동일 volume/slot 중복 제출은 별도의90초 renewable lease/durable journal로 방어합니다. Worker 수가 다르면 물리 controller별 가중치는 같지 않습니다.
-45초 member/leader lease와10초 heartbeat는 Redis server time을 사용합니다. SDK 실행과 스캔은 독립이고, 정상 종료는 SDK drain 뒤 회수합니다. Hard crash 인계는 membership/leader 만료와 다음 heartbeat/poll, 해당 볼륨의 남은90초 lease를 기다립니다. 진행 중인 Cinder data copy를 취소하거나 재시작하는 기능이 아닙니다.
- 정책·slot·active journal은 캐시가 아닌 정본입니다. Redis persistence/backup·failover 데이터 보존과 controller 시간 동기화를 유지합니다. Key 삭제/독립 Redis/journal 유실을 복구 작업으로 사용하지 않습니다. Redis 조정 불능에는 새 백업을 local로 실행하지 않으며, 이미 접수되었거나 결과가 불명확한 백업은 재발행하지 않습니다.
- 1.30.16 전환은 구형 process가 새 membership/assignment에 참여하지 않으므로 혼합 cohort의 rolling upgrade로 수행하지 않습니다. 기존 API·Notion worker 전체를 drain·중지한 뒤 같은 새 버전으로 함께 교체합니다. [SQL088/089 및 writer cohort 업그레이드 순서](#13016-업그레이드-sql-088089와-writer-cohort)를 따르세요. 2026-10-14 운영 전환은 이 순서로 완료했으며 [운영 receipt](testing.md#production-rollout-2026-10-14)에 기록합니다. Cold DB/Redis restore 검증은 live Cinder data copy/restore 증거가 아닙니다.

### 공유 background process의 다중 컨트롤러 분배

- 모든 Afterglow API·Notion worker replica는 같은 Redis/Valkey primary·logical DB와 같은 SQL DB를 사용해야 합니다. Namespace는 `afterglow:background:api`(API 유지보수 역할), `afterglow:auto_backup`, `afterglow:builds`, `afterglow:notion:work`, `afterglow:db_auto_backup`, `afterglow:worker_runtime:<mode>:<hash>`입니다. 새 설정 키·cron·worker service는 없습니다.
- API의 snapshot·block-consumer·host-health·Swift trash·MCP·Cloud Shell 정리 루프는 설정된 역할만 살아 있는 API process에 나뉘며, process가 합류·이탈하면 재분배합니다. Cinder/Trove 백업·Notion 대상·build/import·worker-runtime 대상은 모든 process가 참여하고 leader만 registry를 발행합니다. 분배는 process 단위이므로 controller별 worker 수가 다르면 물리 가중치는 같지 않습니다.
- 정상 종료(SIGTERM)는 진행 중 SDK·HTTP를 drain한 뒤 lease를 회수하고 membership에서 빠집니다. Hard crash 인계는45초 membership 만료와 다음 heartbeat/scan을 기다리며 해당 대상의 남은90초 execution lease를 우회하지 않습니다. Leader crash 동안에도 정상 실행자의 배정은 후계 leader 스캔까지 유지됩니다.
- Worker runtime 관리는 Docker는 Engine ID, Kubernetes는 `notion-worker` Deployment UID 단위로 조정합니다. Kubernetes는 기존 Deployment `get`과 `deployments/scale` `patch` 권한만 쓰며, scale PATCH에 UID·resourceVersion precondition을 포함하므로 재생성·동시 변경된 Deployment는 409로 거부되고 다음 주기에 다시 읽습니다.
- 이미 접수되었거나 결과가 불명확한 CREATE·백업은 재발행하지 않고 관측합니다. 이 보장은 공유 Redis persistence·failover 데이터 보존, 시간 동기화와 모든 replica의 동일 버전 전환을 전제로 합니다. 구형 process와 혼합 실행하지 말고 전체 API·worker를 함께 교체하세요. Drover·Lumen·Waygate·Palimpsest Hub는 각 저장소의 rollout 절차(구형 SQL worker·controller 중지 후 교체)를 따릅니다.

### 애플리케이션 이미지 채널 자동 해석 및 롤백

표준 Kolla 환경에서 Afterglow, Drover, Waygate, Lumen, Palimpsest의 application image는 `*_image_tag: "latest"`(또는 게시된 `stable`) 채널을 기본으로 따릅니다.
- `kolla-ansible`의 `prechecks`, `pull`, `deploy`, `reconfigure`, `upgrade` 실행마다 서비스별 첫 번째 대상 컨트롤러에서 Docker descriptor API로 manifest/index sha256 다이제스트를 해석합니다. `--limit`과 serial batch를 따르며 다음 명령은 채널을 새로 해석합니다.
- 태그를 생략한 image ref도 implicit `latest`로 해석합니다. 레지스트리 주소의 포트(`registry:5000/repository`)는 이미지 태그가 아니며, 컨트롤러별로 원래 bare ref를 pull하지 않습니다.
- 한 실행에 포함한 컨트롤러의 component enable flag는 동일해야 합니다. 차이가 있으면 첫 레지스트리 조회·역할 실행 전에 중단합니다. 서로 다른 배치는 동일한 flag를 가진 대상별로 `--limit`을 지정합니다.
- Published-image consumer는 첫 대상에 해당 서비스의 완료된 selection이 있어야 합니다. 앞 서비스가 남긴 readiness/ref는 재사용하지 않으며, 첫 대상이 비활성/source mode이고 이후 대상만 published mode인 경우 해당 소비자를 실행하기 전에 차단합니다. 이런 대상은 `--limit`으로 분리합니다.
- 해석된 불변 다이제스트는 해당 실행의 모든 serial batch에 동일하게 공유되므로, 롤링 배포 중 컨트롤러 간 버전 불일치가 발생하지 않습니다.
- 해석 단계는 레이어를 pull하지 않습니다. `pull`은 다운로드만 하며 컨테이너 교체는 `deploy`·`reconfigure`·`upgrade`에서 수행합니다. 레지스트리 조회 실패 시 이전 이미지로 넘어가지 않고 해당 rollout을 차단합니다.
- 특정 릴리즈 고정 또는 롤백이 필요한 경우 `globals.yml`에 명시적인 `*_image_ref`(예: `afterglow_backend_image_ref: "ghcr.io/openstack-afterglow/afterglow-api@sha256:<digest>"`)를 선언하면 레지스트리 동적 해석을 건너뛰고 해당 다이제스트가 유지됩니다.
- 기존 globals/globals.d/CLI extra-vars에 mutable 또는 bare `*_image_ref`가 있으면 제거하고 `*_image_tag`로 채널을 선택합니다. Native Kolla extra-vars는 `set_fact`보다 우선하므로 해석한 digest를 덮어쓰는 ref는 역할 실행 전에 거부합니다. 고정 ref는 그대로 유지합니다.
- 비활성 component와 source-build mode는 이 해석을 건너뜁니다. 이미지 채널은 별도로 고정·승격하는 root-role Git 패키지나 DB migration 승인, 미래 버전의 API/schema 호환성을 대신하지 않습니다.
- stock Kolla 2025.2 기본 서비스와 datastore(MariaDB, Valkey, PostgreSQL)의 버전/다이제스트 고정은 변경되지 않습니다.

Notion worker만 복구할 때는 backend/frontend를 검증한 현재 manifest digest에
명시적으로 고정합니다. 이 ref가 없으면 `--tags afterglow`도 활성 component의 최신
채널을 함께 선택합니다. `/etc/kolla/config/afterglow/globals.yml`의
`afterglow_worker_image_ref`만 `ghcr.io/openstack-afterglow/afterglow-worker@sha256:<digest>`로
바꾸고 backend/frontend의 현재 pin은 유지합니다. SSH host identity를 먼저 검증하고,
배포 계정으로 `/etc/kolla`에서 다음 표준 경로를 실행합니다.

```bash
source /etc/kolla/.venv/bin/activate
cd /etc/kolla
kolla-ansible prechecks -i multinode --tags afterglow
kolla-ansible reconfigure -i multinode --tags afterglow
```

완료 판정에는 각 controller의 running image digest와 restart count, worker startup/error
로그뿐 아니라 `Notion target ... 동기화 완료` 로그와 배포 전보다 증가한
`notion_targets.last_sync`가 필요합니다. Container가 `running`이어도 실제 timestamp가
전진하지 않으면 복구되지 않은 상태입니다. Rollback은 이전 worker digest를 복원하고 같은
service-scoped reconfigure를 반복합니다.


배포 후 각 대상에서 `afterglow_backend`, `afterglow_frontend`, `lumen_api`,
`lumen_worker` 상태와 공개 health 경로를 확인합니다. liveness HTTP 200과
실제 DB·Redis·PostgreSQL 연결 또는 인증된 채팅 동작은 구분해 검증합니다.
`--limit`을 사용해도 DB 마이그레이션과 PostgreSQL은 첫 서비스 컨트롤러에
위임될 수 있으므로 해당 호스트의 설정과 공유 데이터 저장소도 필요합니다.

Afterglow의 Kolla 최종 설정은 `valkey` inventory 전체를 Sentinel 주소로 사용하고
Kolla의 monitor 이름으로 현재 master를 찾습니다. `redis_url`은 사용자명·
`valkey_master_password`·전용 DB index(기본 5)를 계속 전달하지만 첫 controller
주소를 고정 master로 취급하지 않습니다. Valkey promotion 뒤에는 Sentinel이
보고하는 master와 인증된 `/api/v1/auth/refresh` 쓰기 경로를 함께 확인하세요.
단순 health 200이나 replica에서 성공하는 `GET`만으로는 세션 쓰기 가능 여부를
증명하지 못합니다.

서비스 카탈로그 검증은 [등록 튜토리얼](openstack-service-catalog.md)을 참고하세요.

---

## 전역 Cloud Shell 선택 배포

Cloud Shell은 Afterglow backend Pod/container 안에서 shell을 실행하지 않습니다. 운영자가 미리 만든 **전용 OpenStack 프로젝트**에서 사용자별·논리 프로젝트별 Cinder 홈과 세션별 Zun 컨테이너를 실행합니다. 일반 Afterglow 서비스 프로젝트, 사용자 tenant 프로젝트, Cloud Shell 프로젝트는 서로 달라야 합니다.

#### OpenStack 선행 조건

1. `afterglow-cloud-shell` 같은 전용 프로젝트를 하나 만들고 UUID를 고정합니다. 이름이 중복되면 활성화하지 않습니다.
2. Afterglow service user가 이 전용 프로젝트에서 Zun·Cinder·Neutron 자원을 관리할 역할을 받아야 합니다. 세션 정리는 owner 권한의 `stop=true` 삭제를 사용하므로 기본 policy에서는 `member`로 충분하며, Kolla Keystone setup은 기존대로 전용 프로젝트 `admin`을 부여합니다. 사용자 Keystone token으로 Zun/Cinder lifecycle을 관리하지 않습니다.
3. `network_id`는 선택 사항입니다. 비우면 전용 프로젝트의 DB default → 기존 자동 생성 정책 → 자동 생성 비활성 시 검증된 shared default-network 정책을 따릅니다. 선택 네트워크는 subnet과 external network/router gateway 연결이 필요하며, 명시적 override는 전용 프로젝트 소유여야 합니다. `security_group`은 전용 프로젝트의 `default`를 기본으로 사용하고 기존 규칙을 유지합니다. Egress-only가 필요하면 별도 그룹을 명시합니다. Kolla 역할은 project/network/router/group을 만들거나 삭제하지 않으며, backend는 세션 승인 시 기존 default-network 정책에 따라 network/router를 자동 준비할 수 있습니다.
4. Zun, Kuryr, etcd, Docker/containerd Zun integration, Cinder-backed Zun volume mount와 하나 이상의 `zun-compute`를 준비합니다. Backend에서 Keystone/Cinder/Zun API와 Zun exec WebSocket endpoint에 접근할 수 있어야 합니다. Zun API는 container microversion 1.36 이상을 지원해야 하고, zun-compute는 Cinder volume을 attach해 처음 mount할 때 ext4로 format할 수 있어야 합니다.
5. `cloud-shell` 이미지를 `linux/amd64`와 `linux/arm64` manifest로 게시하고 운영 설정에는 반드시 `@sha256:<manifest-digest>`를 사용합니다. `latest`나 bare tag는 사용하지 않습니다.
6. Cinder volume count/gigabytes와 Zun container/CPU/RAM quota는 **전용 프로젝트**에 적용합니다. 사용자 tenant quota를 Cloud Shell 용량으로 사용하거나 늘리지 않습니다. 최대 동시 세션은 전역 사용자당 1개지만 영구 홈은 사용자×논리 프로젝트마다 하나이므로 예상 project 수를 volume quota에 반영합니다.

기본 runtime 설정 예시:

```toml
[services]
zun = true
cloud_shell = true

[cloud_shell]
service_project_id = "<dedicated-project-uuid>"
image = "ghcr.io/openstack-afterglow/afterglow-cloud-shell@sha256:<64-hex-digest>"
network_id = "" # 전용 프로젝트 default 네트워크
security_group = "default"
auth_url = "https://keystone.example.com:5000/v3"
interface = "public"
volume_type = "ceph"
home_size_gib = 5
cpu = 1.0
memory_mib = 1024
idle_timeout_seconds = 1200
max_session_seconds = 3600
ticket_ttl_seconds = 60
reconcile_interval_seconds = 60
zun_websocket_origin = "wss://zun.example.com"
```

`auth_url`과 `zun_websocket_origin`은 backend가 신뢰하는 고정 HTTPS/WSS endpoint입니다. 브라우저에 공개되는 값이 아니며 redirect나 untrusted HTTP fallback을 허용하지 않습니다. `SECRET_KEY`는 관리 volume/container metadata HMAC에도 쓰이므로 홈을 유지하는 동안 회전하면 기존 리소스를 자동 채택하지 않습니다.

#### Kolla

`/etc/kolla/config/afterglow/globals.yml`에 `afterglow_service_zun_enabled: true`, `afterglow_service_cloud_shell_enabled: true`와 `afterglow_cloud_shell_*` 값을 설정합니다. Image는 digest-pinned manifest이며 project ID, public auth URL, Zun WSS origin을 지정합니다. Network ID는 기본 선택 시 비워 두고 security group의 기본값은 `default`입니다. Stock Kolla 변수 `enable_zun`, `enable_kuryr`, `enable_etcd`, `docker_configure_for_zun`, `containerd_configure_for_zun`, `zun_configure_for_cinder_ceph`도 모두 활성화합니다.

```bash
cd /etc/kolla
kolla-ansible prechecks -i multinode --tags afterglow
kolla-ansible deploy -i multinode --tags afterglow
```

Precheck는 전용 project 분리, network/security-group 소유권, ingress 0건, project-scoped Zun/Cinder list, 선택 volume type, 모든 `zun-compute`의 image manifest 접근을 fail-closed 확인합니다. Keystone 단계는 미리 만든 project를 정확히 하나만 찾고 Afterglow service user의 `admin` role assignment만 보장합니다.

#### Kubernetes와 Helm

`generate_k8s.py`는 같은 `[services]`와 `[cloud_shell]` 값을 ConfigMap의 `afterglow.conf`에 렌더합니다. Helm은 `services.zun`, `services.cloudShell`, `cloudShell.*` values를 같은 계약으로 렌더합니다. Secret 값은 추가되지 않습니다. Backend Pod egress policy와 cluster DNS가 Keystone/Cinder/Zun API, Zun WSS, registry에 도달하도록 별도로 허용하고, browser ingress는 기존 `/api/` WebSocket upgrade를 보존합니다.

#### 확인, live smoke, rollback

```bash
# 정적/모의 lifecycle과 배포 계약
npm run test:cloud-shell
npm run test:cloud-shell:image
npm run test:kolla:contract

# 실제 승인 → OpenStack CLI → 종료 → 홈 재사용 → 초기화 (resource mutation)
# username은 tests/integration/credentials.toml [user]의 disposable identity와 정확히 일치해야 한다.
CLOUD_SHELL_LIVE_USER_IDENTITY=cloud-shell-smoke \
CLOUD_SHELL_LIVE_CONFIRM=reset-disposable-home \
npm run test:live:cloud-shell
```

Live target은 일반 사용자 integration credential, Redis, 활성화된 Cloud Shell 설정, 실제 Zun/Cinder/Neutron, 게시된 이미지를 요구합니다. `CLOUD_SHELL_LIVE_USER_IDENTITY`는 선택된 integration username과 정확히 일치해야 하고 `CLOUD_SHELL_LIVE_CONFIRM=reset-disposable-home`을 별도로 지정해야 합니다. Test는 첫 조회에서 active session 또는 기존 home이 하나라도 있으면 mutation 전에 실패하므로 운영 사용자 workspace를 채택하거나 삭제하지 않습니다. 오직 absent/inactive baseline에서 자신이 만든 홈만 마지막에 초기화합니다. 별도로 shell에서 catalog/DNS와 허용한 outbound 목적지를 확인하되 secret/token을 출력하지 않습니다. 기본 최대 세션은 1시간이므로 expiry·재조정은 unit contract와 운영 staging의 짧은 허용 설정에서 확인하고 production 값을 검증 목적으로 낮추지 않습니다.

Rollback은 먼저 `cloud_shell=false`로 재배포해 새 승인과 router mount를 중지합니다. 최대 세션 시간과 reconciler 정리가 지난 뒤 전용 프로젝트의 managed Zun container가 0인지 확인합니다. 사용자 홈 Cinder volume은 자동 삭제하지 않습니다. 보존/백업/삭제 정책을 정한 뒤 managed metadata가 일치하는 volume만 처리하고, 마지막에 service-user role·network·project를 운영 절차로 제거합니다. 설정을 되돌리는 과정에서 tenant volume이나 이름만 같은 resource를 삭제하지 않습니다.

---

## Kubernetes 배포

프로덕션 환경 배포. Kustomize 기반 base + overlay 구조로 dev/prod 환경을 분리합니다.

### 사전 요구사항

| 항목 | 최소 버전 |
|---|---|
| kubectl | 1.28+ |
| k3s 또는 Kubernetes | 1.28+ |
| (선택) ArgoCD | 2.8+ |

### 디렉토리 구조

```
deploy/k8s-template/
├── configmap.yaml      # afterglow.conf ConfigMap
├── secret.yaml         # afterglow-secrets 예시
├── ingress.yaml
├── cert-manager.yaml
├── base/              # 공통 Deployment/Service 리소스
│   ├── namespace.yaml
│   ├── backend/
│   ├── frontend/
│   ├── redis/
│   └── worker/
└── overlays/
    ├── dev/           # 개발 오버레이
    └── prod/          # 프로덕션 오버레이
```

### 1. 프로덕션 네임스페이스 및 시크릿 생성

아래 정적 `configmap.yaml`/`secret.yaml`은 `metadata.namespace: afterglow`를 포함하므로 프로덕션 네임스페이스 전용입니다. `overlays/dev`는 `namespace: afterglow-dev`를 사용하므로 이 파일을 그대로 적용해도 dev Pod가 `afterglow-config`/`afterglow-secrets`를 볼 수 없습니다. dev 오버레이를 단독으로 쓰려면 동일한 ConfigMap/Secret을 `afterglow-dev` 네임스페이스용으로 별도 생성하거나 ArgoCD/ExternalSecret에서 관리해야 합니다.

```bash
kubectl create namespace afterglow
# Builder SSH를 쓰지 않으면 빈 파일로 키 존재만 보장합니다. 실제 사용 시 private key 경로를 지정하세요.
touch builder.key

kubectl create secret generic afterglow-secrets \
  --namespace=afterglow \
  --from-literal=OS_PASSWORD=<openstack-password> \
  --from-literal=SECRET_KEY=$(openssl rand -hex 32) \
  --from-literal=GITLAB_OIDC_CLIENT_SECRET='' \
  --from-literal=K3S_KUBECONFIG_ENCRYPTION_KEY=$(openssl rand -hex 32) \
  --from-literal=DATABASE_URL='mysql+asyncmy://afterglow:<db-password>@mariadb/afterglow' \
  --from-literal=PROMETHEUS_PASSWORD='' \
  --from-file=BUILDER_SSH_PRIVATE_KEY=builder.key
```

### 2. 프로덕션 ConfigMap 및 Kustomize 배포

```bash
# afterglow.conf ConfigMap은 prod overlay에 포함되지 않으므로 먼저 적용
kubectl apply -f deploy/k8s-template/configmap.yaml

# 프로덕션 환경
kubectl apply -k deploy/k8s-template/overlays/prod
```

### 3. 배포 확인

```bash
kubectl get all -n afterglow
kubectl get ingress -n afterglow

# 로그 확인
kubectl logs -f deployment/backend -n afterglow
kubectl logs -f deployment/frontend -n afterglow
```

### ConfigMap 주요 설정

`deploy/k8s-template/configmap.yaml`은 `afterglow.conf`를 인라인으로 제공합니다. `generate_k8s.py`로 생성하는 경우 ConfigMap에는 브라우저/프론트엔드용 `APP_REDIS_URL`, `APP_ORIGIN`, `PUBLIC_S3_BASE`, `APP_GRAFANA_BASE`와 런타임 설정 `afterglow.conf`가 들어갑니다.

```yaml
data:
  APP_ORIGIN: "https://afterglow.example.com"
  APP_REDIS_URL: "redis://redis:6379/0"
  PUBLIC_S3_BASE: "https://s3.example.com"
  APP_GRAFANA_BASE: "https://grafana.example.com"
  afterglow.conf: |
    [openstack]
    auth_url = "https://keystone.example.com:5000/v3"
    # password는 afterglow-secrets/OS_PASSWORD 환경변수로 주입
```

비밀 값은 ConfigMap에 넣지 않습니다. `OS_PASSWORD`, `SECRET_KEY`, `GITLAB_OIDC_CLIENT_SECRET`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL`, `PROMETHEUS_PASSWORD`, `BUILDER_SSH_PRIVATE_KEY`는 `afterglow-secrets`에서 환경변수 또는 Secret volume으로 주입됩니다.

`generate_k8s.py --config ./afterglow.conf --output-dir deploy/k8s-template`는 `configmap.yaml`, `secret.yaml`, `grafana-deployment.yaml`, `ingress.yaml`을 생성합니다. `[app].secret_key`가 빈 값, `change-me-in-production`, 32자 미만이면 `secret.yaml` 생성을 실패시켜 Kubernetes production guard와 맞춥니다.

공개 개인 MCP에는 `[services] mcp = true`와 `[mcp] public_url = "https://cloud.dmslab.re.kr/mcp"`를 설정합니다. Web/API origin과 resource를 함께 읽어 생성한 `ingress.yaml`을 static base/overlay 적용 **뒤 마지막으로** 적용합니다. MCP를 켜면 main web/API Ingress와 priority1000의 별도 MCP Ingress 두 문서가 포함되며, Exact `/mcp`·Prefix `/mcp/`·Prefix `/.well-known/`만 backend로 갑니다. `/mcpevil`·`/mcp-other`·frontend consent는 기존 frontend에 남습니다. Explicit root resource는 dedicated host에만 허용하고 shared web/API host root는 생성 전에 실패합니다. Main Ingress의 TLS hosts에는 MCP host가 포함되며 Secret과 credential은 출력물을 커밋하지 않습니다. Helm의 `services.mcp`·`mcp.publicUrl`도 같은 경계입니다.

### Ingress 도메인 설정

`deploy/k8s-template/ingress.yaml`:

```yaml
spec:
  rules:
    - host: afterglow.example.com
      http:
        paths:
          - path: /.well-known
            pathType: Prefix
            backend:
              service:
                name: backend
                port:
                  number: 8000
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: backend
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 3080
```

> **주의**: 프론트엔드 `PUBLIC_API_BASE` 환경변수는 브라우저에서 직접 접근 가능한 외부 URL로 설정해야 합니다. 클러스터 내부 주소(`http://backend:8000`)로 설정하면 브라우저에서 접근할 수 없습니다.

```yaml
# frontend Deployment 환경변수
- name: PUBLIC_API_BASE
  value: "https://afterglow.example.com"
- name: ORIGIN
  value: "https://afterglow.example.com"
```

### 모니터링 스택

```bash
# 전체 모니터링 배포
kubectl apply -k deploy/k8s-template/monitoring/

# 포트 포워딩으로 로컬 접근
kubectl port-forward svc/grafana 3001:3000 -n afterglow
kubectl port-forward svc/prometheus 9090:9090 -n afterglow
```

### 런타임 설정·시크릿 계약

Kubernetes의 Python 서비스는 Docker Compose 개발 모드와 다르게 항상 production guard를 사용합니다.

| Deployment | 설정 파일 | Secret 참조 |
|---|---|---|
| `backend` | `/app/afterglow.conf` | `OS_PASSWORD`, `SECRET_KEY`, `GITLAB_OIDC_CLIENT_SECRET`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL`, `PROMETHEUS_PASSWORD`, `BUILDER_SSH_PRIVATE_KEY` |
| `drover` (`worker`) | `/app/afterglow.conf` | `OS_PASSWORD`, `SECRET_KEY`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL` |
| `notion-worker` | `/app/afterglow.conf` | `OS_PASSWORD`, `SECRET_KEY`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL` |

세 서비스 모두 `AFTERGLOW_ENV=production`으로 실행되며, `AFTERGLOW_ALLOW_INSECURE=1`은 Kubernetes manifest에 넣으면 안 됩니다. Secret을 직접 작성하지 않고 `generate_k8s.py`를 사용할 때도 `[app].secret_key`가 비어 있거나 `change-me-in-production`이거나 32자 미만이면 `secret.yaml` 생성을 중단합니다.

### Helm 배포

Helm chart도 같은 계약을 사용합니다. `backend`, `drover`, `notion-worker`는 `afterglow-config/afterglow.conf`를 `/app/afterglow.conf`로 마운트하고 `afterglow-secrets/SECRET_KEY`를 읽습니다.

Secret 소유 방식은 두 가지입니다.

1. **ExternalSecret/ArgoCD가 `afterglow-secrets`를 소유**: `values.yaml`의 `secrets.osPassword`를 비워 두면 Helm은 Secret을 렌더하지 않고 Deployment만 기존 Secret을 참조합니다.
2. **Helm이 Secret 직접 렌더**: `secrets.osPassword`를 설정하면 Helm이 `afterglow-secrets`를 만들며, 이때 `secrets.secretKey`, `secrets.databaseUrl`, `secrets.k3sKubeconfigEncryptionKey`도 필수입니다. GitLab/Prometheus/Builder/Grafana 등 선택 Secret 키는 값이 비어 있어도 Secret에 포함됩니다. 필수 값이 하나라도 빠지면 template 단계에서 실패합니다.

```bash
helm template afterglow helm/afterglow --namespace afterglow \
  --set secrets.osPassword='<openstack-password>' \
  --set secrets.secretKey="$(openssl rand -hex 32)" \
  --set secrets.k3sKubeconfigEncryptionKey="$(openssl rand -hex 32)" \
  --set secrets.databaseUrl='mysql+asyncmy://afterglow:<db-password>@mariadb/afterglow'
```

---

## ArgoCD GitOps 배포

`dev` 브랜치의 변경사항을 자동으로 클러스터에 동기화합니다.

### 1. ArgoCD 설치 (없는 경우)

```bash
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 2. Application 등록

```bash
kubectl apply -f argocd/00-namespace.yaml
kubectl apply -f argocd/01-appproject.yaml
kubectl apply -f argocd/03-ingress.yaml
kubectl apply -f argocd/04-server-config.yaml

# Helm Application 생성 — 생성물에는 Secret 값이 들어가므로 커밋하지 않음
backend/.venv/bin/python argocd/generate_helm_application.py dev
KUBECONFIG=/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig \
  kubectl apply -f deploy/k8s/argocd-application-dev.yaml

backend/.venv/bin/python argocd/generate_helm_application.py prod
KUBECONFIG=/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig \
  kubectl apply -f deploy/k8s/argocd-application-prod.yaml
```

`generate_helm_application.py`가 dev/prod Application의 유일한 생성 경로입니다.
Application은 모두 `helm/afterglow`를 source로 사용하며, Helm valuesObject,
`selfHeal`, Image Updater 설정, `afterglow-config`/`afterglow-secrets`의
`ignoreDifferences`가 함께 생성됩니다. 삭제된 `argocd/02-application.*.yaml`
Kustomize Application은 다시 적용하지 않습니다.

### 3. 동기화 확인

```bash
argocd app list
argocd app sync afterglow-dev
argocd app sync afterglow-prod
argocd app get afterglow-dev
```

### 3. 동기화 확인

```bash
argocd app list
argocd app sync afterglow-dev
argocd app get afterglow-dev
```

---

## TLS / HTTPS 설정

cert-manager를 사용하여 Let's Encrypt 인증서를 자동으로 발급합니다.

```bash
# cert-manager 설치
kubectl apply -f deploy/k8s-template/cert-manager.yaml
```

ClusterIssuer 생성:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

Ingress에 TLS 추가:

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - afterglow.example.com
      secretName: afterglow-tls
```

---

## 업그레이드

### Docker Compose

```bash
# Development: update reviewed source, then rebuild the dev manifest.
npm run services:up

# Production: select the reviewed published tag/digest and synchronize images only.
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml pull
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml up -d --no-build --wait
```

### 데이터베이스 스키마 마이그레이션

`auto_create_tables`는 기존 테이블에 컬럼을 추가하지 않습니다. 이미지가 새 ORM 컬럼을 참조하는 릴리스는 **롤아웃 전에** 해당 SQL 마이그레이션을 운영 데이터베이스에 적용해야 합니다. 적용 대상과 순서는 `backend/migrations/manifest.txt`의 논리 ID를 기준으로 판단하며, 숫자 접두사만으로 판단하지 않습니다.

로컬 fallback `afterglow-mariadb`를 사용하는 격리 DB에 한정한 2026-08-02 채팅 메시지
시간대 컬럼 마이그레이션 예시입니다. 외부 `AFTERGLOW_DATABASE_URL`을 선택한 경우 이
명령은 선택 DB가 아니라 local MariaDB를 변경하므로 외부 대상 절차로 사용하지 않습니다.

```bash
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml exec -T afterglow-mariadb sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' \
  < backend/migrations/070_chat_message_local_timestamps.sql
```

Kubernetes 또는 외부 MariaDB에서는 운영 DB 접근 권한을 가진 관리 경로에서 같은 SQL 파일을 실행합니다. 비밀번호를 명령행이나 Git에 기록하지 않습니다. 적용 후 다음 두 컬럼을 확인한 뒤 backend를 롤아웃합니다.

```sql
SHOW COLUMNS FROM chat_messages LIKE 'created_at_local';
SHOW COLUMNS FROM chat_messages LIKE 'created_timezone';
```

Kolla Afterglow `deploy`·`reconfigure`는 생성된 config를 사용해, `upgrade`는 pull한
image와 기존 생성 config를 사용해 backend를 시작하기 **전에** 일회성 DB bootstrap을
실행합니다. 운영 API에서 `auto_create_tables=false`여도 신규 ORM table은 이 단계에서
생성됩니다. 기존 테이블에 새 컬럼을 추가하는 변경에는 위 수동 SQL 적용이 여전히
필수이며, bootstrap 성공이나 `/api/v1/health` 200만으로 인증된 업무 경로를 검증했다고
보지 않습니다.

#### 1.30.16 업그레이드: SQL 088/089와 writer cohort

1.30.16은 Palimpsest block source/consumer의 기존 테이블 컬럼을 읽고 쓰므로 **새 API·Notion worker를 시작하기 전에 SQL 088 다음 089를 명시 적용**해야 합니다. 2026-10-14 전환 전 read-only baseline은 운영 081–087 적용·088/089 미적용이었으나, 이후 cold backup/격리 restore와 writer 전체 중지 뒤 **088→089 적용을 완료**했습니다(필수 컬럼 0→5, row count 불변, bootstrap 뒤 90 tables). [운영 receipt](testing.md#production-rollout-2026-10-14)를 참고하세요. 다른 적용 대상은 현재 schema와 `backend/migrations/manifest.txt`를 다시 대조하여 정합니다. Kolla bootstrap의 `create_tables()`나 `auto_create_tables`는 이 기존 컬럼을 추가하지 않습니다.

1. [운영 데이터와 양방향 호환성 평가](#운영-데이터와-양방향-호환성-평가)의 승인·snapshot·원래 key/Redis/CAS 보존·복원 시험·rollback 제한을 충족합니다. **보호된 backup과 격리 restore 확인이 SQL 적용보다 먼저**입니다. 기존 SQL084–087 cutover의 protected backup/restore 후 필요한 statement만 적용한 패턴을 따르되, 당시의 idempotence/호환성 결과를 088/089로 확대하지 않습니다([1.30.14 receipt](testing.md#13014-운영-기준-통합-검증-2026-10-13)). 없는 ledger를 만들거나 historical migration 전체를 replay하지 않습니다.
2. 위 `SHOW COLUMNS` 패턴으로 적용 **전** 컬럼을 확인합니다. **089는 `IF NOT EXISTS`가 없어 idempotent가 아닙니다**. 모두 없을 때만 전체 089 SQL을 실행하고, 모두 있으면 정의/type/default/nullability가 파일과 일치하는지 확인합니다. 일부만 있거나 정의가 다르면 blind 재실행하지 말고 중단하여 승인된 schema 복구 절차를 정합니다.

   ```sql
   SHOW COLUMNS FROM layer_artifacts LIKE 'block_source';
   SHOW COLUMNS FROM layer_consumes LIKE 'transport';
   SHOW COLUMNS FROM layer_consumes LIKE 'run_id';
   SHOW COLUMNS FROM layer_consumes LIKE 'resources';
   SHOW COLUMNS FROM layer_consumes LIKE 'cleanup_state';
   ```

3. 운영 DB 접근 권한을 가진 기존 관리 경로에서 **`backend/migrations/088_layer_block_sources.sql` → `backend/migrations/089_layer_block_consumes.sql`** 순서로 적용합니다. 088은 nullable JSON `layer_artifacts.block_source`를 `IF NOT EXISTS`로 추가합니다. 089는 `layer_consumes.transport`를 `VARCHAR(16) NOT NULL DEFAULT 'nfs'`로, `run_id`·`resources`·`cleanup_state`를 nullable 컬럼으로 추가하여 기존 NFS consumer를 보존합니다. 위 local fallback Compose SQL 예시는 외부/운영 DB 적용 명령이 아닙니다. 비밀번호를 명령행이나 Git에 기록하지 않습니다. 적용 후 같은 컬럼 검사로 정의를 확인하고 기존 row/state 보존을 대조합니다. Additive nullable/defaulted DDL을 구형 writer가 허용하는 것과 새 durable state의 downgrade 안전성은 별개입니다.
4. SQL 적용·확인 후에만 1.30.16 writer를 시작합니다. Redis 기반 분산 background ownership 전환은 **구형 API·Notion worker 전체의 SDK/HTTP drain·중지 후 모든 replica를 같은 새 버전으로 함께 교체**하며 구형/신형 cohort를 혼합하지 않습니다. Controller별 reconfigure 중에도 구형 writer를 재시작하지 않습니다. Lumen **0.6.8**, Drover **0.4.15**, Waygate **0.3.4**, Palimpsest **0.3.5**의 publication/operator promotion과 각 sibling rollout 절차도 충족해야 합니다. Health/bootstrap exit 0만으로 완료 처리하지 말고 authenticated 업무/UI와 기존 데이터·키·비대상 runtime 보존을 확인합니다.

위 내용은 재사용할 업그레이드 절차입니다. 2026-10-14의 1.30.16 exact-SHA CI·Helm/tag image 발행·operator promotion·production cutover 및 범위가 제한된 authenticated GET-only UI/Bklit 검증은 완료했으며 [운영 receipt](testing.md#production-rollout-2026-10-14)에 결과·미검증 범위·잔여 관측을 기록합니다. SQL088/089와 새 writer가 live인 현재 **image-only rollback은 허용되지 않으며**, cold DB/Redis backup·이전 image·`preafterglow` config snapshot을 함께 사용하는 복구 경계를 따릅니다.


### 선택적 OpenStack notification 수집

관리자 이벤트 뷰어의 Afterglow 요청 기록은 기본 동작이지만, **Afterglow 이외의 CLI/Horizon/OpenStack 내부 이벤트는 자동으로 나타나지 않습니다.** 각 Nova/Cinder/Neutron/Keystone 등의 `oslo_messaging_notifications` driver와 `transport_url`·topic/routing key를 실제 운영 설정에서 확인하고, Afterglow가 접근하는 전용 최소 권한 RabbitMQ 계정과 durable queue를 준비하세요. 서비스별 exchange·notification topic은 설치마다 다릅니다. `afterglow.conf.example`의 `[openstack_notifications]`와 `bindings`는 예시이며 해당 서비스가 발행하지 않는 이벤트는 소비할 수 없습니다.

운영 DB에 `083_activity_event_metadata.sql` migration을 **backend 롤아웃 전에** 적용하고, AMQP URL은 공개 ConfigMap 대신 비밀 환경변수 `OPENSTACK_NOTIFICATIONS_AMQP_URL` 또는 보호된 private config로 주입합니다. TLS `amqps://`와 broker 인증서를 사용하고 알림 exchange의 read/bind 및 Afterglow queue 관리만 허용하세요. 처음에는 `enabled=false`로 배포하여 기존 활동 이력과 관리자 권한을 확인한 뒤 수집을 켜고, Nova `instance.create.error`와 정상 종료 이벤트 각각이 별도 source `openstack` 행으로 나타나는지 검증합니다. 서버가 여러 replica여도 같은 durable queue 이름을 사용해 메시지를 경쟁 소비하고 `external_id`의 DB UNIQUE 제약으로 중복을 차단합니다. DB 장애 시 ack하지 않고 재전달하지만, 알림 발행자의 persistent delivery와 broker 내구성 설정 없이는 재시작 후 전달을 보장할 수 없습니다. broker/발행자 장애나 알림 자체 미발행도 누락 가능성이 남습니다. 알림은 원본 응답 본문/credential을 저장하지 않으며 actor가 없는 이벤트에 사용자를 추정하지 않습니다. API 사용법과 조사 범위는 [관리자 이벤트](api/events.md)를 따릅니다.

### Kubernetes

```bash
# 이미지 또는 ConfigMap/Secret 업데이트 후 Python 서비스 롤링 재시작
kubectl rollout restart deployment/backend -n afterglow
kubectl rollout restart deployment/frontend -n afterglow
kubectl rollout restart deployment/drover -n afterglow
kubectl rollout restart deployment/notion-worker -n afterglow
kubectl rollout status deployment/backend -n afterglow
```

ArgoCD를 사용하는 경우 `dev` 브랜치 푸시 시 자동 동기화됩니다.

---

## 문제 해결

### 백엔드가 OpenStack에 연결되지 않음

```bash
# 로그 확인
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml logs backend
kubectl logs -f deployment/backend -n afterglow

# Keystone 연결 테스트
curl -s https://keystone.example.com:5000/v3 | python3 -m json.tool
```

### Redis 연결 오류

```bash
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml exec redis redis-cli ping
# 또는
kubectl exec -n afterglow deployment/backend -- redis-cli -u redis://redis:6379 ping
```

### 프론트엔드 API 연결 오류

1. `PUBLIC_API_BASE`가 브라우저에서 접근 가능한 외부 URL인지 확인
2. 도메인 변경 후 프론트엔드 재시작:
   ```bash
   kubectl rollout restart deployment/frontend -n afterglow
   ```

### Pod가 Pending 상태

```bash
kubectl describe pod -l app=backend -n afterglow
# PVC 바인딩 또는 리소스 부족 여부 확인
kubectl get pvc -n afterglow
kubectl describe nodes
```

---

## 보안 체크리스트 (배포 전)

자세한 보안 모델은 [docs/security.md](security.md) 참고.

### 필수 환경 변수

| 변수 | 운영 시 |
|---|---|
| `AFTERGLOW_ENV=production` | 필수 |
| `AFTERGLOW_ALLOW_INSECURE` | **설정 금지** (production 과 결합 시 백엔드가 ValueError 로 부팅 실패) |
| `SECRET_KEY` | 32 자 이상 random hex (`change-me-in-production` default 금지) |
| `K3S_KUBECONFIG_ENCRYPTION_KEY` | 64 hex chars (`openssl rand -hex 32`) — kubeconfig/node_token/manager_password/notion 의 마스터키. HKDF 로 도메인별 sub-key 자동 파생 |
| `NOTION_CONFIG_ENCRYPTION_KEY` | 선택. 미설정 시 K3S_KUBECONFIG_ENCRYPTION_KEY 와 동일 마스터로 fallback (HKDF 로 분리됨) |
| `TRUSTED_PROXIES` | 리버스 프록시의 CIDR 리스트. 기본 `127.0.0.1/32, ::1/128` — 실제 LB IP 추가 필요 |
| `CORS_ORIGIN_LIST` | 신뢰할 수 있는 origin 만. wildcard 금지 |

### 부팅 가드 검증

```bash
# 의도적으로 잘못된 조합으로 부팅 시도 → ValueError 가 떠야 함
AFTERGLOW_ENV=production AFTERGLOW_ALLOW_INSECURE=1 \
  uv run uvicorn app.main:app --port 8000
# 예상: "AFTERGLOW_ALLOW_INSECURE=1 must NOT be set when AFTERGLOW_ENV=production"
```

### 정기 점검

- **audit_log retention** — `kubeconfig_download` row 가 적정 기간 (예: 90일) 보관되는지
- **Health Bearer 토큰** — `redis-cli SCAN MATCH afterglow:health:token:*` 의 TTL 이 7일 이내인지
- **K3s ciphertext 버전** — `encrypted_kubeconfig NOT LIKE 'v3:%'` 행의 갯수 (1.15.0 전에 모두 v3 로 마이그레이션 권장)

### 1.13.x → 1.14.0 업그레이드

- **Backward-compatible**, 마이그레이션 작업 불필요
- 다른 프로젝트의 ID 로 자원에 접근하던 자동화 스크립트는 404 를 받게 됨 — admin 토큰 또는 application credential 로 전환 필요
- 첫 v2/legacy ciphertext 복호화 시 워커당 1회 deprecation warning 로그 확인 (스팸 X)

### 1.14.0 → 1.15.0 (예정) 전 필수 작업

- 별도 PR 로 제공될 마이그레이션 스크립트로 모든 v1/v2 ciphertext 를 v3 로 batch re-encrypt
- 미실행 시 v1/v2 ciphertext 가 영구 복호화 불가
