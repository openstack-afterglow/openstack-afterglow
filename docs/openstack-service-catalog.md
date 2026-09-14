# OpenStack 서비스 카탈로그에 Drover, Lumen, Waygate 등록하기

이 튜토리얼은 OpenStack 관리자가 Drover, Lumen, Waygate API를 Keystone 서비스 카탈로그에 등록하는 절차를 설명합니다. 등록이 완료되면 Afterglow와 다른 OpenStack SDK 클라이언트가 서비스 타입과 RegionOne 같은 리전 이름으로 API endpoint를 해석할 수 있습니다.

Drover k3s 통계에서 다음 오류가 발생하면 이 절차가 필요합니다.

```text
keystoneauth1.exceptions.catalog.EndpointNotFound: public endpoint for drover service in RegionOne region not found
```

Kolla 역할로 서비스를 배포하는 환경에서는 역할이 project, service user, service, public/internal/admin endpoint를 자동으로 생성합니다. 이미 API는 실행 중인데 카탈로그만 누락되었거나 잘못된 경우에만 아래 수동 복구 절차를 사용합니다.

## 준비 사항

- Keystone 관리자 권한이 있는 OpenStack CLI 환경
- `openstack token issue`가 성공하는 `OS_CLOUD` 또는 `OS_AUTH_URL` 기반 인증 설정
- 서비스 API가 HAProxy 또는 지정한 VIP에서 이미 접근 가능한 상태
- Kolla 환경의 external FQDN, internal VIP, 리전 이름

관리자 인증을 확인합니다.

```bash
export OS_CLOUD=admin
openstack token issue
openstack region list
```

등록에 사용할 값을 설정합니다. Kolla 역할의 기본 포트는 Waygate `8010`, Drover `8011`, Lumen `8012`입니다.

```bash
export REGION=RegionOne
export PUBLIC_PROTOCOL=https
export PUBLIC_FQDN=api.example.com
export INTERNAL_VIP=10.0.0.10
```

`PUBLIC_PROTOCOL`은 Kolla의 `public_protocol`과 정확히 일치해야 합니다. 외부 TLS를 구성했을 때만 보통 `https`이며, HTTP로 배포했다면 `http`를 설정합니다. `PUBLIC_FQDN`은 Kolla external FQDN으로, `INTERNAL_VIP`는 컨트롤 플레인 서비스가 접근하는 Kolla internal VIP로 바꿉니다. 실제 Kolla 설정의 `openstack_region_name`, `public_protocol`, `kolla_external_fqdn`, `kolla_internal_vip_address`와 일치해야 합니다.

## 1. 현재 카탈로그 확인

먼저 기존 service와 endpoint를 확인합니다. 존재하는 endpoint를 무조건 다시 만들거나 삭제하지 마십시오.

```bash
for service in waygate drover lumen; do
  echo "== $service =="
  openstack service show "$service" || true
  openstack endpoint list --service "$service" --region "$REGION" -f yaml
  echo
done
```

Drover가 누락된 경우처럼 `service show`가 실패하거나 endpoint 목록에 필요한 interface가 없으면 다음 단계를 수행합니다.

## 2. 서비스 타입 등록

각 서비스의 이름과 service type은 동일합니다. 아래 함수는 service 이름 또는 type이 이미 하나라도 있으면 정확히 한 개의 `name == type == service` 레코드만 허용합니다. 중복, 다른 이름, 다른 type은 자동으로 수정하거나 새 service를 만들지 않고 중단합니다.

```bash
set -euo pipefail

ensure_service() {
  local service="$1"
  local description="$2"
  local service_rows matching_rows matching_count
  local service_id actual_name actual_type actual_enabled

  service_rows="$(openstack service list --long -f value \
    -c ID -c Name -c Type -c Enabled)"
  matching_rows="$(printf '%s\n' "$service_rows" \
    | awk -v service="$service" '$2 == service || $3 == service')"
  if [ -z "$matching_rows" ]; then
    matching_count=0
  else
    matching_count="$(printf '%s\n' "$matching_rows" | wc -l | tr -d '[:space:]')"
  fi

  case "$matching_count" in
    0)
      openstack service create --name "$service" --description "$description" "$service"
      ;;
    1)
      read -r service_id actual_name actual_type actual_enabled <<EOF
$matching_rows
EOF
      if [ "$actual_name" != "$service" ] || [ "$actual_type" != "$service" ]; then
        echo "ERROR: service '$service' does not have matching name and type." >&2
        return 1
      fi
      case "$actual_enabled" in
        True|true) ;;
        *) openstack service set --enable "$service_id" ;;
      esac
      ;;
    *)
      echo "ERROR: ambiguous services for '$service'; reconcile them manually." >&2
      return 1
      ;;
  esac
}

ensure_service waygate "Waygate WireGuard gateway service"
ensure_service drover "Drover K3s Kubernetes provisioning service"
ensure_service lumen "Lumen durable chat and LLM service"
```

다른 이름이나 type의 기존 service, 또는 중복 service는 운영 중인 클라이언트에 영향을 줄 수 있습니다. 이 경우 이름이 비슷한 새 service를 만들지 말고, catalog 사용처를 확인한 뒤 유지보수 시간에 교정합니다.

## 3. endpoint 등록 또는 교정

각 서비스에는 같은 리전에 `public`, `internal`, `admin` endpoint가 필요합니다. public endpoint는 Kolla `public_protocol`과 external FQDN을 사용합니다. internal과 admin endpoint는 Kolla 역할과 동일하게 internal VIP와 HTTP를 사용합니다.

아래 함수는 interface별 endpoint를 정확히 하나만 허용합니다. 누락된 interface만 생성하고, URL만 다르면 기존 endpoint를 수정하며, 중복 endpoint는 삭제하지 않고 수동 조정을 요구합니다.

```bash
ensure_endpoint() {
  local service="$1"
  local interface="$2"
  local desired_url="$3"
  local endpoint_rows endpoint_count endpoint_id actual_enabled actual_url

  endpoint_rows="$(openstack endpoint list \
    --service "$service" \
    --region "$REGION" \
    --interface "$interface" \
    -f value -c ID -c Enabled)"
  if [ -z "$endpoint_rows" ]; then
    endpoint_count=0
  else
    endpoint_count="$(printf '%s\n' "$endpoint_rows" | wc -l | tr -d '[:space:]')"
  fi

  case "$endpoint_count" in
    0)
      openstack endpoint create --region "$REGION" "$service" "$interface" "$desired_url"
      ;;
    1)
      read -r endpoint_id actual_enabled <<EOF
$endpoint_rows
EOF
      actual_url="$(openstack endpoint show "$endpoint_id" -f value -c url)"
      if [ "$actual_url" != "$desired_url" ]; then
        openstack endpoint set --url "$desired_url" "$endpoint_id"
      fi
      case "$actual_enabled" in
        True|true) ;;
        *) openstack endpoint set --enable "$endpoint_id" ;;
      esac
      ;;
    *)
      echo "ERROR: $service/$REGION/$interface has $endpoint_count endpoints; reconcile duplicates manually." >&2
      return 1
      ;;
  esac
}
```

모든 endpoint를 등록 또는 교정하려면 다음 명령을 실행합니다.

```bash
ensure_endpoint waygate public "${PUBLIC_PROTOCOL}://${PUBLIC_FQDN}:8010"
ensure_endpoint waygate internal "http://${INTERNAL_VIP}:8010"
ensure_endpoint waygate admin "http://${INTERNAL_VIP}:8010"

ensure_endpoint drover public "${PUBLIC_PROTOCOL}://${PUBLIC_FQDN}:8011"
ensure_endpoint drover internal "http://${INTERNAL_VIP}:8011"
ensure_endpoint drover admin "http://${INTERNAL_VIP}:8011"

ensure_endpoint lumen public "${PUBLIC_PROTOCOL}://${PUBLIC_FQDN}:8012"
ensure_endpoint lumen internal "http://${INTERNAL_VIP}:8012"
ensure_endpoint lumen admin "http://${INTERNAL_VIP}:8012"
```

현재처럼 Drover public endpoint만 누락된 경우에는 다음 한 줄만 실행합니다. 기존 internal/admin endpoint는 변경하지 않습니다.

```bash
ensure_endpoint drover public "${PUBLIC_PROTOCOL}://${PUBLIC_FQDN}:8011"
```

## 4. Kolla 관리 배포와 정렬

Kolla 역할이 서비스 카탈로그의 정본인 환경에서는 `/etc/kolla/globals.yml`에서 서비스를 활성화하고 Kolla 역할로 catalog를 생성·정렬하는 방식을 우선합니다.

```yaml
# /etc/kolla/globals.yml
enable_waygate: "yes"
enable_drover: "yes"
enable_lumen: "yes"
```

서비스 이미지, 비밀, 데이터베이스 설정을 완료하고 플러그인 설치기를 실행한 뒤
Kolla 관리 노드의 `/etc/kolla`에서 배포합니다.

```bash
kolla-ansible deploy --tags waygate,drover,lumen
```

세 역할의 Keystone precondition은 `deploy`와 `upgrade`에서 실행되며 기본적으로 `*_run_preconditions: true`입니다. `reconfigure`만 실행하면 Keystone catalog를 생성하거나 교정하지 않습니다. 수동 CLI 복구와 Kolla 배포를 섞는 경우에도 URL, 리전, service type을 위 값과 동일하게 유지하십시오.

## 5. 등록 확인

각 서비스에 세 interface가 정확히 하나씩 있고 URL이 예상값과 일치하는지 확인합니다.

```bash
for service in waygate drover lumen; do
  echo "== $service =="
  openstack service show "$service" -f yaml
  for interface in public internal admin; do
    openstack endpoint list \
      --service "$service" \
      --region "$REGION" \
      --interface "$interface" \
      -f yaml
  done
  echo
done
```

Drover 오류를 재현했던 Afterglow API는 access JWT로 다시 요청합니다. JWT의 기본 project와 다른 프로젝트를 검사할 때만 `X-Project-ID` 헤더를 추가합니다.

```bash
export AFTERGLOW_ACCESS_TOKEN='replace-with-access-jwt'
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${AFTERGLOW_ACCESS_TOKEN}" \
  http://localhost:8000/api/v1/dashboard/k3s-stats
```

성공 기준은 HTTP 200 응답의 `"available": true`입니다. `"available": false`이면 이 endpoint는 Drover 예외를 HTTP 오류로 전달하지 않으므로 backend 로그의 `dashboard Drover stats 조회 실패` 예외를 확인합니다.

## 문제 해결

### `EndpointNotFound`가 계속 발생합니다

요청 주체가 사용하는 리전과 interface를 확인합니다. 현재 오류처럼 public endpoint를 찾는 SDK 호출에는 같은 리전의 public endpoint가 반드시 있어야 합니다.

```bash
openstack endpoint list --service drover -f yaml
openstack configuration show
```

`OS_REGION_NAME` 또는 clouds.yaml의 region_name이 endpoint의 `Region`과 다르면 둘 중 하나를 일치시킵니다.

### endpoint URL 또는 연결을 확인합니다

Keystone에 저장된 public endpoint URL을 직접 조회합니다. 아래에서 `endpoint_id`가 비어 있거나 둘 이상이면 3단계의 `ensure_endpoint`로 먼저 정리해야 합니다.

```bash
endpoint_id="$(openstack endpoint list \
  --service drover \
  --region "$REGION" \
  --interface public \
  -f value -c ID)"
endpoint_url="$(openstack endpoint show "$endpoint_id" -f value -c url)"
printf 'Keystone public URL: %s\n' "$endpoint_url"
curl --fail --silent --show-error "${endpoint_url%/}/v1/health"
```

저장된 URL이 `${PUBLIC_PROTOCOL}://${PUBLIC_FQDN}:8011`과 다르면 `ensure_endpoint drover public "${PUBLIC_PROTOCOL}://${PUBLIC_FQDN}:8011"`로 수정합니다. URL이 일치하는데 health probe가 실패하면 서비스 컨테이너, HAProxy bind, 외부 firewall, DNS, TLS 인증서를 점검합니다.

## 로컬 direct 서비스 엔드포인트 오버라이드 (Direct Service Endpoint Overrides)

Afterglow는 기본적으로 인증된 Keystone 카탈로그로 독립 서비스(Lumen, Waygate, Drover, Palimpsest)를 탐색합니다. BFF는 `internal` interface를, SDK는 기존 `os_interface` 설정을 사용합니다. 실제 OpenStack은 원격에 두고 이 서비스들만 로컬에서 실행할 때, 클라우드 카탈로그를 수정하지 않고 Afterglow의 목적지만 명시할 수 있습니다.

> **보안 및 스코프 범위:**
> - 엔드포인트 오버라이드는 Keystone **카탈로그 엔드포인트 탐색만 우회**하며, 사용자/서비스 요청의 Keystone 토큰 인증 및 인가를 면제하지 않습니다.
> - BFF `service_proxy`와 공유 OpenStack connection을 사용하는 Drover/Waygate SDK 호출(대시보드·관리자·MCP)에 같은 설정이 적용됩니다. Nova·Neutron·Cinder 등 원격 OpenStack 서비스의 endpoint와 Keystone 인증 경로는 변경하지 않습니다.

### 토폴로지별 설정 값 (Topology-Specific Values)

- **호스트 직접 실행 백엔드 → 호스트 서비스 (Host backend)**: `http://127.0.0.1:8012` (Lumen), `:8010` (Waygate), `:8011` (Drover), `:8020` (Palimpsest)
- **동일 Docker Compose 네트워크 (Same Compose network)**: `http://lumen-api:8012`, `http://waygate-api:8010`, `http://drover-api:8011`, `http://palimpsest-api:8020`
- **백엔드 컨테이너 → 호스트 포트 바인드 서비스 (Backend container)**: `http://host.docker.internal:8012`

### 설정 우선순위 (Precedence Order)

Afterglow 백엔드가 서비스 엔드포인트를 결정하는 최종 우선순위는 다음과 같습니다:

1. **환경 변수 (Environment variables)**: `SERVICE_LUMEN_INTERNAL_URL` (`SERVICE_WAYGATE_INTERNAL_URL`, `SERVICE_DROVER_INTERNAL_URL`, `SERVICE_PALIMPSEST_INTERNAL_URL`)
2. **알파벳순 병합 TOML 오버라이드 (Alphabetically merged TOML overrides)**: `afterglow.*.conf` 파일들의 `[services]` 섹션 (`afterglow.frontend.conf`, `afterglow.kolla.conf`, `afterglow.operator.conf` 등 알파벳 순서대로 덮어씀)
3. **주 설정파일 (Primary TOML config)**: `afterglow.conf` 파일 내 `[services]` 섹션의 `lumen_internal_url` (`waygate_internal_url` 등)
4. **Keystone 서비스 카탈로그 / 기본값 (Keystone Catalog / Default)**: 선택된 값이 빈 문자열이면 카탈로그 탐색. 명시적인 빈 환경 변수는 nonempty TOML보다 우선하므로 해당 서비스만 카탈로그로 돌릴 수 있습니다.

예를 들어 백엔드가 Compose 안에서 실행 중이면 `.env` 또는 shell에 지정합니다:

```dotenv
SERVICE_WAYGATE_INTERNAL_URL=http://waygate-api:8010
SERVICE_DROVER_INTERNAL_URL=http://drover-api:8011
SERVICE_LUMEN_INTERNAL_URL=http://lumen-api:8012
SERVICE_PALIMPSEST_INTERNAL_URL=http://palimpsest-api:8020
```

또는 활성 설정 파일에 지정합니다. 해당 환경 변수를 설정하지 않아야 TOML이 선택됩니다:

```toml
[services]
waygate_internal_url = "http://waygate-api:8010"
drover_internal_url = "http://drover-api:8011"
lumen_internal_url = "http://lumen-api:8012"
palimpsest_internal_url = "http://palimpsest-api:8020"
```

`SERVICE_LUMEN_INTERNAL_URL=`처럼 명시적으로 비우면 그 서비스는 TOML/dev 기본값 대신 카탈로그를 사용합니다. 비우지 않고 **unset**하면 다음 우선순위가 적용됩니다. 설정을 바꾼 뒤 소비 프로세스를 재시작하세요.

### 주요 동작, 경고 및 규칙

- **Compose 실행 모드별 override 계약**:
  - 기본·운영 manifest는 unset 변수를 컨테이너에 주입하지 않아 TOML 또는 기본 카탈로그를 유지합니다. `.env`/`--env-file`/shell에서 지정한 값과 명시적 빈 값은 그대로 전달합니다.
  - 명시적으로 선택하는 dev 모드는 같은 network의 local service DNS가 기본값입니다. `services:config/up`은 shell/`.env` → nonempty private `[services]` → local DNS 순서로 선택합니다. 명시적 빈 환경 변수는 local DNS보다 우선하여 카탈로그를 선택합니다.
  - dev 활성 파일은 최초 한 번 복사하고 보존하는 `.local-services/afterglow.conf`입니다. 이미 snapshot이 있으면 원본 `afterglow.conf` 수정은 자동 복사되지 않습니다. `npm run services:config`는 실제 선택값을 mode 0600 `.local-services/compose.env`에 저장하며 직접 Compose 실행도 `--env-file .local-services/compose.env -f docker-compose.dev.yml`을 사용합니다.

- **프로덕션 HTTPS 규칙**: `AFTERGLOW_ENV=production` 설정 시 명시적인 서비스 오버라이드 URL은 반드시 `https://` 보안 프로토콜을 사용해야 합니다. HTTP URL 지정 시 부팅 검증에서 `ValueError`가 발생합니다. 빈 값(`""`)은 프로덕션에서도 카탈로그 조회를 안전하게 수행합니다.

- **명시적 오버라이드 실패 시 폴백 없음 (No Fallback)**: 지정 URL이 실패하면 요청을 실패 처리합니다. 테스트 서비스 장애를 숨기고 production catalog 데이터에 접근하도록 자동 전환하지 않습니다.

- **역방향 통신은 별도 설정**: Lumen → Afterglow는 `LUMEN_MCP_CONTROL_PLANE_URL`(dev 기본 `http://backend:8000`)입니다. 브라우저용 `PUBLIC_API_BASE` 및 원격 VM용 `WAYGATE_CALLBACK_BASE_URL`/`DROVER_CALLBACK_BASE_URL`은 각각의 호출자에게 도달 가능한 주소여야 합니다. 원격 VM은 개발 머신의 `localhost`나 Compose DNS에 접근할 수 없으므로 실제 routable URL을 사용하세요.

## 다음 단계

- [Kolla-ansible 배포](deployment.md#kolla-ansible-배포)에서 이미지와 역할을 배포합니다.
- [서비스 repository promotion](service-repository-promotion.md)에서 독립 서비스 이미지와 SDK 배포 경계를 확인합니다.
