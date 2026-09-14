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

## Docker Compose 배포

Compose 파일은 합쳐 쓰는 환경 overlay가 아니라 **각각 독립 실행하는 세 가지 계약**입니다. 항상 명시적인 `-f`로 선택합니다.

| 파일 | 실행 목적 | 통신·데이터 경계 |
|---|---|---|
| `docker-compose.yml` | published Afterglow frontend/backend 두 개만 실행 | Redis·DB·OpenStack·형제 서비스는 외부 설정 |
| `docker-compose.dev.yml` | 현재 Afterglow·Lumen·Waygate·Drover·Palimpsest 소스를 빌드해 로컬 실행 | Compose service DNS, private local DB/cache/checkpointer |
| `docker-compose.prod.yml` | GHCR 이미지를 pull·동기화해 운영 실행 | HAProxy TLS/LB, 인증된 Keystone catalog endpoint |

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
- Python **3.11 이상** (표준 `tomllib`)과 이 checkout의 `afterglow.conf`, `.env`. Python은 `backend/.venv/bin/python`을 우선 사용하고, 없으면 `python3`를 사용합니다.
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
  `../palimpsest`가 필요합니다. 마지막 checkout에서는 `hub/Dockerfile`도 필요합니다.
- 실제 provider key를 추가하려면 **로컬** Lumen 관리 UI/API에 등록합니다. 운영 provider DB나
  암호화된 key를 복제하지 않습니다. 키가 없어도 모델 metadata와 context-preview는 검증할 수
  있지만, 실제 provider completion 검증은 별도 자격 증명이 필요합니다.

`docker-compose.dev.yml`은 각 datastore URL을 interpolation 없는 literal로
고정합니다. 따라서 `.env`뿐 아니라 shell에 남은 production DB URL도 local migration을
외부로 보낼 수 없습니다. Backend는 `afterglow-mariadb`, 추출 서비스는 `service-mariadb`의
개별 schema, Lumen checkpointer는 `lumen-postgres`, cache는 이 project의 Redis만 사용합니다.
MariaDB/PostgreSQL은 host port를 공개하지 않습니다. 시작 전 resolved Compose의 DB/cache,
volume/network, mount와 loopback port 경계를 검사하며, 무시된 `docker-compose.override.yml`을
읽지 않습니다. API health와 migration 완료까지 기다린 뒤 `services:up`이 성공하지만,
이것만으로 대시보드·OpenStack 통신까지 검증됐다는 뜻은 아닙니다.

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

# 기존 선택적 개발 모니터링 profile
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml --profile monitoring up -d
```

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
선택합니다. 명시적 빈 환경 변수는 해당 서비스만 카탈로그로 돌립니다. 기존 private snapshot은
원본 설정 변경으로 덮어쓰지 않습니다. `services:config`는 선택값을 private `compose.env`에
보존하고 `services:up`은 새 환경을 반영합니다. 기본·운영 실행은 override가 없으면 카탈로그를
사용합니다. [주소 예시와 우선순위](openstack-service-catalog.md#로컬-direct-서비스-엔드포인트-오버라이드-direct-service-endpoint-overrides)를 따르세요.

`LUMEN_MCP_CONTROL_PLANE_URL`은 Lumen이 Afterglow를 호출할 주소입니다. 브라우저의
`PUBLIC_API_BASE` 및 원격 VM의 Waygate/Drover callback URL은 별도이며, 원격 VM callback에는
개발 컨테이너 DNS나 `localhost`가 아닌 VM에서 도달 가능한 주소가 필요합니다.

### 4. 운영 이미지와 TLS HAProxy

Prod는 `afterglow-production` project에서 frontend/backend, private persistent Redis,
HAProxy **3.2**를 기본 실행합니다. 앱 컨테이너는 host port를 열지 않고 HAProxy만
80/443 및 선택 서비스용 TLS listener 8010/8011/8012/8020을 공개합니다. `/api/`,
`/v1/`, `/.well-known/`, API docs는 backend, 나머지는 frontend로 전달합니다.
SSE와 WebSocket 연결은 유지하며, 외부 `X-Forwarded-*`는 edge에서 덮어씁니다.

운영자가 별도 mode 0600 env 파일에 `SECRET_KEY`, `OS_PASSWORD`, `DATABASE_URL`,
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

기본 운영은 이미 설치된 형제 서비스의 **Keystone internal catalog endpoint**로 통신합니다.
운영 backend/Notion worker는 unset endpoint를 덮어쓰지 않으므로 TOML 또는 카탈로그를
사용합니다. 명시적인 `SERVICE_*_INTERNAL_URL`/TOML override는 신뢰된 **HTTPS** URL만
허용하고 빈 환경 변수는 카탈로그를 선택합니다. 같은 호스트에 형제 서비스를
이미지로 설치해야 할 때만 `--profile waygate`, `--profile drover`, `--profile lumen`,
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
- 실제 Kolla 가상 환경에 설치한 고정 버전 역할 패키지 (`lumen-kolla==0.2.0`)
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

`generate_k8s.py --config ./afterglow.conf --output-dir deploy/k8s-template`는 `configmap.yaml`, `secret.yaml`, `grafana-deployment.yaml`을 생성합니다. `[app].secret_key`가 빈 값, `change-me-in-production`, 32자 미만이면 `secret.yaml` 생성을 실패시켜 Kubernetes production guard와 맞춥니다.

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

로컬 Compose의 2026-08-02 채팅 메시지 시간대 컬럼 마이그레이션 예시:

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
