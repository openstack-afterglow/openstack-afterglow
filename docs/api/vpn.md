---
title: Waygate VPN
parent: API 레퍼런스
nav_order: 61
---

# Waygate VPN API

Waygate는 프로젝트별 WireGuard 게이트웨이 VM을 프로비저닝하고 클라이언트(peer), 테넌트 네트워크 연결, 백업/복원을 관리하는 독립 서비스입니다. Afterglow 브라우저는 인증 BFF를 사용하고, 게이트웨이 VM 에이전트는 VM에서 도달 가능한 Waygate 공개 origin으로 직접 콜백합니다.

## 경계와 기본 경로

| 호출자 | 기본 경로 | 인증 |
|---|---|---|
| Afterglow 브라우저 | `/api/v1/waygate/servers` | 사용자 `Authorization: Bearer <JWT>` 및 프로젝트 컨텍스트 |
| 서비스 간 직접 호출 | Waygate origin의 `/v1/servers` | 사용자 토큰을 검증하는 Waygate 서비스 경계 |
| 게이트웨이 VM 에이전트 | `${WAYGATE_CALLBACK_BASE_URL}/v1/servers/{server_id}/agent` | 서버에 바인딩된 에이전트 Bearer 토큰 |

Afterglow BFF는 `/api/v1/waygate/servers/...`의 method, body, 인증 헤더와 프로젝트 컨텍스트를 catalog에서 발견한 Waygate `/v1/servers/...`로 전달합니다. 사용자 API는 서버와 하위 리소스의 `project_id` 소유권을 검사합니다. 존재하지 않는 리소스와 다른 프로젝트의 리소스는 모두 `404`로 처리하여 정보 노출을 막습니다.

관리자 UI는 `/admin/waygate`의 `서비스 → Waygate`에서, 사용자 UI는 `/dashboard/network/waygate`의 `네트워크 → Waygate`에서 접근합니다. 두 화면은 같은 프로젝트별 서버·클라이언트·네트워크 관리 기능과 BFF를 사용합니다. 관리자 화면이라고 모든 프로젝트를 조회하지 않습니다. 현재 프로젝트나 인증 토큰이 없으면 요청을 시작하지 않으며, 프로젝트 전환 시 선택·상세·클라이언트 트래픽을 지우고 이전 프로젝트의 비동기 응답, 대기 중인 확인과 다운로드 후속 동작을 버립니다.

에이전트용 Afterglow passthrough 경로는 기존 게이트웨이 VM 호환을 위해 유지되지만, 새 cloud-init에 생성하는 콜백 URL은 항상 직접 Waygate origin과 `/v1/servers/.../agent` 경로를 사용합니다. 경로 문자열을 검사하여 BFF/direct 경로를 추론하지 않습니다.

## 필수 설정

Afterglow 개발 Compose에서는 다음 값을 반드시 지정합니다.

```dotenv
WAYGATE_PUBLIC_BASE_URL=https://waygate.example.com
```

Compose는 이 값을 Waygate 컨테이너의 `WAYGATE_CALLBACK_BASE_URL`로 전달합니다. URL은 게이트웨이 VM에서 도달할 수 있는 `http://` 또는 `https://` origin이어야 하며 사용자 정보, query, fragment, `localhost`, loopback 또는 unspecified 주소를 사용할 수 없습니다. API와 worker는 값이 없거나 안전하지 않으면 시작 단계에서 실패합니다.

Waygate 서버 생성에는 관리자가 구성한 provider network, image, flavor 리소스 정책과 DB/cache가 필요합니다. 정책 또는 DB가 없으면 요청을 성공으로 가장하지 않고 `503`을 반환합니다.

## 1. 서버

| 메서드 | BFF 경로 | 설명 |
|---|---|---|
| `POST` | `/api/v1/waygate/servers` | 서버 생성 작업 제출, `201` |
| `GET` | `/api/v1/waygate/servers` | 프로젝트 서버 목록 |
| `GET` | `/api/v1/waygate/servers/{server_id}` | 서버 상세 |
| `PATCH` | `/api/v1/waygate/servers/{server_id}` | DNS와 PersistentKeepalive 기본값 수정(`ACTIVE`만 허용) |
| `DELETE` | `/api/v1/waygate/servers/{server_id}` | 삭제 작업 제출, `202` |

### 서버 생성

```http
POST /api/v1/waygate/servers
Content-Type: application/json

{"name":"tenant-gateway"}
```

응답은 `CREATING` 상태의 서버입니다. worker가 정책 snapshot을 사용해 provider port, security group, floating IP와 VM을 생성하고 상태를 `PROVISIONING`으로 전이합니다. VM 에이전트가 공개키를 등록하면 서버가 `ACTIVE`가 됩니다. 생성 실패 시 이미 만든 OpenStack 리소스를 역순으로 정리하고 서버를 `ERROR`로 기록합니다.

서버 조회 응답은 DB 상태에 최근 에이전트 상태 캐시의 `last_status_reported_at`과 `peer_count`를 병합합니다. 삭제는 `{ "ok": true, "status": "DELETING" }`을 즉시 반환하고 worker가 리소스를 정리합니다.

서버 기본값은 `dns`(최대 두 주소, `null`이면 DNS 행 생략)와 `persistent_keepalive`(엄격한 정수 `0–65535`, `0`이면 비활성)뿐입니다. `PATCH .../{server_id}`에서 생략한 값은 유지하고, 현재 서버 설정을 상속하는 클라이언트의 목록·새 다운로드·QR에는 변경 값이 즉시 적용됩니다. MTU는 서버 기본값이 아닌 클라이언트별 설정입니다. 다른 프로젝트 서버는 `404`, 이미 `DELETING`인 서버는 `409`이고, 삭제와 수정은 같은 서버 행 잠금으로 직렬화됩니다. 설치된 클라이언트 기기는 자동 갱신되지 않으므로 설정을 다시 가져와야 합니다.

## 2. 클라이언트(peer)

| 메서드 | BFF 경로 | 설명 |
|---|---|---|
| `POST` | `.../{server_id}/clients` | 클라이언트 발급, `201` |
| `GET` | `.../{server_id}/clients` | 클라이언트 목록과 최근 상태 |
| `PATCH` | `.../{server_id}/clients/{client_id}` | 이름, 활성 상태, DNS/MTU/PersistentKeepalive 변경 |
| `DELETE` | `.../{server_id}/clients/{client_id}` | 클라이언트 soft delete, `204` |
| `GET` | `.../{server_id}/clients/{client_id}/config` | WireGuard `.conf` 다운로드 |

### 클라이언트 발급

```http
POST /api/v1/waygate/servers/{server_id}/clients
Content-Type: application/json

{
  "name": "operator-laptop",
  "allowed_ips": ["10.240.0.0/24"],
  "mtu": 1380
}
```

새 클라이언트가 DNS·PersistentKeepalive 값과 상속 플래그를 모두 생략하면 현재 서버 기본값을 상속합니다. 응답은 계산된 `dns`·`persistent_keepalive`와 `inherit_dns`·`inherit_persistent_keepalive` 플래그를 함께 반환합니다. 기존 클라이언트는 schema migration 004에서 두 플래그가 `false`가 되므로 기존에 저장된 명시 설정을 유지합니다. `dns`는 쉼표로 구분한 최대 두 주소/호스트 이름이고, `mtu`는 클라이언트 전용 `576–9000` 정수 또는 `null`(WireGuard 자동값)입니다. 이 설정은 클라이언트 측 `.conf`에만 반영되므로 저장 후 `.conf`를 다시 받거나 QR을 다시 스캔해야 합니다.

```http
PATCH /api/v1/waygate/servers/{server_id}/clients/{client_id}
Content-Type: application/json

{"inherit_dns":false,"dns":null,"inherit_persistent_keepalive":false,"persistent_keepalive":0}
```

이 PATCH는 DNS 행이 없는 명시적 설정과 keepalive 비활성화(0)를 저장하며 서버 기본값이 바뀌어도 따라가지 않습니다. `{ "inherit_dns": true, "inherit_persistent_keepalive": true }`로 다시 상속할 수 있습니다. PATCH에서 생략한 필드는 기존 모드를 유지합니다. `false` 플래그에 대응 값이 없거나 `true` 플래그와 대응 값을 함께 보내거나 플래그가 `null`이면 `422`입니다. 정수에 boolean·문자열을 사용하거나 범위를 벗어나도 거부합니다.

새 클라이언트는 전용 32바이트 난수 사전 공유 키(PSK)를 자동 생성해 암호화 저장하고, 같은 키를 발급/다운로드 `.conf`와 에이전트 desired-state에 포함합니다. 목록·상세·PATCH 응답은 키 자체가 아니라 `psk_enabled` boolean만 반환합니다. 기존 클라이언트는 연결이 끊기지 않도록 PSK를 자동으로 추가하거나 교체하지 않으며, import는 번들의 키를 보존합니다.

클라이언트 응답의 `rx_bytes`/`tx_bytes`는 게이트웨이 WireGuard peer 관점의 누적 카운터이고 `last_reported_at`은 그 값을 담은 에이전트 상태 보고를 Waygate가 받은 시각입니다. Afterglow UI는 클라이언트 관점으로 표시하므로 `클라이언트 수신 RX = tx_bytes`, `클라이언트 송신 TX = rx_bytes`입니다. 브라우저는 열린 프로젝트·서버의 클라이언트별 보고를 최대 60개만 보관하고, 서로 다른 두 보고의 서버 시각 차이로 bytes/s를 계산합니다. 같은/이전 시각 보고, 카운터 감소(재시작·재활성화), 시간 간격 누락, 보고·peer 누락은 속도 공백으로 남깁니다. 비활성 클라이언트와 서버/프로젝트 전환은 이력을 비웁니다. UI의 피어 자동 새로고침은 끔/1/2/5/10/15/30/60초로 서버·네트워크 메타데이터 새로고침과 독립입니다. 지연 보고는 `max(5초, 3 × max(선택한 피어 간격, 에이전트 report_interval_seconds))`를 초과한 보고 시각 또는 브라우저 수신 시각으로 판정하며, 속도를 이어 계산할 때도 같은 간격을 사용합니다. 구형 에이전트가 간격 메타데이터를 보내지 않으면 기존 15초 reconcile 간격을 대신 사용합니다.

서버가 `ACTIVE`이고 서버 공개키가 등록된 경우에만 발급합니다. Waygate가 X25519 키쌍과 다음 터널 IP를 생성하고 private key를 AES-256-GCM으로 암호화해 저장합니다. 생성 응답에는 `tunnel_conf`가 포함됩니다. 설정 다운로드는 저장된 키를 복호화해 최신 활성 네트워크 CIDR까지 `AllowedIPs`에 병합하여 다시 렌더합니다.

브라우저는 `.conf` 파일을 그대로 다운로드하거나 같은 텍스트로 QR 코드를 로컬 생성합니다. QR 이미지나 평문 private key를 별도 API나 DB에 저장하지 않습니다.

클라이언트 행의 다운로드·QR·설정 아이콘은 고정 순서로 표시되고 활성화·삭제 작업과 시각적으로 분리합니다. 각 버튼은 클라이언트 이름이 포함된 접근성 레이블과 제목을 가지며, 변경 작업 중에는 같은 클라이언트의 중복 변경을 막습니다. 연결된 네트워크는 권한 범위에서 이름이 확인되면 그 이름을, catalog에 있으나 이름이 비었으면 `이름 없는 네트워크`를, 보이지 않거나 조회에 실패했으면 `네트워크 이름 확인 불가`를 표시합니다. UUID는 어떤 경우에도 별도로 노출하고 해제 확인에도 포함합니다. 상세 패널이 열릴 때 네트워크 catalog를 읽으며 연결 변경·수동 갱신 때 다시 조회합니다. 주기적인 metadata 폴링은 서버 상세와 연결 목록만 읽고 catalog를 반복 조회하지 않습니다.

피어 상태는 보고가 없거나 `online`이 `null`이면 `알 수 없음`, 마지막 수신 보고가 선택한 피어 주기와 보고된 에이전트 주기로 계산한 지연 한도를 넘으면 `보고 지연`으로 표시합니다. 비활성 피어는 항상 `disabled`입니다. 마지막 보고 경과 시간과 실제 에이전트 보고 주기를 함께 표시하며, metadata가 없는 구형 에이전트를 1초 보고로 표현하지 않습니다. `ONLINE`은 최근 120초 핸드셰이크와 최신 보고가 관측되었다는 뜻이지 단말 연결 보증이 아닙니다.

## 3. 테넌트 네트워크 연결

| 메서드 | BFF 경로 | 설명 |
|---|---|---|
| `POST` | `.../{server_id}/networks` | 네트워크와 IPv4 서브넷 연결, `201` |
| `GET` | `.../{server_id}/networks` | 연결 목록 |
| `DELETE` | `.../{server_id}/networks/{attachment_id}` | 연결 해제, `204` |

Afterglow UI는 프로젝트에서 볼 수 있는 non-external 네트워크만 표시하고, 네트워크 상세의 서브넷을 별도 검색 선택기로 제공합니다. 서브넷이 하나면 자동 선택하고, 서브넷이 없으면 연결 동작을 비활성화합니다.

```http
POST /api/v1/waygate/servers/{server_id}/networks
Content-Type: application/json

{
  "network_id": "11111111-1111-4111-8111-111111111111",
  "subnet_id": "22222222-2222-4222-8222-222222222222",
  "nat_mode": "snat"
}
```

브라우저 경로는 `network_id`, `subnet_id`, `nat_mode: "snat"`를 모두 명시합니다. 직접 Waygate API에서 `subnet_id`를 생략하면 서비스가 해당 네트워크의 첫 IPv4 서브넷을 선택하지만, 운영 UI는 모호성을 피하기 위해 항상 명시합니다.

Waygate는 다음 불변성을 검증합니다.

- 서버가 요청 프로젝트 소유이고 `ACTIVE` 상태입니다.
- 네트워크가 요청 프로젝트 소유이거나 프로젝트에서 사용할 수 있는 shared/external 네트워크입니다.
- 선택한 서브넷이 그 네트워크에 속한 IPv4 서브넷입니다.
- 동일 서버와 네트워크의 활성 연결이 중복되지 않습니다.
- 현재 NAT 모드는 `snat`만 허용합니다.

연결은 선택한 `subnet_id`를 `fixed_ips`에 넣은 Neutron port를 먼저 생성하고, Nova에는 해당 `port_id`를 attach합니다. 성공한 port ID와 CIDR을 attachment에 보존합니다. Nova attach가 실패하면 생성한 port와 attachment 레코드를 롤백합니다. port 정리까지 실패하면 attachment를 `ERROR`로 남겨 운영자가 유실된 리소스를 확인할 수 있게 합니다.

해제는 Nova interface detach 뒤 Neutron port를 삭제합니다. 이미 사라진 Nova interface는 정리 가능한 상태로 취급하지만, Neutron port 삭제가 실패하면 DB 레코드를 지우지 않고 `ERROR`로 남깁니다. 활성 연결의 CIDR은 에이전트 desired-state의 `nat_networks`와 새로 다운로드하는 클라이언트 `.conf`의 `AllowedIPs`에 반영됩니다.

## 4. 백업과 마이그레이션

| 메서드 | BFF 경로 | 설명 |
|---|---|---|
| `POST` | `.../{server_id}/export` | 암호화된 JSON 번들 내보내기 |
| `POST` | `.../{server_id}/import` | 준비된 대상 서버로 번들 가져오기 |

두 API 모두 `GET`이 아닙니다. 패스프레이즈를 요청 body로 받고 래핑된 시크릿을 방출하거나 소비하기 때문입니다.

```json
{"passphrase":"at-least-8-characters"}
```

export는 클라이언트와 네트워크 연결 정보를 포함하지만 서버 private key는 포함하지 않습니다. 클라이언트 private key는 scrypt로 파생한 키와 AES-256-GCM으로 다시 래핑되며 응답에는 `Cache-Control: no-store`가 설정됩니다. import는 같은 패스프레이즈로 키를 검증·복호화하고 입력 validator를 다시 적용합니다. 대상 서버 키는 새로 유지되므로 가져오기 후 클라이언트 `.conf`를 다시 내려받아야 합니다.

export는 상속 중인 클라이언트의 **출발 서버에서 계산된** DNS·keepalive를 bundle 안의 명시 설정으로 고정합니다. 다른 기본값을 가진 서버에 import해도 출발 설정을 보존하며 대상 서버 기본값은 바꾸지 않습니다. MTU·클라이언트 private key·PSK도 그대로 보존하고 네트워크 attachment는 여전히 재생성하지 않습니다.

## 5. 게이트웨이 VM 에이전트

새 게이트웨이 VM은 아래 direct Waygate 경로만 호출합니다.

| 메서드 | 직접 Waygate 경로 | 설명 | 제한 |
|---|---|---|---|
| `POST` | `/v1/servers/{server_id}/agent/register` | 서버 공개키와 listen port 보고, `204` | 30/분 |
| `GET` | `/v1/servers/{server_id}/agent/desired-state` | peer와 `nat_networks` 목표 상태 조회 | 120/분 |
| `POST` | `/v1/servers/{server_id}/agent/status` | handshake와 byte counter 보고, `204` | (client IP, server ID)당 120/분 + client IP 공유 1200/분 |

사용자 JWT가 아니라 `Authorization: Bearer <agent-token>`을 사용합니다. 토큰은 `server_id`에 직접 바인딩하여 timing-safe 비교로 검증합니다. 누락, 무효 토큰, 다른 서버 토큰은 fail-closed `401`입니다. register는 공개키를 저장하고 허용된 상태를 `ACTIVE`로 전이합니다. desired-state는 활성 peer와 연결된 테넌트 CIDR을 반환합니다. status는 최근 상태를 TTL 캐시에 저장하며 영속 agent token은 DB의 AES-GCM 암호문으로 유지합니다.

게이트웨이는 하나의 장기 실행 `afterglow-waygate-reconcile.service`에서 15초마다 원하는 peer/NAT를 reconcile하고 별도 deadline으로 `wg show` 카운터를 기본 1초마다 보고합니다. `/etc/waygate/agent.json`의 `report_interval_seconds`를 엄격한 정수 `1–60`으로 설정할 수 있고 보고 body에도 그 간격을 포함합니다. 두 작업은 순차 실행되므로 느린 reconcile이나 HTTP 응답으로 보고가 지연될 수 있지만 병렬 토큰 writer나 catch-up 폭주는 없습니다. `wg show` 실패는 빈 peer 목록으로 새 보고를 쓰지 않습니다. cloud-init과 prebuilt 이미지에 같은 서비스 파일을 설치하며 반복 systemd timer를 사용하지 않습니다. 여러 게이트웨이가 한 NAT 공인 주소를 공유하면 IP 총 1200/분 제한이 먼저 도달할 수 있습니다.

기존 게이트웨이 VM과 과거 prebuilt Glance 이미지는 구형 timer agent를 그대로 사용합니다. 새 prebuilt 게이트웨이에 1초 보고를 적용하려면 업데이트한 이미지를 별도로 빌드·검증해 image policy를 전환해야 합니다. 기존 VM의 systemd unit 교체·timer 중지는 명시적으로 승인한 migration에서만 수행하며 이 API/UI 변경만으로 자동 적용되지 않습니다. Waygate API/worker보다 먼저 migration 004를 적용해야 기존 클라이언트가 새로운 상속 플래그 없이 잘못 해석되지 않습니다.

## 검증 경계

모의 계약과 단위 테스트는 BFF 전달, 명시 서브넷 port attach, 실패 롤백, detach 정리, callback URL fail-closed, 클라이언트 설정/QR 흐름, 클라이언트 설정 검증과 트래픽 이력 경계(중복·역순·reset·누락·지연)를 검증합니다. 실제 OpenStack data plane은 별도 환경 검증이 필요합니다.

2026-09-28 로컬 확인: Waygate migration 001–004를 격리 MariaDB에 적용하고 Redis와 실제 Uvicorn HTTP로 상속·override·config·export/import·보고 주기를 검증했습니다. Waygate 본체 직렬/4-worker 테스트 각 431건 통과·1건 건너뜀, SDK 36건 통과. Afterglow Waygate 집중 frontend 95건·backend BFF 12건과 전체 gate(backend 3137, frontend 1591, 계약 132, 기능 28, orchestration 9) 및 lint가 통과했습니다. Chromium 375px 모바일 패널의 네트워크 fallback·상태·작업 크기를 확인했고 1280px 셸의 가로 넘침은 없었습니다. 신규 0.2.0 에이전트가 설치된 Glance 이미지의 부팅·실제 신규 VPN 트래픽과 OpenStack lifecycle은 검증하지 않았습니다.

Waygate의 opt-in lifecycle 검증은 다음 환경값으로 실행합니다.

```bash
WAYGATE_RUN_LIVE=1 \
WAYGATE_LIVE_BASE_URL=https://waygate.example.com \
WAYGATE_LIVE_AUTH_TOKEN=... \
WAYGATE_LIVE_NETWORK_ID=... \
WAYGATE_LIVE_SUBNET_ID=... \
uv run pytest tests/test_live_waygate_lifecycle.py -v
```

이 검증은 서버 생성과 `ACTIVE` 대기, 명시 서브넷 attach/list/detach, 서버 삭제와 `404` 수렴을 실행합니다. WireGuard 클라이언트 handshake와 내부 인스턴스 도달성은 실제 클라이언트와 대상 VM이 있는 운영 런북에서 별도로 확인해야 합니다.
