# Afterglow 보안 모델

이 문서는 Afterglow 백엔드 (FastAPI) + 프론트엔드 (SvelteKit) 의 보안 모델과
주요 가드레일을 정리합니다. 보안 패치 이력은 [CHANGELOG.md](../CHANGELOG.md) 와
[docs/releases/](releases/) 를 참고하세요.

---

## 인증·인가 모델

```
브라우저 ──[Authorization: Bearer <jwt> (+X-Project-Id)]──▶ FastAPI
                                            │
                                            ├─ 토큰 캐시 검증 (Redis, TTL 60s) ─[Keystone]
                                            │  └ logout/revoke 시 invalidate
                                            │
                                            ├─ project-scoped Connection 생성
                                            │  └ conn._afterglow_project_id 저장
                                            │
                                            └─ assert_resource_owner (defense-in-depth)
                                               └ admin 우회 + 외부/공유 자원 면제
```

### 토큰 lifecycle (Keystone)

- **세션 토큰 캐시**: Redis `afterglow:cached:validate:<sha256>:<project>` (TTL 60초)
- **logout / revoke 시**: `invalidate_token_cache(token, project_id)` 가 cache key 와
  session key 모두 즉시 삭제 → 동일 토큰으로 다음 호출 시 Keystone 재검증 → 401
- **session 절대/idle timeout**: `app/api/deps.py` 의 `_check_session_timeout`

### 브라우저 access/refresh 복구

- `frontend/src/lib/api/client.ts`의 `fetchWithAuth`는 명시적 access token을 붙이는 first-party 요청의 HTTP handshake를 담당한다. JSON API와 채팅/SSE·첨부·다운로드 소비자가 같은 경로를 사용하고, 진행률 XHR 업로드도 같은 인증 복구 정책을 사용한다.
- 현재 세션의 access 만료가 120초 이내이면 요청 전 refresh를 기다린다. 진행 중 갱신에 들어온 요청도 같은 Promise를 기다리므로 background-tab timer가 늦어져도 만료 토큰으로 요청부터 보내지 않는다.
- 첫 401은 refresh 또는 이미 회전한 live token으로 **한 번만** 재시도한다. body·project·사용자 취소 신호를 보존하며, 이미 HTTP 응답을 받아 소비 중인 SSE를 재시작하지 않는다. 취소된 요청은 갱신 뒤 재전송하지 않고 공유 refresh는 다른 요청을 위해 완료한다.
- root layout은 mount, window focus, document visible 복귀 시 즉시 만료를 확인하고 60초 interval도 유지한다. mockup과 logout 중에는 lifecycle 갱신을 시작하지 않는다.
- refresh 자체의 401, 폐기/차단된 Redis 세션, 서버 session timeout, Keystone 인증 만료는 재로그인 대상이다. Keystone token authentication의 `Failed to validate token` 및 `Could not recognize Fernet token` 404는 adapter에서 Unauthorized로 정규화하며, 일반 endpoint/resource 404는 일시적 검증 실패와 구분하지 못하므로 503을 유지한다. Background refresh의 terminal 결과도 보호 요청을 기다리지 않고 로컬 인증을 지우고 로그인 화면으로 전환한다.
- refresh 503·429·네트워크 오류는 인증 실패로 바꾸지 않고 세션을 보존하되, root shell의 닫을 수 없는 인증 복구 dialog로 작업을 중단한다. 기존 화면은 mounted 상태로 남겨 작성 내용을 유지하고, `dialogFocus`가 다른 화면·overlay를 inert 처리한다. 재시도는 기존 coalescing/cooldown 및 `Retry-After`를 따르며 성공하면 동일 화면을 복구한다. 실패 상태는 해당 access token에 묶이고 다른 로그인·회전·로그아웃 이후의 늦은 응답은 새 identity를 덮어쓰지 않는다.
- Kolla HA에서는 backend가 모든 Valkey Sentinel을 통해 현재 master를 해석하고 `redis_url`의 사용자명·비밀번호·DB index를 발견된 master 연결에 적용한다. replica로 승격 정보가 어긋나거나 master 쓰기가 불가능하면 refresh/session 검증은 503으로 fail-closed하며, 브라우저에서 이를 terminal 401로 바꾸지 않는다.
- 외부/presigned URL은 이 복구 경로와 브라우저 Authorization 주입 대상이 아니다. `downloadAuthenticated`는 설정된 API origin의 `/api/v1/` 경로만 인증하고 다른 URL은 자격 없이 요청한다. logout revocation fence와 늦은 401/cross-tab 회전 winner 보호를 유지한다.
- 명시적 로그아웃은 진행 중인 refresh의 성공/실패를 관찰한 뒤 가능한 최신 token의 서버 폐기를 시도한다. Refresh나 폐기 통신 실패가 있어도 이 기기의 auth/storage는 정리하며, 서버 폐기를 확인하지 못한 경우 이를 경고한다. 일시 장애 때 자동으로 전체 세션을 삭제하거나 인증을 우회하지 않는다.

### Claude Gateway 승인 shell과 BFF 경계

- `/oauth/claude/authorize`는 device verification URL로 직접 열 수 있는 public UI shell이다. Complete-link의 `user_code`는 허용 alphabet/length로 검증·정규화해 `sessionStorage`에만 보존하고 `history.replaceState`로 query를 제거한다. Page response와 document는 `Cache-Control: no-store`, `Referrer-Policy: no-referrer`를 사용한다.
- Shell 진입 marker는 password/GitLab login과 project selection을 거쳐 같은 route로 복귀시키지만 권한 자체가 아니다. Approve/deny는 access bearer와 current `X-Project-Id`가 필요한 `/api/v1/chat/claude-gateway/authorize` BFF에서만 가능하다. Catch-all Lumen proxy의 `Depends(get_token_info)`가 unauthenticated request를 401로 거부한다.
- Afterglow는 device code, issued Gateway API key 또는 provider credential을 DB/localStorage에 저장하지 않는다. Lumen이 user/project binding, hashed grant/key, one-time consume, fixed scope와 24시간 expiry를 소유한다. UI는 current project, exact scopes와 expiry를 승인 전에 표시한다.
- Invalid/expired/consumed code는 safe OAuth reason을 사용자 행동으로 바꾸어 새 Claude Code connection을 안내한다. Browser/client logs와 analytics에 query code나 credential을 넣지 않는다.

### 전역 Cloud Shell 자격·격리 경계

- Cloud Shell 승인은 현재 Afterglow access JWT와 `X-Project-Id`를 다시 검증하고, Keystone에서 같은 사용자·프로젝트로 scoped된 token의 사용자/project/만료를 대조합니다. 만료까지 120초 미만인 token은 새 세션에 사용하지 않습니다.
- Redis ticket에는 scoped Keystone token이 짧은 `ticket_ttl_seconds` 동안 포함됩니다. 티켓은 high-entropy opaque 값이고 목적(`cloud-shell`)이 묶이며 원자적으로 한 번만 소비됩니다. Consume 뒤 ticket key는 삭제되고 active ownership key에는 token 대신 서명된 fingerprint/session metadata만 남습니다. Redis가 불가하면 ticket/lock/heartbeat 경로는 503/4500으로 fail-closed합니다.
- 브라우저는 Keystone token, 서비스 프로젝트 자격, Zun exec URL을 받지 않습니다. Backend가 Zun binary WebSocket에 직접 연결하고 browser에는 configured public Afterglow API relay만 노출합니다. Frontend CSP `connect-src`는 설정된 API HTTP(S) origin과 정확히 대응하는 WS(S) origin만 추가합니다. Handshake 뒤 `Origin`을 frontend/CORS allowlist와 정확히 비교하며 누락·userinfo·path/query가 있는 origin도 거부합니다.
- Bootstrap은 PTY echo를 먼저 끈 뒤 bounded payload를 받고, token을 `/dev/shm/afterglow/secure.yaml`의 UID/GID 1000·mode 0600 파일에만 씁니다. `/dev/shm`은 컨테이너 tmpfs이고 영구 Cinder mount `/home/cloudshell`과 분리됩니다. 그 뒤 UID/GID 1000, 빈 supplementary group, `no-new-privs`, 비어 있는 inheritable/ambient/bounding capability로 `bash --login`을 exec합니다. Image layer와 persistent home에는 credential을 쓰지 않습니다.
- Zun 컨테이너는 privileged=false, 고정 CPU/RAM, 운영자 지정 network/security group, 한 개의 managed home volume만 사용합니다. Security group은 전용 service project 소유이며 ingress rule이 없어야 합니다. Dedicated project service credential은 Zun/Cinder lifecycle에만 사용하고 shell 안에는 caller-scoped token만 들어갑니다.
- 영구 홈과 컨테이너는 이름만으로 채택/삭제하지 않습니다. HMAC signature, service-project resource metadata, user/workspace/session fingerprint, expiry가 모두 맞아야 합니다. 중복·collision·metadata 불일치·조회 실패는 자동 정리 대신 fail-closed 상태로 남깁니다.
- 사용자당 전역 singleton reservation/active key가 다른 탭과 프로젝트의 동시 세션을 막습니다. Project switch/logout은 먼저 relay를 닫고 container cleanup을 요청합니다. Idle/max expiry, browser disconnect, backend restart 뒤에는 exact managed container cleanup과 startup/interval reconciler가 보조하지만 persistent home은 명시적 reset 전까지 유지합니다.
- Audit은 `cloud_shell.start`, `cloud_shell.end`, `cloud_shell.reset`의 project/user/status와 safe error code만 기록합니다. Ticket, Keystone token, bootstrap payload, exec URL, terminal bytes는 audit/application log에 기록하지 않습니다. Terminal 내용 자체는 Afterglow DB에 저장하지 않습니다.

주요 위협과 남은 경계:

| 위협 | 완화 | 남은 운영 책임 |
|---|---|---|
| Ticket 재사용·다른 protocol 사용 | purpose-bound atomic consume, 짧은 TTL, user-wide reservation | Redis TLS/auth와 접근 제어 |
| Cross-site WebSocket hijacking | exact Origin allowlist, opaque ticket | 공개 ingress의 HTTPS/WSS 및 WebSocket upgrade |
| Token의 영구 홈 유출 | PTY echo off, tmpfs 0600 config, ephemeral container, token은 home에 미기록 | Zun compute/root와 memory dump 접근 통제 |
| 서비스 프로젝트 resource 탈취/오삭제 | dedicated project, signed exact metadata, duplicate/collision fail-closed | project/network/security-group/quotas와 `SECRET_KEY` lifecycle |
| 컨테이너 escape·outbound 남용 | non-privileged, no capabilities, no-new-privs, fixed resources, ingress-free SG | Zun runtime hardening, registry provenance, egress allowlist/monitoring |
| 중단 뒤 orphan | lease heartbeat, exact cleanup, startup/interval reconciliation | cleanup alerting, staging expiry 검증, 수동 보존 정책 |

### 리버스 프록시 IP 추출

- `X-Forwarded-For` / `X-Real-IP` 헤더는 `settings.trusted_proxies` (CIDR 리스트)
  안에서 들어온 요청에만 신뢰
- 외부 직접 요청의 헤더는 무시 (위조 가능)
- 기본값: `127.0.0.1/32, ::1/128`

---

## Defense-in-depth IDOR 가드 (1.14.0+)

OpenStack RBAC (project-scoped Keystone token) 이 1차 방어선이지만, 다음 시나리오에
대비해 백엔드 layer 에서 한번 더 owner 검증을 수행합니다:

- Neutron / Octavia / Cinder / Trove / Manila policy.json 이 광범위하게 열려 있을 때
- admin 토큰이 누설된 후 admin 권한 없이 cross-project 접근을 시도하는 자동화 도구
- 향후 owner-blind 한 SDK 호출이 실수로 추가될 때 회귀 방지

### 핵심 헬퍼

```python
# backend/app/api/common/owner_check.py
from app.api.common.owner_check import assert_resource_owner

# 1. SDK 로 자원 조회 (없으면 404)
res = await asyncio.to_thread(conn.network.get_router, router_id)

# 2. owner 검증 (admin 통과, 불일치 시 404 — enumeration 방지)
assert_resource_owner(res, conn, token_info, not_found_detail="라우터를 찾을 수 없습니다")
```

- `_resource_project_id` 가 `project_id` / `tenant_id` 양쪽 fallback
- `is_system_admin` 토큰은 우회
- 외부 네트워크 (`is_router_external`) / 공유 네트워크 (`is_shared`) / 공개 share
  (`is_public`) 는 cross-project 노출이 정상이라 면제

### 적용 범위 (1.14.0)

| 모듈 | 엔드포인트 |
|---|---|
| `network/networks.py` | get/delete/update network, FIP associate/disassociate/delete, subnet update/delete |
| `network/routers.py` | get/delete + interface/gateway 모두 |
| `network/security_groups.py` | delete + rule create/delete |
| `network/loadbalancers.py` | LB/listener/pool/member/HM 의 모든 sub-path (lb_id 검증) |
| `database/instances.py` | instance + databases/users/backups + restore + **enable_root_user** |
| `storage/volumes.py` | get/delete + transfer |
| `storage/volume_snapshots.py` | snapshot get/delete + create (volume owner) |
| `storage/volume_backups.py` | backup get/delete/restore + create (volume owner) |
| `storage/file_storage.py` | share delete + access-rule list/grant/revoke |
| `compute/instances.py` *(1차 PR)* | get/delete + start/stop/reboot/shelve/unshelve |

### 적용 안 됨 / minimal

| 모듈 | 이유 |
|---|---|
| Object-storage 검증 | Swift 의 account 모델 (project-scoped token = 그 account 의 컨테이너만 접근) 이 1차 방어선으로 충분. 신규 컨테이너에 `X-Container-Meta-Owner-Project-Id` 자동 부착만 (운영 도구 토대) |

---

## K3s 비밀 데이터 암호화 (HKDF v3)

```
master key (k3s_kubeconfig_encryption_key, 64 hex)
    │
    ▼ HKDF-SHA256 (salt=None, info=b"afterglow-k3s/<domain>")
    │
    ├─ sub-key kubeconfig    ─▶ AES-256-GCM (AAD=domain) → "v3:" + base64(nonce+ct)
    ├─ sub-key node_token    ─▶ ...
    ├─ sub-key notion_config ─▶ ...
    └─ sub-key manager_password ─▶ ...
```

- **Key separation**: 동일 마스터키여도 도메인 간 ciphertext 가 cross-decrypt 되지 않음
- **복호화 fallback 순서**: v3 → v2 (마스터키 직접 + AAD) → legacy (no prefix, AAD 없음)
- v2/legacy ciphertext 복호화 시 **deprecation warning 1회** (도메인 단위) 로그
- 다음 릴리스에서 v2/legacy 제거 예정 — 마이그레이션 스크립트로 batch re-encrypt 필요

---

## Audit Log

- 모든 mutation 엔드포인트는 `app.api.common.activity_recorder.rec()` 로
  `(project_id, user_id, resource_type, action, status, resource_id, source_ip)` 기록
- **Kubeconfig 다운로드** 도 매 GET 마다 `action="kubeconfig_download"` + `extra={"source_ip": ...}` 기록 (1.14.0+) — HEAD 는 사전 요청이라 미기록
- **K3s callback** 는 source IP 와 cluster_id 를 logger 에 기록 (audit table 별도 row 는 callback 응답 후 발생)

---

## 입력 검증

| 항목 | 위치 | 검증 |
|---|---|---|
| Object-storage object name | `_sanitize_object_name` | 제어문자/`..`/leading slash/max 1024자 차단 |
| Upload MIME / 크기 | `object_storage/upload.py` | `app_max_upload_gb` (기본 10GB) |
| K3s `allowed_cidrs` | `models/k3s.py` | `IPvAnyNetwork` Pydantic v2 검증 |
| K3s `node_token` 패턴 | `_NODE_TOKEN_RE` | `^[A-Za-z0-9:_+/=.\-]{8,512}$` |
| K3s callback fields | `K3sCallbackRequest` | `min_length=8` |

---

## Cloud-init 템플릿 (Jinja2)

- `Environment(autoescape=False)` 명시 (YAML/shell 출력에 HTML autoescape 무의미)
- 모든 사용자 입력 변수는 `{{ var | shlex_quote }}` 적용 — shell injection 차단
- `health_check.sh.j2`, `k3s_agent.yaml.j2`, `envmgr_rotate_key.sh.j2`
  - `K3S_TOKEN`, `REPORT_URL`, `INSTANCE_ID`, `SHARE_NAME`, `NEW_KEY` 모두 quoted
  - `envmgr_rotate_key.sh.j2` 는 `printf` heredoc + `NEW_KEY` 형식 정규식 검증

---

## Health Bearer 토큰 (instance_health)

- VM 의 cloud-init 가 backend 로 health 보고 + cephx rotate 권한을 가지는 토큰
- **Lifetime**: 7일 절대 만료 (1.14.0 — 이전: 30일 sliding 으로 사실상 영구)
- VM userdata 노출 시에도 7일 후 자동 만료 → cephx rotate 권한 무효화
- 7일 이상 살아있는 인스턴스는 `health_check.sh` 의 재발급 흐름이 새 토큰 받음

---

## Rate Limiting

- `slowapi.Limiter` 기반, key_func = `_get_real_ip` (`trusted_proxies` 검증 후 추출)
- mutation 엔드포인트별 정책:
  - 인스턴스 create/delete: 5/min, action: 30/min
  - 네트워크/SG/FIP/LB: 10/min
  - K3s create: 2/min, scale: 10/min
  - Volume create: 10/min
- callback 등 인증 없는 endpoint 도 `10/minute` 적용

---

## CORS / RGW

- **백엔드 CORS**: `cors_origin_list` allowlist (wildcard 금지)
- **RGW 버킷 CORS**: `s3.py:_put_bucket_cors` 가 `cors_origin_list` 와 동기화. allowlist 가 비어있으면 CORS rule 자체 삭제 (cross-origin 차단)

---

## Production 부팅 가드

- `AFTERGLOW_ENV=production` + `AFTERGLOW_ALLOW_INSECURE=1` → **즉시 ValueError**
- `AFTERGLOW_ENV=production` + `secret_key` default 값 → **즉시 ValueError**
- dev 환경은 INSECURE=1 + default secret_key 가 경고만 (부팅 허용)

---

## 알려진 제한 / 후속 작업

| 항목 | 우선도 | PR 후보 |
|---|---|---|
| Frontend 토큰 localStorage 평문 저장 (XSS = 계정 탈취) | Critical | PR-D |
| CSP `script-src 'unsafe-inline'` (XSS 방어 무력화) | Critical | PR-D |
| K3s background task admin conn 무한 진행 (logout 무력화) | High | PR-C |
| K8s securityContext / NetworkPolicy 부재 | High | PR-E |
| `:latest` tag + ArgoCD digest pinning | High | PR-E |
| HAProxy 컨테이너 USER root | High | PR-E |
| CI dependency / image scan gate 없음 | High | PR-F |
| Manila CSI manifest 평문 admin password (worker node 노출) | Medium | PR-G |
| extend-session CSRF 보호 부재 | Medium | PR-G |
| K3s callback 토큰 IP 하드 바인딩 (현재는 logging only) | Medium | PR-C |

---

- [루트 Architecture 정본](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md)
- [배포](deployment.md)
