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
