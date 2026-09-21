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
| `DELETE` | `/api/v1/waygate/servers/{server_id}` | 삭제 작업 제출, `202` |

### 서버 생성

```http
POST /api/v1/waygate/servers
Content-Type: application/json

{"name":"tenant-gateway"}
```

응답은 `CREATING` 상태의 서버입니다. worker가 정책 snapshot을 사용해 provider port, security group, floating IP와 VM을 생성하고 상태를 `PROVISIONING`으로 전이합니다. VM 에이전트가 공개키를 등록하면 서버가 `ACTIVE`가 됩니다. 생성 실패 시 이미 만든 OpenStack 리소스를 역순으로 정리하고 서버를 `ERROR`로 기록합니다.

서버 조회 응답은 DB 상태에 최근 에이전트 상태 캐시의 `last_status_reported_at`과 `peer_count`를 병합합니다. 삭제는 `{ "ok": true, "status": "DELETING" }`을 즉시 반환하고 worker가 리소스를 정리합니다.

## 2. 클라이언트(peer)

| 메서드 | BFF 경로 | 설명 |
|---|---|---|
| `POST` | `.../{server_id}/clients` | 클라이언트 발급, `201` |
| `GET` | `.../{server_id}/clients` | 클라이언트 목록과 최근 상태 |
| `PATCH` | `.../{server_id}/clients/{client_id}` | 이름 또는 활성 상태 변경 |
| `DELETE` | `.../{server_id}/clients/{client_id}` | 클라이언트 soft delete, `204` |
| `GET` | `.../{server_id}/clients/{client_id}/config` | WireGuard `.conf` 다운로드 |

### 클라이언트 발급

```http
POST /api/v1/waygate/servers/{server_id}/clients
Content-Type: application/json

{
  "name": "operator-laptop",
  "allowed_ips": ["10.240.0.0/24"],
  "dns": "1.1.1.1"
}
```

서버가 `ACTIVE`이고 서버 공개키가 등록된 경우에만 발급합니다. Waygate가 X25519 키쌍과 다음 터널 IP를 생성하고 private key를 AES-256-GCM으로 암호화해 저장합니다. 생성 응답에는 `tunnel_conf`가 포함됩니다. 설정 다운로드는 저장된 키를 복호화해 최신 활성 네트워크 CIDR까지 `AllowedIPs`에 병합하여 다시 렌더합니다.

브라우저는 `.conf` 파일을 그대로 다운로드하거나 같은 텍스트로 QR 코드를 로컬 생성합니다. QR 이미지나 평문 private key를 별도 API나 DB에 저장하지 않습니다.

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

## 5. 게이트웨이 VM 에이전트

새 게이트웨이 VM은 아래 direct Waygate 경로만 호출합니다.

| 메서드 | 직접 Waygate 경로 | 설명 | 제한 |
|---|---|---|---|
| `POST` | `/v1/servers/{server_id}/agent/register` | 서버 공개키와 listen port 보고, `204` | 30/분 |
| `GET` | `/v1/servers/{server_id}/agent/desired-state` | peer와 `nat_networks` 목표 상태 조회 | 120/분 |
| `POST` | `/v1/servers/{server_id}/agent/status` | handshake와 byte counter 보고, `204` | 60/분 |

사용자 JWT가 아니라 `Authorization: Bearer <agent-token>`을 사용합니다. 토큰은 `server_id`에 직접 바인딩하여 timing-safe 비교로 검증합니다. 누락, 무효 토큰, 다른 서버 토큰은 fail-closed `401`입니다. register는 공개키를 저장하고 허용된 상태를 `ACTIVE`로 전이합니다. desired-state는 활성 peer와 연결된 테넌트 CIDR을 반환합니다. status는 최근 상태를 TTL 캐시에 저장하며 영속 agent token은 DB의 AES-GCM 암호문으로 유지합니다.

## 검증 경계

모의 계약과 단위 테스트는 BFF 전달, 명시 서브넷 port attach, 실패 롤백, detach 정리, callback URL fail-closed, 클라이언트 설정/QR 흐름을 검증합니다. 실제 OpenStack data plane은 별도 환경 검증이 필요합니다.

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
