# 전역 Cloud Shell API

Afterglow 사용자 셸에서 현재 프로젝트 권한으로 OpenStack CLI를 실행하는 선택 기능입니다. 영구 홈은 전용 서비스 프로젝트의 Cinder 볼륨이고, 실행 세션은 같은 프로젝트의 일회성 Zun 컨테이너입니다. 브라우저는 Keystone 토큰을 받거나 저장하지 않습니다.

> **활성화 조건:** `[services] cloud_shell = true`와 `[services] zun = true`. 비활성화 시 `/api/v1/cloud-shell` 라우터는 마운트되지 않아 `404`를 반환합니다.

## 공통 인증과 범위

HTTP 요청은 다음 헤더를 사용합니다.

```http
Authorization: Bearer <afterglow-access-jwt>
X-Project-Id: <current-project-uuid>
```

`GET /workspace`는 인증된 사용자에게 허용됩니다. 티켓 발급과 영구 홈 초기화는 현재 프로젝트의 write 권한이 필요하므로 `reader`는 `403`을 받습니다. 한 사용자는 브라우저 탭과 프로젝트 전체에서 활성 또는 준비 중인 세션을 하나만 가질 수 있습니다.

## `GET /api/v1/cloud-shell/workspace`

현재 사용자와 현재 프로젝트에서 보이는 홈·세션 상태를 조회합니다.

```json
{
  "workspace": "available",
  "home_size_gib": 5,
  "session_active": true,
  "session_in_project": true
}
```

| 필드 | 의미 |
|---|---|
| `workspace` | `absent` 또는 Cinder volume 상태. `available`, `in-use` 외 상태도 숨기지 않습니다. |
| `home_size_gib` | 기존 홈 크기 또는 새 홈의 설정 크기입니다. |
| `session_active` | 현재 사용자가 어느 프로젝트에서든 활성/준비 세션을 가지고 있는지 나타냅니다. |
| `session_in_project` | 그 세션이 현재 `X-Project-Id`에 묶였는지 나타냅니다. |

## `POST /api/v1/cloud-shell/tickets`

사용자가 승인 대화상자에서 명시적으로 동의한 뒤에만 호출합니다. 승인 대화상자를 열거나 취소하는 동작은 이 API를 호출하지 않습니다.

- 성공: `201 Created`
- 제한: IP별 `5/minute`
- 같은 사용자의 다른 활성/준비 세션: `409`

```json
{
  "ticket": "single-use-random-value",
  "websocket_path": "/api/v1/cloud-shell/ws",
  "expires_at": 1760000000
}
```

티켓은 Redis에서 원자적으로 한 번만 소비되고 짧게 만료됩니다. 응답에는 Keystone 토큰, 서비스 프로젝트 자격, Zun exec URL이 포함되지 않습니다.

## `WS /api/v1/cloud-shell/ws?ticket=...`

브라우저는 HTTP 응답의 `websocket_path`를 같은 Afterglow origin의 `ws:`/`wss:` URL로 바꿔 연결합니다. 서버는 handshake 후에도 `Origin`을 CORS/frontend allowlist와 대조하고 누락되거나 다른 origin이면 닫습니다.

### 프로비저닝 흐름

서버는 text JSON control frame으로 상태를 순서대로 보냅니다.

```json
{"type":"status","phase":"provisioning"}
{"type":"status","phase":"workspace"}
{"type":"status","phase":"container"}
{"type":"status","phase":"terminal"}
{"type":"status","phase":"authorizing"}
{"type":"ready","expires_at":1760003600,"idle_timeout_seconds":1200}
```

정확한 중간 단계 수는 리소스 재사용 여부에 따라 달라집니다. `ready` 전에는 terminal input을 보내지 않습니다. 서버는 사용자의 현재 프로젝트로 별도 검증한 단기 Keystone 토큰을 컨테이너 안의 tmpfs에 주입한 뒤에만 `ready`를 보냅니다.

### Terminal frame

- 브라우저 → 서버 terminal input: binary frame, 최대 64 KiB
- 서버 → 브라우저 terminal output: binary frame, 각 frame 최대 64 KiB
- 브라우저 → 서버 resize: UTF-8 text JSON, 최대 2 KiB
- browser control frame은 아래 두 형태만 허용합니다.

```json
{"type":"resize","cols":120,"rows":34}
{"type":"ping"}
```

`cols`는 20–500, `rows`는 5–200입니다. 알 수 없는 key, 타입, 범위 또는 control frame은 protocol error로 연결을 종료합니다. Terminal bytes를 JSON이나 UTF-8 문자열로 재인코딩하지 않습니다.

서버 종료·경고 frame 예시:

```json
{"type":"warning","reason":"idle_timeout"}
{"type":"exit","reason":"session_expired"}
{"type":"error","code":"coordination_lost"}
```

| WebSocket close code | 의미 | 사용자 조치 |
|---|---|---|
| `4401` | 티켓/사용자 권한이 만료되거나 유효하지 않음 | 다시 승인합니다. 반복되면 다시 로그인합니다. |
| `4403` | browser origin 거부 | 배포의 frontend/CORS origin을 수정합니다. |
| `4408` | idle timeout | 다시 승인합니다. 홈은 유지됩니다. |
| `4410` | 같은 사용자의 다른 세션 또는 프로젝트 충돌 | 기존 탭의 세션을 닫고 재시도합니다. |
| `4419` | 최대 세션 시간이 끝남 | 다시 승인합니다. 홈은 유지됩니다. |
| `4500` | Zun/Cinder/Redis/relay 실패 | 운영 상태를 확인하고 재시도합니다. |

정상 close, 브라우저 종료, timeout, relay 실패 모두 일회성 컨테이너 정리를 시도합니다. 정리가 완료되기 전에는 사용자 lease를 성공으로 해제하지 않으며 background reconciler가 만료/고아 컨테이너를 다시 처리합니다.

## `DELETE /api/v1/cloud-shell/workspace`

현재 사용자×프로젝트의 영구 홈 Cinder 볼륨을 삭제합니다.

- 성공: `204 No Content`
- 같은 사용자의 활성/준비 세션: `409 workspace_busy`
- home attached/non-available 또는 OpenStack 오류: fail-closed `409`/`503`

UI는 `ConfirmDialog`로 비가역성을 확인한 뒤 호출합니다. HTTP 성공 전에 성공 toast를 표시하지 않습니다. 홈 삭제는 Cloud Shell 전용 metadata와 HMAC signature가 일치하는 정확히 한 볼륨에만 허용되며, 일반 tenant 볼륨은 검색·삭제 대상이 아닙니다.

## HTTP 오류 형식

Cloud Shell 도메인 오류는 FastAPI `detail` 안에 안전한 code/message를 둡니다.

```json
{
  "detail": {
    "code": "active_session",
    "message": "A Cloud Shell session is already active or pending"
  }
}
```

대표 code는 `active_session`, `workspace_busy`, `ticket_expired`, `token_expired`, `cloud_shell_unavailable`입니다. Upstream endpoint, service credential, Keystone token, exec URL은 오류에 노출하지 않습니다.
