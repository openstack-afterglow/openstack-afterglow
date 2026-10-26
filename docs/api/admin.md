---
title: 관리자 (Admin)
parent: API 레퍼런스
nav_order: 20
---

# 관리자 (Admin) API

> 태그: `admin`, `admin-instances`, `admin-services`, `admin-worker-runtime`, `admin-flavors`, `admin-identity`, `admin-gpu`, `admin-libraries`, `admin-notion`, `admin-images`, `admin-activity`, `admin-orphans`, `admin-dashboard`, `admin-announcements`, `admin-key-manager`
> 기본 경로: `/api/v1/admin`

관리자 API는 클러스터 전체(모든 프로젝트)를 대상으로 하는 **현재 system-admin 권위로 보호된** 관리 기능입니다. 이것이 모든 공급자에게 system-scoped token을 보낸다는 뜻은 아닙니다. Native 정책에 맞춘 provider admin-project 실행과 caller-bound credential/telemetry를 구분하며 하이퍼바이저·리소스 집계·전체 조회·VM/볼륨/네트워크·directory/quota/role·GPU/이미지/Notion·고아 정리 등을 제공합니다.

## 인증 및 권한

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` — 관리자(system admin) 권한 계정의 access JWT |
| `X-Project-Id` | (선택) 논리적 요청 프로젝트 UUID. 대상 ID만으로 Keystone 토큰의 실제 인증 범위나 서비스 조회 권한이 바뀌지는 않음 |

**모든 관리자 엔드포인트에는 `Depends(require_admin)`가 적용**됩니다(개별 또는 라우터 의존성). 캐시 없이 native token, live `domain_context`, 정확한 Keystone `system:all` 권한을 재검증합니다. 현재 grant가 없거나 stale이면 `403`과 `detail={code:"system_admin_required",message:"Current system:all administrator authority is required"}`, 무효 token은 `401`, directory 장애는 `503`입니다. 프로젝트 역할 이름이나 JWT flag만으로 관리자 권한을 부여하지 않습니다.

브라우저의 관리자 강등은 정확한 first-party `/api/v1/admin` 경로 경계의 `403`에만 적용됩니다. 이 경우 stale `isSystemAdmin`을 해제하고 관리자 화면에서 `/dashboard`로 이동하되 로그인 token은 유지합니다. `/api/v1/chat/admin/...`·Drover 같은 downstream 서비스 거부나 query 값에만 `/admin`이 있는 요청은 일반 resource 오류로 표시하며 platform-admin flag·현재 route·세션을 바꾸지 않습니다.

Lumen·Drover·Waygate·Palimpsest 관리 화면의 resource 작업에서 BFF는 **현재 project membership 또는 verified human `system:all` authority**와 원래 credential을 검증하며 action 정책을 복제하지 않습니다. 최종 허용은 각 native 서비스의 현재 `oslo.policy`·운영자 `policy.yaml`이 결정하고 UI capability도 해당 결과를 사용합니다. 기본 정책의 system-admin 지원은 operator의 action 거부를 우회하지 않습니다. System 관리자는 선택 target의 프로젝트 멤버십·세부 service leaf가 없어도 native 검증을 요청할 수 있지만 target의 native enabled 상태와 선택 도메인을 검증합니다. 원본 native project/system/unscoped 인증 범위는 유지하며, BFF가 원래 connection project와 논리 target을 각각 native `X-Project-Id`·`X-Target-Project-Id`로 전달합니다. Browser가 native target 헤더를 권위 있게 주입할 수는 없습니다. 명시한 빈 target도 원본 범위로 대체하지 않습니다.

Projectless 예외는 위 service BFF에 한정되며 core OpenStack project scope나 다른 사용자의 세션·개인 credential 소유권을 만들어 내지 않습니다. Native 서비스는 현재 raw user/group system grant·role-ID graph, 원본 reduced-token/API-key ceiling과 실제 provider send를 독립 검증합니다. Drover·Waygate provider 변경은 전용 non-admin executor가 필요하며, 미설정·읽기 장애는503, 권한 회수는 거부입니다. [Native 설정·schema·drain 선행 조건](../deployment.md#system-관리자-서비스-작업의-native-선행-조건)을 먼저 확인하세요.

- 대부분의 라우터는 `/api/v1/admin` prefix에 마운트됩니다.
- 예외: 라이브러리 관리(`/api/v1/admin/libraries`), 공지(`/api/v1/admin/announcements`).
- 캐시 기반 조회 엔드포인트는 대부분 `refresh` (query, boolean, 기본 `false`) 파라미터로 캐시 무시 재조회를 지원합니다.
- 목록 조회는 대체로 `limit`(1~100, 기본 20) + `marker` 커서 페이지네이션을 사용하며 `{ "items": [...], "next_marker": ..., "count": N }` 형태로 응답합니다.

![관리자 개요](../../assets/admin-page.png)
*관리자 개요 페이지 — 클러스터 전체 vCPU·RAM·Disk 사용률, 총 VM/하이퍼바이저 수, 프로젝트별 리소스 할당량을 한 화면에서 조회*

---

## Aodh 경보와 Gnocchi 서비스 점검

UI: [Aodh 경보](/admin/monitoring/aodh), [경보 설정](/admin/monitoring/aodh/settings), [Gnocchi 서비스](/admin/monitoring/gnocchi). 기존 통합·exporter 모니터링과 독립적이며 native 서비스 미설치가 다른 화면을 비활성화하지 않습니다.

모든 경로는 fresh `require_admin`과 요청자 `get_os_conn`을 사용합니다. `alarming` catalog의 Aodh `/v2`, `metric` catalog의 Gnocchi `/v1`을 기존 interface/region으로 발견합니다. 별도 서비스 계정·DB·자격 증명·공유 cache는 없습니다. 성공·dependency/입력/변경 오류까지 `Cache-Control: no-store, private`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`입니다. Native 조회 권한은 실제 caller scope와 서비스 정책이 최종 결정합니다.

| 메서드 | `/api/v1/admin/telemetry` 아래 경로 | 계약 |
|---|---|---|
| GET | `/aodh` | `status,error,checked_at,capabilities,alarms`; capabilities와 목록 상태는 독립적 |
| GET | `/aodh/alarms` | `limit` 기본25·최대100, UUID `marker`, 선택 `state=ok|alarm|insufficient data` |
| GET | `/aodh/alarms/{alarm_id}` | 경보 정의와 독립 `history` 페이지; `limit,marker`는 이력에 적용 |
| POST | `/aodh/alarms` | native 생성201, 정제된 경보 응답 |
| PUT | `/aodh/alarms/{alarm_id}` | 전체 편집 정의 갱신200 |
| DELETE | `/aodh/alarms/{alarm_id}` | 명시적 삭제204 |
| GET | `/gnocchi` | capabilities·processing·archive_policies·archive_policy_rules·resource_types를 독립 점검 |
| GET | `/gnocchi/resources` | `type` 기본generic, `limit,marker`; ID·프로젝트·수명·미터 관계만 공개 |
| GET | `/gnocchi/metrics` | `limit,marker`; ID·이름·단위·리소스·archive policy |
| GET | `/gnocchi/metrics/{metric_id}/measures` | `hours`1–168·기본1, `aggregation`기본mean, 선택 양수 `granularity`; 실제 timestamp/granularity/value 최대512개 |

Section은 `{status,error,data}`, Page는 `{status,error,items,next_marker,truncated}`입니다. 상태는 `available/partial/not_configured/forbidden/unavailable/not_found`이며 native 실패를 정상 빈 배열이나 실측0으로 바꾸지 않습니다. nonempty 페이지는 서버 `max_limit`에 걸려 짧더라도 마지막 UUID marker를 유지하므로 명시적 빈 페이지가 종료 증거입니다. 대시보드 수는 로드된 페이지 수이지 전체 클라우드 경보 수가 아닙니다.

경보 편집은 `name,type,<type>_rule`을 필수로 하고 `description,enabled,severity,repeat_actions,alarm_actions,ok_actions,insufficient_data_actions,time_constraints`를 전달합니다. severity는 `low/moderate/critical`입니다. 제공되지 않은 optional 값을 임의 기본값으로 덮지 않고, supplied native rule/time constraints 내부 JSON을 그대로 보존합니다. 알 수 없는 top-level 필드는 조용히 버리지 않고400으로 거부합니다. 표준 type은 Gnocchi resource/metric/resource-aggregation threshold 세 종류, event, composite, loadbalancer_member_health, prometheus입니다. Native rule 의미·quota·policy가 최종 권위입니다. 상태 강제 변경·알림 재전송 API는 제공하지 않습니다.

알림 URL은 세 상태별 목록으로 관리합니다. `http/https`, `trust+http/trust+https`, `log`, `zaqar/trust+zaqar`, `trust+heat`를 전달하며 **Afterglow는 URL을 호출하거나 연결 검사하지 않습니다**. Native가 주입한 trust ID/userinfo는 읽기에서 제거하고 사용자가 입력한 trust ID는 거부합니다. 일반 webhook·Zaqar signed query는 편집에 필요한 private 응답에 남을 수 있으므로 URL을 비밀로 취급하며 화면에서 링크로 열거나 브라우저 저장소에 보존하지 않습니다. History의 raw `detail`, arbitrary resource metadata·worker/config 정보는 공개하지 않습니다.

Native capabilities는 API/storage 기능이지 설치된 notifier 플러그인 목록이나 실제 전달 증명이 아닙니다. 직접 `mailto:`/SMTP·Slack/Telegram 전용 driver를 꾸미지 않으며 호환 webhook relay 또는 배포된 Zaqar subscriber를 사용합니다. Trust 액션은 caller 권한 위임과 외부 효과를 수반합니다. 생성·수정·삭제는 retry/redirect/재인증 replay 없이 한 번만 제출하고, 응답 유실·2xx malformed 등은503 `detail.code=telemetry_mutation_uncertain`으로 반환합니다. 재제출 전에 native 목록/정의를 다시 읽어 결과를 확인해야 합니다. Native400/403/404/409는 고정 오류로 노출하고 원문 provider body는 숨깁니다.

Gnocchi는 읽기 전용입니다. `/status`의 pending measures/metrics는 관측된 backlog이지 metricd/ingester 전체 건강 판정이 아닙니다. Archive 보존 정책·rule과 resource type은 점검만 합니다. 측정값은 raw native 단위·실제 grain을 유지하며 CPU-percent로 추정하거나 빈 값을0으로 채우지 않고 `refresh=true` 수집 동기화를 요청하지 않습니다. 상세 bounds·운영 전제는 [배포 가이드](../deployment.md#관리자-aodhgnocchi-운영-전제)를 따릅니다.

## 관리자 자격 증명

UI: [애플리케이션 자격 증명](/admin/application-credentials), [사용자 자격 증명](/admin/user-credentials).
두 API는 `require_admin` 확인 뒤 **요청자의 인증 토큰으로 만든 `get_os_conn`**에서 Keystone native API를 호출합니다. 서비스 계정으로 재인증하거나 관리자 화면이라는 이유로 Keystone 정책을 우회하지 않습니다. 아래 기능의 실제 조회·변경 범위는 요청 토큰과 Keystone 정책에 따르며, 문서 상단의 시스템 관리자 접근 요건이 곧 시스템 스코프 SDK 토큰을 뜻하지는 않습니다.

**아래 모든 credential route는 non-empty query `domain_id`가 필수**입니다(context·list·get·create·patch·delete 모두). 생략/빈 값은 `422 credential_invalid_input`이며 no-store입니다. 이름이 아니라 정확한 Keystone domain ID를 확인합니다. 본문으로 domain을 바꾸지 않으며 user/project를 native directory에서 검증해 같은 도메인에만 접근합니다. 다른 도메인이나 소유권 metadata 불일치는 `403 credential_scope_denied`; native operation 오류는 아래 매핑을 유지합니다.

Explicit owner/project native lookup는404를 반환할 수 있고 목록의 소유권을 입증하지 못한 credential row는 제외합니다. PATCH 반환 owner/project 불일치는 `credential_scope_denied`로 결과 공개를 거부하지만 기존 credential을 파괴할 수 있는 보상 삭제/되돌리기는 하지 않습니다. 보상 삭제는 새로 생성한 credential에만 적용됩니다.
### 애플리케이션 자격 증명 (`application-credentials`)

| 메서드 | 경로 | 입력·응답 |
|---|---|---|
| `GET` | `/api/v1/admin/application-credentials` | 선택 query `user_id`; 생략하면 현재 사용자. `{items: [...]}` |
| `GET` | `/api/v1/admin/application-credentials/context` | 현재 실제 인증 사용자·프로젝트·토큰 역할의 `{domain_id,user_id,project_id,roles:[{id,name}]}` |
| `GET` | `/api/v1/admin/application-credentials/{credential_id}` | 선택 query `user_id`; 생략하면 현재 사용자. metadata 단건 |
| `POST` | `/api/v1/admin/application-credentials` | `{name, description?, role_ids, expires_at?}` → `201`, metadata와 **1회 표시용 `secret`** |
| `DELETE` | `/api/v1/admin/application-credentials/{credential_id}` | 선택 query `user_id`; 생략하면 현재 사용자. `204` |

Metadata는 `domain_id`, `id`, `user_id`, `name`, `description`, `project_id`, `expires_at`, `unrestricted`, `roles:[{id,name}]`만 반환합니다. 목록·상세에는 secret이 없으며 생성 응답에서 한 번만 반환합니다. Native 계약에 수정/PATCH는 없습니다. List는 확인된 도메인의 프로젝트에 속한 해당 user의 credential만 반환하며 별도 limit/marker 계약은 없습니다.

생성은 **현재 사용자와 현재 실제 인증 프로젝트에서만** 가능합니다. 논리적 `X-Project-Id`와 `connection_project_id`가 다르거나 SDK access의 사용자·프로젝트가 일치하지 않으면 거부합니다. 본문의 `user_id`, `project_id`, `unrestricted`, `secret` 등 미정의 필드는 허용하지 않습니다. `role_ids`는 현재 토큰 역할 ID의 부분집합이어야 하며 비어 있을 수 없습니다. Keystone에는 역할 ID와 `unrestricted=false`를 보내고 프로젝트는 토큰에서 결정하게 합니다. 다른 사용자 조회·삭제가 Keystone 정책상 허용되더라도 그 사용자를 대신한 생성 권한은 부여하지 않습니다.

- `name`: 1–255자, `description`: 기본 빈 문자열·최대 4096자, `role_ids`: 1–128개.
- 경로/query/역할 ID: 1–128자, 영문·숫자·`_`·`.`·`-`만 허용합니다.
- `expires_at`: 생략/null 또는 **미래의 timezone-aware 시각**. 요청은 UTC `Z`로 전달합니다. 필수 만료나 별도의 최대 유효기간을 강제하지는 않습니다.
- 생성 결과의 프로젝트·정확한 역할 ID 집합·restricted 상태·ID·비어 있지 않은 secret을 확인합니다. 만료를 요청했으면 반환 만료도 해석 가능하고 요청보다 늦지 않아야 합니다. 불일치하면 반환된 native ID로 revoke를 보상 시도하고 secret을 공개하지 않습니다. 삭제 성공 또는 이미 삭제된 경우 원래 `403 credential_scope_denied`를 반환합니다. 보상 삭제 실패는 **502 `credential_rollback_failed`**이며 살아 있는 credential이 없다고 보장할 수 없습니다.

### 사용자 자격 증명 (`user-credentials`)

| 메서드 | 경로 | 입력·응답 |
|---|---|---|
| `GET` | `/api/v1/admin/user-credentials` | 선택 query `user_id`; 선택 domain의 native user/project에 귀속된 credential만 `{items:[...]}`로 반환 |
| `GET` | `/api/v1/admin/user-credentials/{credential_id}` | 기본 metadata만 반환. 명시적 `sensitive=true`일 때만 `blob` 추가 |
| `POST` | `/api/v1/admin/user-credentials` | `{user_id, project_id?, type, blob}` → `201`, metadata |
| `PATCH` | `/api/v1/admin/user-credentials/{credential_id}` | `user_id`, `project_id`, `type`, `blob` 부분 갱신 → metadata |
| `DELETE` | `/api/v1/admin/user-credentials/{credential_id}` | `204` |

Metadata는 `{domain_id,id,user_id,project_id,type}`만 포함합니다. **목록·생성·수정 응답에서 blob을 생략**합니다. 기존 Keystone credential 관리이며 새 EC2 키 자동 발급 API가 아닙니다. `type`은 1–255자, `blob`은 1–65536자의 문자열입니다. 생성 `type="ec2"`는 project_id와 JSON으로 파싱 가능한 blob이 필요하며 임의 access/secret 구조를 보완하지 않습니다. PATCH는 각 필드 독립 선택이며 생략/null은 제외합니다. 실제 변경 없음은 `422`; null로 지우는 계약이 아닙니다. 기존 credential owner/project와 변경 후 owner/project가 모두 선택 domain에 속해야 합니다. 미정의 필드는 거부합니다.

모든 자격 증명 route의 정상 응답과 route가 처리하는 검증/HTTP 오류에는 `Cache-Control: no-store, private`, `Pragma: no-cache`를 붙입니다. Blob/secret을 URL·로그·활동 기록·브라우저 영속 저장소에 복사하지 마세요. 공개 native 오류는 원본 Keystone 본문을 노출하지 않는 다음 `detail` 코드입니다.

| HTTP | `detail` | 의미 |
|---|---|---|
| `422` | `credential_invalid_input` | 입력 검증 또는 빈 PATCH; 민감 입력을 검증 응답에 되비추지 않음 |
| `403` | `credential_scope_denied` | 선택 domain·owner/project·역할·반환 범위 검증 실패 |
| `403` | `credential_native_denied` | Native 401/403 또는 권한 거부 |
| `404` | `credential_not_found` | Native 대상 부재 |
| `409` | `credential_conflict` | Native 충돌 |
| `400` / `422` | `credential_native_invalid` | Native 입력 거부 |
| `502` | `credential_rollback_failed` | native 발급 후 보상 삭제 실패; 발급이 없었다는 일반 거부와 구분 |
| `503` | `credential_unavailable` | 그 밖의 native 장애 |

인증·관리자 의존성 및 SDK connection 생성 실패는 각 의존성의 기존 오류 계약을 사용합니다.

---

## 호스트 건강 관측 (`host-health`)

UI: [하이퍼바이저](/admin/hypervisors). `GET /api/v1/admin/host-health`는 관리자 전용이며 `Cache-Control: no-store`로 **공유 Redis snapshot만 읽습니다**. 브라우저 요청이 새 probe나 Nova 조회를 시작하지 않습니다.

응답은 `{enabled, interval_seconds:10, collected_at, stale, error, hosts}`입니다. 호스트에는 `id`, `name`, `role`(`compute/controller/storage`), `address`, `reachability`, `heartbeat`, `metrics`, `metrics_error`, `interfaces`, `interfaces_omitted`가 있습니다. `reachability`는 `{status, checked_at, latency_ms, error}`, `heartbeat`는 `{status, updated_at, source}`이며 각각 `up/down/unknown`입니다.

애플리케이션 주 프로세스의 lifespan에서 독립 collector를 시작합니다. 여러 backend 프로세스 중 cloud별 Redis **30초 lease** 소유자만 수집하고 5초마다 갱신합니다. 소유자 fence 아래 snapshot·counter baseline·history를 함께 게시하며 Redis/lease 상실 시 수집을 중단합니다. Nova discovery와 exporter 수집은 분리되어 느린 Nova 조회가 exporter cycle을 막지 않습니다. nominal 10초 간격, cycle 중복·밀린 slot 몰아 실행은 없습니다.

Nova `nova-compute`와 hypervisor의 정확한 `host_ip`를 매핑하고, scheduler/conductor의 host DNS를 controller로 사용합니다. 설정 대상은 동일 role/name의 주소·포트를 override하며 storage 및 Nova에 없는 호스트를 추가할 수 있습니다. 최대 64호스트, 동시 8 probe, probe당 3초, exporter body 2 MiB·전체 sample 40000개 제한입니다. Bare DNS/IP만 받으며 DNS의 모든 응답을 안전성 검사하고 선택한 IP로 연결을 고정합니다. `GET http://<검증 IP>:<port>/metrics`만 사용하고 redirect·환경 proxy·인증·query·response 압축은 사용하지 않습니다.

`metrics`의 `cpu`, `memory`, `disk`, `network_rx`, `network_tx`는 각각 `{value, unit, series:[{ts,value}]}`입니다.

- CPU `%`: 연속 CPU counter 차이에서 idle+iowait를 제외한 비율. guest/guest_nice는 중복 합산하지 않습니다.
- Memory `%`: `100 × (1 - MemAvailable / MemTotal)`.
- Disk `%`: 지원하는 파일시스템의 **단일 writable `/`**에서 `100 × (1 - avail / size)`. 전체 디스크 합계·Ceph pool·인스턴스 할당률이 아닙니다.
- Network `B/s`: loopback과 일반 virtual/stacked NIC를 제외한 RX/TX byte counter 차이 합계. VLAN·bridge·bond/team 등 중복 집계를 피하며 누락/불일치 counter를 0으로 메우지 않습니다.
- `interfaces`: 최대 32개 NIC의 `name`, exporter label의 `mac`/`operstate`, `addresses`, RX/TX byte·packet `*_total`, `*_per_second`. 주소는 `node_exporter --collector.netdev.address-info`가 제공할 때만 있으며 미수집은 `null`입니다. 이는 LLDP나 케이블 연결 증거가 아닙니다.

첫 표본·counter reset·NIC/CPU membership 변경·유효하지 않은 counter·30초 초과 gap은 해당 **차분 rate를 `null`**로 표시합니다. Memory/filesystem gauge는 유효한 첫 표본에서도 계산 가능합니다. Exporter 주소·포트·실제 pinned IP가 달라지면 이전 baseline/history와 연결하지 않습니다. 호스트별 각 metric history는 최근 600초·최대 60 points이며 Redis snapshot TTL은 1200초입니다. 누락 구간을 interpolation하거나 정상 0으로 표시하지 않습니다.

30초보다 오래된 snapshot/probe는 현재 값과 NIC 관측을 비우고 exporter 상태를 `unknown`으로 바꾸며 과거 history는 과거 관측으로 남깁니다. Nova inventory 관측이 오래되면 heartbeat도 `unknown`입니다. `not_collected`, `redis_unavailable`, `snapshot_invalid`, `snapshot_stale`, `discovery_failed`, `target_limit` 등은 `error`로 표시하며 **빈 응답·null은 건강함의 증거가 아닙니다**. Exporter HTTP 200이어도 metrics parsing/완전성은 별도입니다. Nova heartbeat와 Afterglow→exporter reachability는 서로 다른 관측이며 실제 ping, host 간 통신, 데이터 plane 정상 또는 물리 장비 생존을 보장하지 않습니다.

---

## 인프라 토폴로지와 호스트 관측

UI: [인프라 토폴로지](/admin/infrastructure-topology). 프로젝트 Neutron 지도 `/api/v1/admin/topology`와 다른 **호스트 inventory 및 수집된 네트워크 증거**입니다. 설치·허용 대상은 [배포 가이드](../deployment.md#관리자-호스트-관측과-트래픽-분석-운영)를 참조하세요.

| 메서드 | 경로 | 권한·응답 |
|---|---|---|
| `GET` | `/api/v1/admin/infrastructure-topology` | `require_admin`; snapshot |
| `POST` | `/api/v1/admin/infrastructure-topology/hosts/{host_id}/traces` | `require_admin`; `{target:"허용된 literal IP"}` → `202`, queued job |
| `POST` | `/api/v1/monitoring/host-observations/{host_id}/reports` | 해당 호스트 전용 bearer; observation → `202`, `{accepted:true,captured_at}` |
| `GET` | `/api/v1/monitoring/host-observations/{host_id}/jobs` | 해당 호스트 전용 bearer; `{job,peer_targets}`. 기본 `claim=true`; busy일 때 `?claim=false`로 peer admission만 갱신 |
| `POST` | `/api/v1/monitoring/host-observations/{host_id}/jobs/{job_id}/result` | 해당 호스트 전용 bearer; trace result → `202`, `{accepted:true}` |

이 route들의 정상 응답은 `Cache-Control: no-store`입니다. Observer API는 사용자 access JWT가 아니라 설정된 **호스트별 서로 다른 token**으로 인증합니다. 다른 host_id의 token은 `401 observer_unauthorized`; token은 administrator snapshot에 반환하지 않습니다. `host_id` 형식은 `compute|controller|storage` + `:` + 소문자 영문/숫자로 시작하는 `[a-z0-9_.-]` 이름(최대 253자)입니다. `job_id`는 UUID입니다. Observer body는 파싱 전에 **256 KiB**로 제한하며 초과는 `413 observation_payload_too_large`, identity 이외 encoding은 `415 content_encoding_not_supported`입니다.

Snapshot은 `{enabled, error, inventory_error, interval_seconds:10, trace_targets, hosts, flows, fabric}`입니다. Health inventory와 configured observers를 합쳐 최대 256호스트를 반환하며 호스트는 `id`, `name`, `role`, `address`, `reachability`, `heartbeat`, `observer_configured`, `observation_state`(`unmeasured/fresh/stale`), `observation`, `peer_probes`, `traces`입니다. Inventory 실패(`inventory_error`, 초과 시 `inventory_truncated`)와 관측 store 실패(`error`: `topology_disabled/topology_store_unavailable/topology_store_invalid`)를 구분합니다. GET은 공유 snapshot을 읽으며 새 host probe·SNMP poll을 시작하지 않습니다. Store 장애·관측 부재는 정상 링크의 증거가 아닙니다.

공개 `host.observation`은 `captured_at`, `boot_id`, `interfaces`, `interfaces_omitted`, `evidence_omitted`, `neighbors`, `routes`, `lldp`, `peer_probes`, `sources`입니다. `sources`의 addresses/neighbors/routes/lldp/counters/peer_probes/flows는 `measured/unsupported/error`를 구분합니다. Interface는 `name`, `mac`, `operstate`, `addresses`, `ifindex`, `physical`(true/false/null), RX/TX bytes·packets 누적 counter와 서버가 계산한 `rates`, `history:[{ts,rates}]`입니다. LLDP는 `interface`, `chassis_id`, `port_id`, `system_name`, `management_address`, `port_description`을 담습니다. 최대 interfaces 64개(주소 각 32개), neighbors 256개, routes 256개, LLDP 128개, peer probes 64개이며 모든 neighbor/route/LLDP는 보고된 interface를 참조해야 합니다. 잘린 inventory/evidence는 omitted 수로 명시합니다. 원본 flow counter·`collector_id`·내부 `flow_rates`는 공개 observation에서 제거하고 별도의 `snapshot.flows`로만 rate를 반환합니다.

- **물리 인접 근거는 LLDP의 local interface·remote chassis/port identity**이며 LLDP 부재는 케이블 부재가 아닙니다. Host `physical=true` NIC와 일치한 LLDP만 fabric join에 사용합니다. Switch port는 LLDP local port number를 ifIndex로 간주하지 않고 이름/MAC alias의 유일한 일치와 `physical=true`가 있어야 계측 port로 연결합니다. Bond·bridge·가상·unknown-physical·미해결 port는 진단 근거일 수 있지만 측정된 cable이 아닙니다. LLDP 관리 주소·system name으로 poll 대상을 자동 발견하지 않습니다. ARP/NDP neighbor, route/gateway, 주소, Nova inventory, exporter reachability, TCP·flow·trace는 독립된 근거이며 물리 링크로 합치지 않습니다.
- NIC rate는 같은 boot_id·interface 이름·MAC·ifindex, 양쪽 measured counters, 5–30초 간격과 감소하지 않는 counter에서만 계산합니다. 첫 표본·재부팅·reset·gap에서는 해당 rate가 `null`. History는 최대 60표본이며 configured retention 밖의 점은 제외합니다. 30초 초과 관측은 `stale`, 현재 rate는 null이고 원본 누적값/과거 history는 과거 증거로 남습니다.
- Peer probe는 운영자가 허용한 **source host→target host의 정확한 literal IP/port**로 TCP 연결만 시도합니다. `up`은 그 방향·포트의 연결 성공/latency, `down`은 refusal/timeout/unreachable, `unknown`은 source/local probe 실패·미측정·stale입니다. Payload·로그인·포트 scan은 없으며 역방향·다른 NIC·data plane 정상이나 물리 연결을 증명하지 않습니다.
- Trace는 호스트에서 허용한 destination으로 나가는 **outbound traceroute**만입니다. DNS/CIDR·arbitrary target·역방향 trace는 없습니다. 서버 allowlist와 observer의 local `--trace-target`가 모두 필요합니다. `source_interface`/`next_hop`은 실제 `ip -j route get` 결과입니다. `*` hop은 `{ip:null,rtt_ms:null}`로 남기며 그 hop을 장애 위치로 단정하지 않습니다. Target IP가 출력에 보이는 것만으로 도달 성공이 아닙니다. Completed command의 annotation 없는 timed target reply가 있어야 `reached=true`; 서버도 complete result의 마지막 hop IP·RTT를 대조합니다. Failed command/`!H`·`!X`/untimed reply는 도달 성공으로 표시하지 않습니다.

Reports는 현재 기준 30초 이내·미래 최대 5초의 timestamp만 허용하며 host별 최소 5초 간격입니다. Replay/out-of-order는 `409`, 빠른 보고는 `429 observation_rate_limited`; peer tuple과 timestamp/replay도 검증합니다. Job poll은 host별 최소 5초입니다. Trace는 host별 60초당 1회, 활성 queued/running job 1개만 허용합니다. Job은 90초 만료, 최대 16 hops·40초 command deadline, history 최대 20개입니다. `202 queued`는 접수이지 실행·완료·도달 성공이 아닙니다. 비활성은 `503 topology_disabled`, 미등록 observer는 `404 observer_not_configured`, target 거부는 `422 trace_target_not_allowed`, 활성 job 충돌은 `409 trace_already_active`, 제한은 `429 trace_rate_limited`, Redis 장애는 `503 topology_store_unavailable`입니다. 만료·재전송·회수된 target·시간 불일치 result는 거부하며 자동 재실행이나 우회 설치는 없습니다.

### 방향별 호스트 flow (`flows`)

Observer ingress는 선택적 `flows:{collector_id,captured_at,overflow,rows}`를 받습니다. Row는 `{source_host_id,target_host_id,interface,direction:ingress|egress,packets,bytes}`이고 packets/bytes는 **decimal uint64 문자열**입니다. 최대 1,024개 row, 고유 interface/direction/source/target tuple, 서로 다른 등록 호스트와 qualified physical NIC가 필요합니다. Egress는 인증된 source host, ingress는 인증된 target host 소유여야 합니다. 주소 등록은 호스트별 최대 32개 literal IPv4/IPv6이며 중복 소유·mapped IPv6 alias를 허용하지 않습니다. `overflow=true`는 `sources.flows=error`여야 하고 미지원 source는 counter를 보낼 수 없습니다.

| 공개 `flows[]` 필드 | 의미 |
|---|---|
| `id`, `source_host_id`, `target_host_id` | 안정된 observation identity와 실제 통신 방향 |
| `reporting_host_id`, `interface`, `direction` | 관측 호스트·NIC와 `ingress/egress` 관측 지점 |
| `captured_at`, `window_seconds` | epoch와 유효 counter 차분 구간(초), 미측정 구간은 null |
| `packets_per_second`, `bytes_per_second` | 그 지점의 pps/B/s 또는 null; 관측된 0은 0 |
| `state`, `measurement`, `reason` | `fresh/stale/unmeasured/error`, `linux_skb_header_counter`, nullable 사유 |

`reason`은 `first_sample/counter_reset/collector_reset/overflow/stale_sample/collector_error` 또는 null입니다. 같은 boot·collector ID·NIC 이름/ifIndex/MAC·physical 자격, 양쪽 measured/nonoverflow 표본, 5–30초 구간과 감소하지 않는 counter에서만 rate를 계산합니다. 정수 차분 뒤 안전한 범위에서만 float로 바꾸며 첫 표본·reset·수집 오류·overflow·stale에서 rate/window는 null입니다. Flow timestamp 위반은 `409 flow_observation_time_invalid`, 재전송·역순은 `409 flow_observation_replayed_or_out_of_order`, 등록/방향 소유권 위반은 `422 flow_host_not_allowed`입니다. Schema·physical 자격 위반도 `422`입니다.

이는 별도 BPF socket-filter collector가 등록 주소와 검토된 NIC에서 계수한 **Linux skb 헤더/길이 관측**입니다. GRO/GSO·VLAN offload·선택 관측 지점의 영향을 받으며 wire packet 수·NIC 전체 traffic·TCP probe 성공 횟수가 아닙니다. 화면은 방향별 fresh sender egress가 있으면 sender family, 없으면 fresh receiver ingress family를 우선하고, 둘 다 미측정이면 sender 존재 여부에 따라 남은 근거를 표시합니다. NIC별 row는 분리하고 양 끝 관측은 inspector에 보존하며 **sender+receiver·NIC·switch 값의 합계는 만들지 않습니다**. Controller 중심은 layout anchor일 뿐 transit 경로가 아닙니다.

### Switch fabric (`fabric`)

`fabric`은 `{state,generated_at,devices,ports,links,coverage}`이며 `state=unconfigured/available/partial/unavailable`, `coverage={description,last_observed_at,error}`입니다. 명시적 target만 별도 lifecycle에서 SNMPv3 authPriv GET/GETBULK로 수집합니다. Host flow/health store와 독립된 상태이므로 top-level `error`가 없어도 fabric이 unavailable일 수 있습니다. SNMP 대상 미설정이면 `unconfigured`이지만 qualified host LLDP의 수동 관측 장치·링크는 남을 수 있습니다. 이 경우 switch rate를 만들거나 LLDP 주소로 자동 poll하지 않습니다.

| 공개 필드 | 내용 |
|---|---|
| `devices[]` | `{id,name,chassis_id,state}`; state는 `fresh/stale/unmeasured/error` |
| `ports[]` identity | `{id,device_id,ifindex,name,physical}`; physical은 true/false/null |
| `ports[]` observation | `{captured_at,state,operstate,window_seconds,rx_packets_per_second,tx_packets_per_second,rx_bytes_per_second,tx_bytes_per_second,measurement,reason}` |
| `links[]` | `{id,source,target,captured_at,state,evidence,source_port_id,target_port_id}`; endpoint는 `{kind:host|switch,id,port}`, state는 `fresh/stale/unmeasured`, evidence는 `lldp`; 미해결 port ID는 null |

Port `measurement=snmp_if_mib`, `operstate=up/down/unknown`; reason은 flow와 같은 nullable 사유 집합입니다. IF-MIB/IF-X-MIB high-capacity octets와 완전한 unicast/multicast/broadcast packet counter의 연속 차분을 사용하고 uptime·engine boots·discontinuity·장치/port identity·freshness를 확인합니다. Table walk의 시작·종료 GET은 typed sysUpTime와 engine boots가 모두 유효하고 동일 boot임을 확인해야 하며 누락/잘못된 closing marker는 sample 전체를 거부합니다. sysUpTime의 정상32-bit wrap은 modulo delta와 실제 elapsed bound로 구분하고 reboot/discontinuity는 baseline을 끊습니다. 누락 component·첫 표본·reset·stale·오류·overflow는 해당 rate를 null로 남기며 host NIC 합계로 보충하지 않습니다. 화면의 RX/TX 화살표는 **양 끝의 switch port identity가 모두 physical로 확정된 링크에서 한 qualified switch port의 수신/송신 관측 지점**이고 양 끝 port를 합친 cable throughput이 아닙니다. 미해결·논리 switch endpoint의 LLDP 근거와 독립 port totals는 남지만 cable rate를 부여하지 않으며 port membership 선도 traffic이 아닙니다.

Configured device ID는 `switch:<target.id>`, port는 `switch:<target.id>:if:<ifindex>`, LLDP-only device는 canonical chassis hash의 `switch:lldp:<24 hex>`입니다. `coverage.error`는 쉼표로 구분한 코드 또는 null이며 `snmp_configuration_pending`, `snmp_store_unavailable`, `snmp_unmeasured`, `snmp_stale_sample`, `snmp_timeout`, `snmp_authentication`, `snmp_network_unreachable`, `snmp_unsupported`, `snmp_dependency_unavailable`, `snmp_collector_error`, `snmp_cardinality_exceeded`, `snmp_invalid_response`, `snmp_missing_counters`, `snmp_missing_lldp`, `snmp_missing_uptime`, `snmp_identity_mismatch`, `snmp_counter_overflow`, `snmp_duplicate_sample`을 구분합니다. 이들은 snapshot coverage이지 credential·raw SNMP 오류 문자열을 노출하는 HTTP 오류가 아닙니다.

단일 radial workspace는 flow/physical 기본 layer와 선택적 route/probe/trace layer, 동일 node/edge selection과 inspector를 사용합니다. Rate polling은 camera를 초기화하지 않고 resize·Fit만 다시 맞춥니다. Pointer/touch pan·pinch, keyboard Arrow pan·+/− zoom·Home/0 Fit, native evidence 목록의 선택을 제공합니다. Desktop 옆/tablet 아래 inspector와 mobile modal sheet의 닫기·재열기·focus 복귀는 [`DESIGN.md`](../../DESIGN.md#administrative-observation-surfaces)를 따릅니다.
---

## 트래픽 분석

UI: [트래픽 모니터링](/admin/monitoring/traffic).

| 메서드 | 경로 | 입력·응답 |
|---|---|---|
| `GET` | `/api/v1/admin/monitoring/traffic` | `require_admin`; `range=24h\|7d\|30d`(기본 `24h`), `source=backend\|frontend`(기본 `backend`), `origin=all\|internal\|external\|unknown\|legacy_unclassified`(기본 `all`); no-store snapshot |
| `POST` | `/api/v1/monitoring/traffic/events` | 별도 frontend writer bearer; 최대 **2 KiB**, event 시각 현재 ±120초; `{accepted:true}` |

Writer는 사용자/관리자 로그인 token이 아닌 독립 frontend ingest bearer입니다. 인증 뒤 streaming body를 제한하며 validation 응답에 IP/secret 입력을 되비추지 않습니다. 오류는 `404 "Traffic observation is disabled"`, `401 "Invalid traffic writer credential"`, `413 "Traffic event exceeds size limit"`, `422 "Invalid traffic observation"` 또는 `"Traffic observation outside freshness window"`, `503 "Traffic aggregation unavailable or capacity exceeded"`입니다. Read query enum 위반도 `422`입니다.

V2 event는 `{schema_version:2,id:UUID,at,status,route,peer_ip?,peer_verified?,forwarded_for?,pageview?,request_bytes?,response_bytes?,latency_ms,reporter_dropped_events?}`입니다. `peer_ip`는 원래 socket peer의 nullable 문자열(최대 64자), `peer_verified`는 strict boolean(기본 false), `forwarded_for`는 nullable XFF 문자열(최대 1,024자)이며 최종 client 주소를 사전 확정한 `client_ip` alias가 아닙니다. 주소·XFF 문법/신뢰 오류는 unknown reason으로 집계하고 유효한 주소로 보정하지 않습니다. `status` 100–599, route 최대 256자, 각 byte count 0–2^40 또는 null, finite latency 0–86400000 ms, reporter drop 0–1000000; 미정의 필드는 거부합니다.

Version 없는 `{id,at,status,route,client_ip?,...측정 필드}`는 명시적 legacy wire만 허용합니다. 이 `client_ip`는 신뢰하지 않고 무시하므로 새로 수용된 legacy event는 `legacy_unclassified`, country `XX`, identity 미확인입니다. Version 없는 v2 필드 혼합·다른 schema version은 `422`입니다. **Backend v2 ingest를 먼저 전환한 뒤 reporter v2를 전환**해야 하며 v2 reporter→구 backend는 호환되지 않습니다. 이는 일반 주소 호환 shim이 아니라 rolling-upgrade 경계입니다.

Snapshot은 `{state,source,origin,origins,range,retention_days,generated_at,coverage,totals,countries,routes,series}`입니다. `origins`는 `{internal,external,unknown,legacy_unclassified}` request count 또는 totals 미관측 시 null입니다. `countries[]`는 `{country,...metrics}`, `routes[]`는 `{route,origins,...metrics}`, `series[]`는 `{at,metrics}`입니다. `origin` filter는 totals·country·route·series·HLL·reason counts에 적용하고 선택되지 않은 origin count는 0입니다. `origins` 및 route별 origins의 합은 각 requests와 같습니다. Source별 Redis **UTC 시간 bucket**에서 요청 기간과 retention 중 짧은 범위(최대 30일)만 조회합니다. 두 source를 합쳐 고유 사용자/요청 수라고 주장하지 않습니다. `series[].at`은 bucket 시작 epoch, `metrics:null`은 미관측 bucket입니다.

V2 bucket은 기존 v1 key와 분리합니다. 과거 v1 bucket은 기존 국가/metric/HLL을 보존한 채 origin만 `legacy_unclassified`로 읽으며 `all` 또는 legacy filter에서만 포함합니다. 과거 raw IP가 없으므로 MMDB/CIDR 변경이나 새 writer로 과거를 재분류하지 않습니다. Unknown 과거 geo의 사유도 legacy로만 남기고 원래 원인을 추정하지 않습니다. 새로 수용된 legacy event와 과거 v1 HLL의 identity coverage는 다를 수 있습니다.

`totals` 및 country/route/hour metrics에는 `requests`, `success`(2xx/3xx), `errors`(4xx/5xx), `status_1xx`–`status_5xx`, `pageviews`, `unlocated`, `request_bytes`, `response_bytes`, 각각의 `*_bytes_known`, `latency_ms_total`, `latency_ms_max`, `unique_visitors`, `visitor_identity_known`가 있습니다. Byte coverage가 없으면 합계도 null이고 일부만 알려졌다면 알려진 합계 및 known count를 함께 봅니다. 이는 transport header/TLS/관측 밖 압축을 포함하는 wire bandwidth가 아닙니다. Latency 평균은 total/requests로 해석할 수 있으며 p95 같은 percentile은 수집하지 않습니다.

- 고유 방문자는 검증된 normalized 주소의 keyed HMAC을 Redis HyperLogLog에 넣은 **추정치(표준 오차 약 0.81%)**입니다. 사람이 아니며 NAT/공유 IP는 과소, IP 변경은 과대 집계됩니다. 기간 total은 선택 source/origin HLL union이며 country/route별 HLL은 없으므로 dimension의 `unique_visitors`는 null입니다. IP identity 미관측도 null입니다. 기존 legacy HLL은 당시 방식 그대로 유지합니다.
- 국가 조회는 `geoip_mmdb`의 운영자 제공 **DB-IP Country MMDB 전체 데이터**를 mmap으로 읽는 IPv4/IPv6 offline lookup입니다. Runtime 외부 GeoIP 호출·download·CIDR CSV fallback은 없습니다. 비global·multicast·미등록 주소, 미검증 provenance, 미설정/실패 DB는 `XX`(위치 미확인)이며 `coverage.geo_source=unconfigured/offline_mmdb/unavailable`입니다. `geo_provider`, `geo_version`(MMDB build UTC 날짜), `geo_attribution`은 현재 열린 DB metadata 또는 null입니다. Lite는 DB-IP/CC BY 4.0 attribution을 표시합니다. 이 metadata는 **과거 bucket별 dataset attribution이 아니며**, DB 교체는 새 event에만 영향을 줍니다.
- `coverage.site_country`는 서비스 위치 설정 문자열 또는 미설정 `null`입니다. 지도에서는 **client 국가→서비스 위치의 논리적 access flow**에만 사용하며 실제 packet 경로·물리 링크·host trace를 뜻하지 않습니다. `XX`는 서비스 위치로 사용할 수 없습니다.
- Backend는 이 앱의 HTTP ASGI 요청만 관측하고 analytics ingest/read·WebSocket·앱 밖 요청을 제외합니다. Health/host-observation 요청은 버리지 않고 같은 주소 provenance와 cluster CIDR 정책으로 분류합니다. Frontend는 SvelteKit server 요청만 관측하며 성공한 HTML GET이 SSR pageview입니다. SPA client-only 이동, CDN/static bypass, edge traffic은 수집하지 않습니다. Frontend request bytes는 미수집이고 response는 실제 소비된 stream에서만 측정합니다.
- Origin은 검증된 원본 주소가 승인된 `cluster_cidrs`에 있으면 `internal`, 그 밖의 global nonmulticast이면 `external`, 비global noncluster·provenance 미확인은 `unknown`입니다. Private/VPN/예약 주소 자체·URL/route·User-Agent·status·외부 ingress 경유 여부로 internal/external을 정하지 않습니다. 국가 일치 여부와 origin은 독립적이므로 internal도 `XX`일 수 있고 external도 DB 미일치일 수 있습니다.
- Analytics만의 `backend_trusted_proxy_cidrs`와 `frontend_trusted_proxy_cidrs`는 서로 독립이며 인증·rate-limit의 `trusted_proxies` 또는 Uvicorn `FORWARDED_ALLOW_IPS`를 바꾸거나 대신하지 않습니다. Rewrite **이전** socket peer가 확인되고 그 peer가 해당 source의 proxy CIDR일 때만 XFF를 신뢰합니다. 최대 1,024자/16개 hop 전체를 먼저 검증하고 오른쪽부터 trusted proxy를 제거해 첫 nontrusted 주소를 고릅니다. Nonproxy peer의 header는 무시하며 malformed/missing/all-trusted chain은 unknown입니다. X-Real-IP fallback·뒤에서 두 번째 값을 고르는 구 규칙은 analytics에 사용하지 않습니다.
- Backend launcher는 `app.middleware.traffic_address:create_app --factory --no-proxy-headers`로 outer wrapper가 원래 peer를 private ASGI extension에 보존한 뒤 기존 auth용 proxy rewrite를 적용합니다. Extension 없는 backend는 peer 미확인입니다. Frontend reporter는 **실제 adapter socket provenance를 확인한 뒤** `TRAFFIC_ANALYTICS_PEER_IS_SOCKET=true`이고 `ADDRESS_HEADER`가 없을 때만 `getClientAddress()`를 socket peer로 보냅니다. 그 외는 `peer_verified=false`입니다. 구 `TRAFFIC_ANALYTICS_TRUST_CLIENT_ADDRESS`·ADDRESS_HEADER/XFF_DEPTH 설정만으로 신뢰를 부여하지 않으며 reporter bearer가 end-user address 검증을 대신하지 않습니다.

`coverage`의 정확한 필드는 `description`, `geo_source`, `geo_provider`, `geo_version`, `geo_attribution`, `geo_unknown_reasons`, `origin_unknown_reasons`, `classified_requests`, `legacy_unclassified_requests`, `classification_policy`, `site_country`, `unique_method`, `dropped_events`, `reporter_dropped_events`, `observed_since`, `last_observed_at`입니다. Classified는 선택된 internal+external requests이고 legacy count도 선택 filter에 따르며 미관측이면 null입니다. `classification_policy`는 현재 정책/과거 재분류 불가 안내입니다. Drop 수와 observation timestamp는 **origin filter와 관계없는 source-wide coverage**입니다. Drop은 다음 accepted event에 실린 복구 관측과 현재 worker만 반영하며 종료 worker·끊긴 reporter의 모든 손실은 복원하지 못합니다.

| Reason count map | 허용 key(관측된 nonzero 사유만 반환) |
|---|---|
| `geo_unknown_reasons` | `address_unavailable`, `invalid_address`, `non_global`, `database_unconfigured`, `database_unavailable`, `range_missing`, `country_invalid`, `lookup_failed`, `peer_unverified`, `forwarded_missing`, `forwarded_invalid`, `forwarded_all_trusted`, `legacy_unclassified` |
| `origin_unknown_reasons` | `peer_unverified`, `address_unavailable`, `invalid_address`, `forwarded_missing`, `forwarded_invalid`, `forwarded_all_trusted`, `non_global_noncluster`, `legacy_unclassified` |

Reason은 개인정보 없는 집계 사유이며 IP별 drilldown이 아닙니다. `state=disabled/available/partial/unavailable`: 빈 store·선택 origin 미관측은 0이 아닌 `partial`, Redis 읽기 실패는 `unavailable`, known source drops·현재 worker drops·DB unavailable도 partial입니다. DB 미설정·미분류/위치 미확인 count 자체는 상태 실패로 바꾸지 않으므로 available이 모든 주소·국가의 완전한 관측을 뜻하지 않습니다.

원문 peer/client IP·XFF는 전송·메모리 내 provenance/origin/국가/HMAC 계산에만 사용하고 durable aggregate·public snapshot·analytics 로그에 보관하지 않습니다. Cookie, user agent, body, token, 실제 URL/query/동적 path ID도 저장하지 않고 고정 route category만 남깁니다. 중복 방지용 event UUID는 제한된 Redis dedupe table에 TTL 300초로 잠시 남으며 사용자/request drilldown 기능이 아닙니다. 집계는 bucket 시작 기준 만료하고 늦은 event가 보존기간을 늘리지 않습니다. Reporter는 최대 16 inflight·2초 deadline, 집계 writer는 250 ms deadline으로 bounded이며 관측 실패가 원래 응답/예외를 바꾸지 않습니다. 설정과 secret 주입은 [운영 설정](../deployment.md#트래픽-분석-설정)을 따르세요.

---

## 사용자 로그인 모니터링

UI: [로그인 모니터링](/admin/monitoring/logins).

| 메서드 | 경로 | Query·응답 |
|---|---|---|
| `GET` | `/api/v1/admin/monitoring/logins/users` | `limit` 기본/최대 100·최소 1, `marker` 최대 128자; `{items:[{id,name}],next_marker}` |
| `GET` | `/api/v1/admin/monitoring/logins/users/{user_id}` | user_id 1–64자, `window=24h\|7d\|30d` 기본 24h; 선택 사용자 history/session snapshot |

두 endpoint는 `require_admin`, no-store와 caller-scoped SDK connection을 사용합니다. Directory는 Keystone native pagination으로 요청 page만 소비하며 꽉 찬 page는 마지막 ID를 next_marker로 반환합니다. 선택 사용자를 native 조회로 확인하고 `403 login_monitoring_native_denied`, `404 login_monitoring_user_not_found`, 그 밖의 native 장애 `503 login_monitoring_directory_unavailable`를 반환합니다.

선택 사용자 응답은 `{user,window,as_of,from_at,observed_interval_seconds:300,history,sessions}`입니다. 두 데이터 원천은 **보존된 SQL ActivityLog**와 **현재 Redis session store**이며 Keystone 전체 로그인 감사·현재 온라인 상태를 대신하지 않습니다.

- `history`: 해당 사용자·기간의 최근 활동 최대 100개 `events`와 Afterglow auth/login row 최대 10000개로 `timeline`(UTC 시간 bucket), `hour_distribution`(UTC 0–23시), `login_successes`, `recorded_login_failures`를 만듭니다. Event allowlist는 `at`, `project_id`, `resource_type`, `action`, `status`, `auth_method`(`password/federated/null`)입니다. 최근 event는 로그인뿐 아니라 사용자 활동도 포함합니다. State는 `ready/partial/unavailable`; login row가 10000개를 넘으면 partial입니다. DB 미사용/실패에서는 수치를 null로 표시합니다. 현재 password/OIDC hook은 성공만 기록하므로 항상 `failure_history="not_collected"`; recorded 실패 0은 실제 실패가 없었다는 증거가 아닙니다.
- `sessions`: 정확한 user_id, blacklist, refresh 만료와 설정된 세션 timeout을 검사해 유효한 retained session만 반환합니다. 허용 필드는 `started_at`, `last_seen`, `expires_at`(refresh 만료와 session timeout 중 빠른 값), `refresh_expires_at`, `project_id`, `device_type`(`desktop/mobile/tablet/unknown/null`), `os`(`Windows/macOS/Linux/Android/iOS/null`), `auth_method`(`password/federated/null`), `observed_recently`입니다. JTI·token·fingerprint·IP·임의 session metadata는 제외합니다.
- Session state는 `ready/partial/unknown/unavailable`입니다. Secondary index가 없으면 세션 0개를 증명하지 못하므로 unknown, Redis 실패는 unavailable, index/row 수 불일치·잘못된 소유권/필수 metadata는 partial이고 `valid_count`/`observed_recent_count`를 null로 둡니다. 최근 300초의 유효한 last_seen만 `observed_recently=true`; 유효 token·recent activity는 실제 사용자가 현재 온라인이라는 증거가 아닙니다. 이 API는 세션 갱신·차단·삭제나 로그인 수집을 추가하지 않습니다.

---

## 이벤트 조사

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/api/v1/admin/events` | 모든 프로젝트의 활동·OpenStack 알림을 필터/커서로 조회 |
| `GET` | `/api/v1/admin/events/stats` | 현재 필터의 서비스·프로젝트·페이지·액션별 성공/실패 집계 |
| `GET` | `/api/v1/admin/events/{id}` | 실패 원인, actor, 대상과 요청/외부 이벤트 식별자 확인 |

필터, 수집 전제 및 기존 활동 API와의 차이는 [관리자 이벤트](events.md)를 참조하세요.

---

## 클러스터 개요·모니터링

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/overview` | 하이퍼바이저·인스턴스·vCPU/RAM/Disk 사용량·GPU 인스턴스 수 등 클러스터 개요 |
| `GET` | `/api/v1/admin/overview/domains` | 전체 native domain별 프로젝트 수·VM/vCPU/RAM/GPU·볼륨 수/GiB 집계 |
| `GET` | `/api/v1/admin/monitoring/summary` | 서비스 상태·리소스·알림을 종합한 모니터링 요약 |
| `GET` | `/api/v1/admin/notifications` | 관리자 알림(이상 상태·경고) 목록 |
| `GET` | `/api/v1/admin/topology` | 전체 프로젝트 네트워크/라우터/인스턴스 토폴로지 (`AdminTopologyData`). 사용자용 `GET /api/v1/networks/topology` 응답에 더해 `networks[]`에 `provider_network_type` / `provider_segmentation_id` / `provider_physical_network`를 추가한다 (관리자 응답 전용). `instances[].is_database`는 Trove 전체 프로젝트 목록(`all_projects=True`)의 fixed IP 매칭으로 채우며 Trove 미배포 시 모두 `false` |
| `GET` | `/api/v1/admin/timeseries/{resource_type}` | 리소스 유형별 시계열 스냅샷 (1시간 간격) |
| `GET` | `/api/v1/admin/version` | 백엔드/배포 버전 정보 |

관리자 토폴로지 `networks[]`는 fresh native 소유권의 `project_name`, `domain_id`, `domain_name`, `owner_status`(`known/deleted_project/deleted_domain/unknown_owner`)도 반환합니다. 도메인·프로젝트 조건은 네트워크 소유권으로 적용하며 공유 사용자의 도메인을 소유자로 대체하지 않습니다. Directory 실패는503입니다. 관리자 캔버스/레인은 domain UUID별 상위 그룹을 만들고 동일한 표시 이름에는 UUID를 함께 표시하지만, 그 상자는 통신 허용·연결을 의미하지 않습니다. 실제 연결선과 소비자 응답은 유지됩니다. Swift 전체 inventory는 별도 `GET /api/v1/admin/object-storage`를 사용합니다([Object Storage API](object-storage.md#get-apiv1adminobject-storage)).


`GET /monitoring/summary`는 기존 inventory·quota allocation과 별도로 `telemetry: {source, status, resources, truncated, error}`를 반환합니다. 각 resource는 공개 whitelist의 `id`, `type`, `name`, `metrics`만 포함하고 metric은 `series[{ts,value}]`, `unit`, `status`, 안전한 `error`를 갖습니다. 현재 caller의 Gnocchi 정책에 허용된 `nova_compute` CPU percent/frequency, `ipmi` 센서 및 `volume_provider`/`volume_provider_pool` 용량을 읽습니다. 이 목록은 완전한 cloud inventory가 아니며 Nova 할당량·호스트 도달성을 실측 이용률로 바꾸지 않습니다. Native 데이터는 기존 공통 inventory cache에 넣지 않고 매 요청 현재 시스템 관리자 권한과 native policy를 확인하며 응답은 no-store입니다. UI는 최대 12 resource × 12 meter와 기록 시각·단위·부분 coverage를 표시하고 이력은 펼칠 때 렌더합니다. 미수집을 0으로 채우지 않습니다.

관리자 개요는 프로젝트별 quota 표 대신 **도메인별 실제 할당 자원**을 표시합니다. `/overview/domains`는 native Keystone project→domain UUID join으로 전체 Nova/Cinder inventory를 합산하며 사용자 home·동일한 표시 이름으로 소유권을 추정하지 않습니다. 자원이 없는 native domain과 프로젝트도 집계 대상입니다. 각 row는 `domain_id`, `domain_name`, `project_ids`, `project_count`, `instances`, `vcpus`, `ram_mb`, `gpu_instances`, `volumes`, `volume_gb`, `attached_volumes/attached_gb`, `available_volumes/available_gb`, `owner_status`를 반환합니다. Nova의 embedded CPU/RAM 수치가 없으면 해당 합계는 null이며 확인된0과 다릅니다. 삭제된 프로젝트·도메인과 owner 누락은 `deleted_project`·`deleted_domain`·`unknown_owner`로 구분합니다. Directory 조회 장애는503이지 빈 합계가 아닙니다. 도메인 행에서 인스턴스/볼륨 목록을 열면 `domain_id` query를 독립 관측 picker에 적용하고 로그인 workspace는 바꾸지 않습니다. 퇴역한 `/overview/projects`는 제공하지 않습니다.

`GET /overview` 응답 예시:

```json
{
  "hypervisor_count": 5,
  "running_vms": 42,
  "gpu_instances": 3,
  "instance_stats": {"total": 42, "active": 38, "shutoff": 2, "error": 1, "other": 1},
  "vcpus": {"total": 160, "allowed": 320, "used": 85},
  "ram_gb": {"total": 512.0, "used": 256.5},
  "disk_gb": {"total": 10000, "used": 3500},
  "containers_count": 0,
  "file_storage_count": 12
}
```

**timeseries 제한**: `resource_type`은 `instances` / `volumes` / `file_storage` / `networks` 중 하나여야 하며, 그 외 값은 `400`. `range` (query)는 `1d` / `2d` / `7d` / `30d` (기본 `7d`).

---

## 하이퍼바이저·컴퓨트 호스트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/hypervisors` | 컴퓨트 하이퍼바이저 상세 목록(호스트별 vCPU/RAM/디스크/VM 수) |
| `GET` | `/api/v1/admin/hypervisors/{hypervisor_id}` | 특정 하이퍼바이저 상세 |
| `GET` | `/api/v1/admin/compute-hosts` | 마이그레이션 대상 선택용 컴퓨트 호스트 목록 |
| `PUT` | `/api/v1/admin/hypervisors/{hypervisor_id}/service` | 연결 상태와 별개로 해당 호스트의 `nova-compute` 스케줄링 변경. 본문 `{ "status": "enabled" }` 또는 `{ "status": "disabled", "reason": "점검 사유" }`; 비활성화 사유 필수 |
| `POST` | `/api/v1/admin/hypervisors/{hypervisor_id}/relocate` | `up/disabled`일 때 `{ "mode": "migrate" }`로 전체 인스턴스 이동 요청, `down`일 때 원본 전원 차단·펜싱 확인 후 `{ "mode": "evacuate", "fenced": true }`로 대피 요청. 서버가 호스트 상태·소속을 재확인하고 모든 페이지를 읽으며 인스턴스별 `requested`/`failed`/`skipped` 결과를 반환 |
| `POST` | `/api/v1/admin/hypervisors/{hypervisor_id}/removal-check` | 캐시를 우회해 호스트 메타데이터·현재/보존 서버·이주·Placement tree를 점검. `{report, review_token, expires_at}`를 반환하고 모든 조건을 통과한 보고서에만 5분·1회용 승인 발급 |
| `POST` | `/api/v1/admin/hypervisors/{hypervisor_id}/remove` | 보고서 검토·실제 `nova-compute` 중지 확인·정확한 호스트명·제거 사유를 받은 뒤 최신 상태를 재점검하고 검증한 Nova compute service 등록만 삭제. 삭제 접수와 검증 완료를 구분 |

`state`(`up/down`)는 호스트 생존 상태, `status`(`enabled/disabled`)는 새 인스턴스 스케줄링 허용 여부로 독립입니다. 비활성화는 기존 인스턴스를 자동으로 이동시키지 않습니다. 전체 이동은 `ACTIVE`의 live migration과 `SHUTOFF`의 cold migration을 별도로 요청하고, 다른 상태는 이유와 함께 건너뜁니다. `down`만으로 호스트가 펜싱되었다고 판단할 수 없으므로, 대피 전 운영자가 원본의 전원 차단·격리를 반드시 확인해야 합니다. API의 `requested`는 Nova가 비동기 작업을 접수했다는 뜻이며 **이동 완료·복구 성공이 아닙니다**. 개별 VM의 상태와 목적지, cold migration의 `VERIFY_RESIZE` 확정 여부를 후속 확인하세요.

하이퍼바이저 상세의 `servers[]`는 각 VM의 `domain_id/domain_name`, `project_id/project_name`, `flavor_id/flavor_name`과 기존 `flavor`를 제공합니다. UI는 **도메인 - 프로젝트 - Flavor**로 표시하고 전체 UUID는 상세에서 확인할 수 있습니다. Native 소유 metadata가 없는 경우 확인 불가/삭제 상태를 표시하며 사용자 home이나 이름으로 보완하지 않습니다.

### 호스트 메타데이터 검토와 등록 제거

시스템 관리자 전용 기능입니다. 먼저 운영자가 해당 장비의 **실제 `nova-compute` 프로세스를 중지하고 계속 중지 상태로 유지**해야 합니다. 이 확인은 운영자의 승인 진술이며 Afterglow가 SSH·전원 제어로 수행하거나 증명하지 않습니다. `down`과 `forced_down`은 물리 종료 증거가 아닙니다. Nova 공식 [compute service 삭제 계약](https://docs.openstack.org/api-ref/compute/#delete-compute-service)에 따라 중지하지 않으면 compute node 등록이 다시 생길 수 있습니다. 물리 장비·다른 OpenStack 서비스·VM·스토리지는 삭제하지 않습니다.

1. 호스트 상세에서 **제거 점검 새로고침**을 선택합니다. 보고서는 정확한 hypervisor/service UUID 매핑과 단일 compute node, 양쪽 `disabled/down`, `forced_down=false`, 유효한 서비스 갱신 시각, 전체 프로젝트의 현재 서버·soft-deleted 서버, 보존 삭제 서버·이주 이력, Placement root와 모든 child provider의 consumer/resource 할당을 보여줍니다.
2. 실행 중 VM 수만 0인 것으로 충분하지 않습니다. `SHUTOFF` 등 모든 현재 서버와 soft-deleted 서버, 미완료 이주(`finished`/`VERIFY_RESIZE` 포함), GPU child를 포함한 Placement 할당이 있으면 차단합니다. 필수 조회·필드·전체 페이지·provider 매핑을 확인하지 못하면 `unknown`이며 승인 token을 발급하지 않습니다. 호스트의 정상 메모리 overhead가 0일 필요는 없습니다.
3. `service.updated_at`은 서비스 갱신/마지막 통신의 참고 값이며 실제 ping 시각은 아닙니다. Uptime은 정보이지 제거 허용 조건이 아닙니다. 실제 성공 관측만 Redis에 cloud/hypervisor/service별 30일 보관하고, 현재 조회가 실패하면 `source=last_observed`와 `observed_at`을 명시합니다. 이전 관측도 없으면 `unavailable`입니다. 과거 uptime으로 현재 생존·프로세스 중지를 추정하지 않습니다.
4. 보존 이력은 불완전합니다. 이미 정리된 서버·이력 및 Nova가 숨기는 cross-cell migration copies는 볼 수 없으며 빈 이력은 미사용 호스트라는 증거가 아닙니다. Migration completeness는 compute 2.58의 unpaged host-filtered 응답으로 확인하고 2.59의 UUID 페이지 조회와 대조합니다. Hidden 기록만 있는 중간 페이지에서 2.59 응답이 비더라도 뒤의 미완료 이주를 놓치지 않습니다. 한쪽 compute가 명시적 `null`인 완료된 실패 이력은 다른 쪽이 호스트와 정확히 일치하면 그대로 표시하며, 누락된 key·잘못된 값·모순된 응답은 `unknown`입니다. UUID가 없는 보존 기록은 ID와 UUID 미제공을 표시합니다.
5. 메타데이터 검토와 실제 프로세스 중지 checkbox, **정확한 호스트명** 및 공백이 아닌 제거 사유를 입력합니다. 요청 본문은 다음과 같습니다.

```json
{
  "review_token": "<removal-check에서 받은 1회용 token>",
  "confirm_hostname": "compute-host-name",
  "reason": "인스턴스 이동 및 실제 nova-compute 중지 후 장비 퇴역",
  "reviewed_metadata": true,
  "compute_stopped": true
}
```

승인은 사용자·프로젝트·cloud endpoint·hypervisor·service와 검토 fingerprint에 묶입니다. 제거 요청 시 token을 원자적으로 소비하고 호스트 작업 잠금 아래 다시 Nova/Placement를 조회합니다. 메타데이터 변경·만료·잘못된 호스트·차단 조건은 `409`, 승인/사유 누락은 `422`, coordination 불가 시 `503`이며 잠금 없는 삭제로 우회하지 않습니다. 승인 실패 후에도 token은 재사용하지 말고 새 점검·승인을 수행하세요. UI는 새 점검·수동 새로고침·호스트/프로젝트 변경·관련 상태 변경·만료·요청 실패에서 승인 입력을 초기화합니다. 시간/uptime 관측만 달라지면 검토 내용을 변경한 것으로 취급하지 않습니다.

Nova `DELETE /os-services/{service_uuid}`의 `204`는 접수입니다. 이후 service와 대체 등록, hypervisor, 검토한 Placement root/child provider의 부재 및 aggregate membership 제거를 별도로 조회합니다. 모두 확인한 `{status:"removed", verified:true}`만 UI가 완료로 표시하고 패널을 닫아 목록을 갱신합니다. 잔여 등록 또는 검증 실패는 `{status:"removal_unverified", verified:false, checks:[...]}`이며 보고서·차단 사유를 보존합니다. Nova가 거부하면 `409` 또는 `502`입니다. `forced_down` 설정, Placement 수동 삭제, 강제 workload 삭제는 하지 않습니다.

스케줄링·전체 호스트 이주도 같은 host lock을 사용합니다. 취소된 HTTP 요청의 SDK thread가 끝나기 전에 잠금을 해제하지 않으며, 잠금을 잃은 이후 이주 요청은 건너뜁니다. 점검·제거 감사 로그에는 actor·대상·사유·검토/최신 check·검증 결과를 남기고 review token은 남기지 않습니다. 삭제 시도 뒤 관련 호스트 목록·모니터링·개요·서비스·GPU cache를 무효화합니다.

`removal_unverified`처럼 HTTP 200으로 반환하는 비검증 결과도 감사 status는 `failed`입니다. 자동 middleware는 endpoint의 terminal 실패 이력을 2xx 기반 성공으로 덮어쓰거나 중복 추가하지 않으며, 명시적 terminal 기록이 없는 4xx/5xx와 예외는 계속 자동 기록합니다.

![하이퍼바이저 목록](../../assets/admin-hv-list.png)
*호스트별 VM 수, vCPU 사용률, RAM 사용량, 로컬 디스크 현황을 테이블로 일괄 조회*

---

## 전체 리소스 조회 (all-*)

전체 프로젝트를 가로지르는 조회 엔드포인트입니다. 아래 모든 `all-*` 목록은 선택적인 non-empty `domain_id`와 `project_id`를 **독립적인 AND 조건**으로 받습니다. 생략하면 전체 범위이며 도메인만 지정하면 그 도메인 소유 프로젝트의 자원을 조회합니다. 두 조건의 교집합이 없으면 빈 결과입니다. `all-instances` / `all-volumes` / `all-ports`의 `limit`+`marker`는 소유 범위를 제한한 뒤 적용합니다. 다른 범위의 marker는400 `inventory_marker_outside_scope`입니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/all-instances` | 도메인·프로젝트별 인스턴스 목록 (페이지네이션) |
| `GET` | `/api/v1/admin/all-volumes` | 도메인·프로젝트별 볼륨 목록 (페이지네이션) |
| `GET` | `/api/v1/admin/all-containers` | 전체 Zun 컨테이너 목록 (Zun 활성화 시) |
| `GET` | `/api/v1/admin/all-file-storages` | 전체 Manila 파일 스토리지 목록 (Manila 활성화 시) |
| `GET` | `/api/v1/admin/all-networks` | 전체 네트워크 목록 |
| `GET` | `/api/v1/admin/all-subnets` | 서브넷 목록; 관리자 네트워크 화면의 서브넷 목록 진입점과 연결 |
| `GET` | `/api/v1/admin/all-loadbalancers` | 전체 로드밸런서 목록 (Octavia 활성화 시) |
| `GET` | `/api/v1/admin/all-floating-ips` | 전체 Floating IP 목록 |
| `GET` | `/api/v1/admin/all-routers` | 전체 라우터 목록 |
| `GET` | `/api/v1/admin/all-ports` | 전체 포트 목록 |

같은 조건은 `/admin/file-storage`, `/admin/topology`, `/admin/images`(이미지 `owner`), `/admin/instances/health`, `/admin/volumes/status-summary`, `/admin/overview/domains`, `/admin/key-manager/project-quotas`, `/admin/events` 및 `/admin/events/stats`에도 적용됩니다. Trove는 명시적인 `/admin/database-instances`, Swift는 `/object-storage?all_projects=true`를 사용하고 매번 fresh 관리자 권한을 확인합니다. 소비자 Trove 목록의 이전 `all_projects` query는403이며 사용자 소유권 계약은 유지합니다.

Swift의 all-project fan-out 중 한 프로젝트의 인증/조회가 실패하면503 `object_storage_inventory_unavailable`로 반환하며 나머지만 성공한 부분 목록으로 보고하지 않습니다. 도메인/프로젝트 조건은 fan-out 대상 프로젝트를 먼저 제한합니다.

도메인을 지정하면 fresh system-admin guard를 통과한 configured provider 연결로 native 도메인과 소유 프로젝트 UUID를 새로 확인한 후 complete inventory를 제한합니다. 이름이 같은 프로젝트를 합치지 않으며 없는 도메인은404, 디렉터리 장애·불명확한 metadata는503입니다. 전역 inventory cache 재사용보다 directory 확인이 먼저이며 scoped 결과를 전역 cache에 저장하지 않습니다. Nova/Zun/Trove/Manila 및 Barbican project quota는 native 페이지를 끝까지 읽고 자원에 도메인이 직접 붙어 있다고 가정하지 않습니다.

Interactive 관리자의 기본 workspace도 Personal/member입니다. **Nova2025.2 all-tenants server·hypervisor·flavor-access의 scope는 project**이므로 관리자 경로 전체를 system token으로 바꾸지 않습니다. Provider inventory·selected-domain resource directory·quota·Flavor CRUD/ACL은 명시적 `get_admin_os_conn`에서 fresh native system-admin caller guard 뒤 기존 configured 고정 admin project/service credential로 실행합니다. 인증 결과의 project scope·admin role·SDK native is_admin_project 의미를 확인하며, Keystone이 legacy marker를 생략하는 경우 SDK 기본 true를 존중합니다. 명시 false/null/non-boolean, 잘못된 scope 또는 unavailable executor는503이고 다른 scope/계정으로 재시도하지 않습니다. `_afterglow_project_id`는 caller logical workspace, `_afterglow_authenticated_project_id`는 실제 executor project입니다. 사람의 Personal admin grant·기존 native grant·원 로그인 증명·header workspace는 변경하지 않습니다. Consumer, credential 관리/발급과 Aodh/Gnocchi telemetry는 caller-bound `get_os_conn`·native 정책을 유지합니다. 이는 caller impersonation이 아니라 검증된 system admin만 쓸 수 있는 명시적 configured provider 실행이며 권한 없는 caller는 executor 인증 전에 거부됩니다.

Manila의 `/v2/{project}` URL prefix도 논리 Personal이 아닌 실제 인증 executor project를 사용합니다. Catalog가 이미 executor project를 포함하면 logical ID를 중복해서 붙이지 않습니다. 별도 quota resource의 target project는 그대로 유지하며 native transport project가 없으면 송신 전에 거부합니다.

#### 관리자 상세 transport

관리자 사용자·프로젝트·그룹·역할의 디렉터리 및 `_selected_objects` domain/object 검증은 모두 같은 검증된 `get_admin_os_conn`을 사용합니다. 사람의 Personal member token으로 native 디렉터리를 읽지 않으며, domain mismatch·native ID 대체·권위 철회는 계속 거부합니다. Monitoring SG 생성에는 대상 `project_id`를 native group/rule 요청에 명시하므로 executor project에 잘못 생성하지 않습니다.

| 경로 (`/api/v1/admin` 기준) | 계약 |
| --- | --- |
| `GET /instances/{id}` 및 `/interfaces`, `/volumes`, `/available-volumes`, `/security-groups`, `/floating-ips`, `/networks`, `/owner` | 실제 Nova owner와 port/volume/SG/FIP 연결을 native metadata로 대조합니다. Browser project hint는 권한 근거가 아닙니다. |
| `GET /instances/{id}/console`, `/log`, `/resize-flavors`, `/admin-password/precheck` | 기존 상세 기능을 관리자 경로로 복구합니다. `/instances/health`는 dynamic ID보다 먼저 등록합니다. |
| `GET /instances/{id}/metrics-batch`, `/metrics-summary` | 서버 식별은 executor, Gnocchi credential은 caller-native를 유지하며 오류에도 no-store입니다. |
| `GET /images/{id}` 및 `GET/POST /images/{id}/members`, `DELETE /images/{id}/members/{member}` | exact native image/owner 및 member/image 연결을 검증합니다. UI의 상세·공개 범위·삭제·properties도 관리자 URL을 사용하고 삭제 후 모든 프로젝트 이미지 목록 cache를 무효화합니다. |
| `GET /file-storage/{id}`, `/access-rules` | canonical share owner를 먼저 검증하고 exact access-rule share ID를 재확인합니다. |
| `GET /loadbalancers/{id}` 및 `/listeners`, `/pools`, `/pools/{pool}/members`, `/status` | LB owner와 모든 child/부모 연결을 확인합니다. SDK Pool/Listener의 다른 native field 이름을 구분합니다. |
| `GET /database-instances` 및 `/{id}`, `/{id}/databases`, `/{id}/users`, `/{id}/backups` | Trove management parent tenant_id와 parent URI/backup instance_id를 검증하고 next-link marker만 읽습니다. |

인스턴스 상세의 기존 lifecycle·비밀번호·volume/interface·SG/FIP·storage 연결 작업도 exact native parent/child와 fresh 관리자 경계 아래 명시적 관리자 경로를 사용하며 성공·실패의 actor와 native target project를 구분해 기록합니다. Fixed executor로 target 소유를 보장할 수 없는 새 볼륨 생성은 관리자 상세에서 숨기며 caller-bound block-ledger 삭제는 native mutation 전에409입니다. LB/DB/파일 스토리지의 기존 일반 mutation은 실제 부모가 현재 caller project 소유일 때만 노출합니다. Palimpsest foreign-private export와 K3s 서비스 credential을 executor로 승격하지 않습니다.

관리자 인스턴스 storage 접근 허용 및 connection-info와 관리자 share access-rule 목록 응답에는 `secret`/`access_key`를 포함하지 않습니다. Native 규칙의 상태·대상·내보내기 위치만 보여주며, CephX key의 기존 caller-owned 명시 조회 계약을 관리자 executor로 확대하지 않습니다.

관리자 화면의 공용 도메인→프로젝트 picker는 사용자 header의 active workspace와 독립적입니다. 도메인 변경은 선택 프로젝트가 새 도메인에 없으면 해제하고 목록 page/marker·선택·열린 상세를 초기화합니다. 이전 scope/auth 수명의 늦은 조회·mutation 피드백은 새 화면에 게시하지 않습니다. Quota와 flavor 접근 대상, 포트 생성·볼륨 이관의 대상 프로젝트 선택도 같은 디렉터리 조건을 사용하되 **관측 필터를 mutation 대상 허용 목록으로 오용하지 않습니다**. Shared/external network 등 생성 옵션은 원래 native 가용 범위를 유지합니다. 공지 수신 도메인의 프로젝트 목록도 해당 도메인으로 제한합니다.

`all-instances`는 모든 scope에서 complete Nova inventory에 `domain_id/project_id/host/status/name`을 AND로 적용한 뒤 native UUID 오름차순으로 marker page를 자릅니다. `name`은 이름 또는 전체 ID의 literal 부분 검색입니다. `all-volumes`도 complete Cinder inventory에 동일한 소유 scope와 `status`, `name`(이름/ID), `volume_type`, `min_size`, `max_size`(GiB 정수)를 적용한 뒤 같은 방식으로 페이지를 만듭니다. `min_size > max_size`는422입니다. 두 row 형식 모두 native 소유 `domain_id/domain_name/project_name/owner_status`를 포함합니다. URL의 domain/project query는 공용 관측 picker와 동기화되며 filter 변경은 열린 상세·선택·marker도 초기화합니다.

사용자·프로젝트·그룹·credential·chat quota의 기존 **필수 identity-domain** 경계는 유지합니다. 이 도메인은 프로젝트 소유 도메인과 다른 의미이며 검증된 사용자의 account-wide quota 상세를 임의의 project-domain으로 잘라 표시하지 않습니다. 글로벌 설정·물리 인프라·catalog 기록에 의미 없는 도메인 필터를 추가하지 않습니다.

저장된 `/admin/timeseries/*`는 프로젝트 귀속 없는 cluster 집계입니다. scoped 요청은422로 거부하고 scoped UI는 명시적 안내와 함께 해당 차트를 숨깁니다. Scoped topology도 전역 과거 traffic 조회를 생략하며 그래프 자체만 소유 범위로 제한합니다. Lumen 통계는 BFF query 전달뿐 아니라 native Lumen의 네 통계 API에서 project-domain UUID 교집합을 SQL 집계·paging **전에** 적용해야 합니다. 사용자/대화 수는 도메인 전체에서 distinct 집계하며 프로젝트별 숫자를 더하지 않습니다. Native Lumen 변경은 별도 dev worktree의 source 변경이며 운영 배포 증거가 아닙니다.

`GET /all-instances` 응답 예시:

```json
{
  "items": [
    {"id": "uuid", "name": "vm", "status": "ACTIVE", "project_id": "uuid",
     "user_id": "uuid", "flavor": "m1.small", "host": "compute01",
     "created_at": "2024-01-01T00:00:00Z", "fault": null}
  ],
  "next_marker": "uuid-or-null",
  "count": 20
}
```

---

## VM 마이그레이션·복구

인스턴스를 다른 호스트로 이동하거나 상태 전이/복구를 수행하는 **파괴적·상태전이** 엔드포인트입니다. 대상 인스턴스의 현재 상태가 전제 조건을 만족해야 하며(예: resize는 `VERIFY_RESIZE`를 거쳐 confirm/revert 필요), 진행 중 작업은 되돌리기 어려우므로 대상 검증이 필수입니다.

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `POST` | `/api/v1/admin/instances/{server_id}/live-migrate` | 라이브 마이그레이션 시작 | `host` (선택), `block_migration` (선택) |
| `POST` | `/api/v1/admin/instances/{server_id}/live-migrate/abort` | 진행 중 라이브 마이그레이션 중단 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/live-migrate/force-complete` | 라이브 마이그레이션 강제 완료 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/cold-migrate` | 콜드 마이그레이션 (`host` 지정 시 해당 호스트로) | `host` (선택) |
| `POST` | `/api/v1/admin/instances/{server_id}/evacuate` | 다운된 호스트에서 인스턴스 대피 | `host` (선택) |
| `GET` | `/api/v1/admin/instances/{server_id}/migration-status` | 마이그레이션 진행 상태 조회 | - |
| `PUT` | `/api/v1/admin/instances/{server_id}/name` | 전원 상태와 무관한 표시 이름 변경; caller 연결·fresh admin·실제 target owner 확인 | `name` (1–63자 정규화) |
| `POST` | `/api/v1/admin/instances/{server_id}/resize` | 인스턴스 리사이즈 시작 (`VERIFY_RESIZE`로 전이) | `new_flavor` |
| `POST` | `/api/v1/admin/instances/{server_id}/confirm-resize` | 리사이즈 확정 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/revert-resize` | 리사이즈 되돌리기 | - |
| `GET` | `/api/v1/admin/instances/{server_id}/recovery-analysis` | 오류/멈춤 인스턴스 복구 분석 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/recover` | 분석 결과 기반 인스턴스 복구 수행 | - |
| `GET` | `/api/v1/admin/instances/health` | 전체 인스턴스 헬스 스냅샷 | - |
| `POST` | `/api/v1/admin/instances/bulk-action` | 다수 인스턴스 일괄 제어 | `instance_ids[]`, `action`, `snapshot_name` (선택) |

**bulk-action 제한**: `action`은 시작/정지/재부팅/스냅샷 등 허용된 값이어야 하며, 각 인스턴스별 결과가 개별 집계됩니다. 일부 실패해도 나머지는 계속 진행됩니다.

이름 변경은 [공용 인스턴스 이름 변경 계약](instances.md#put-apiv1instancesinstance_idname)을 따릅니다. Native name-only update 뒤 ID·이름·소유 프로젝트를 재조회하여 일치한 경우만 성공하며 guest hostname·전원 상태는 바꾸지 않습니다. 사용자 경로의 관리자 소유권 우회를 허용하는 대신 이 명시적 관리자 경로를 사용합니다. 기존 관리자·사용자 크기 변경 화면은 `SHUTOFF`에서만 노출되며 이 작업으로 변경하지 않습니다.

### 관리자 인스턴스 생성 (대리 프로비저닝)

관리자가 특정 프로젝트를 대신하여 인스턴스를 생성할 때 사용하는 헬퍼입니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/instances/networks-for-project` | 대상 프로젝트에서 선택 가능한 네트워크 |
| `GET` | `/api/v1/admin/instances/security-groups-for-project` | 대상 프로젝트의 보안 그룹 |
| `GET` | `/api/v1/admin/instances/volumes-for-project` | 대상 프로젝트의 볼륨 |
| `POST` | `/api/v1/admin/instances/async` | 대상 프로젝트에 인스턴스 비동기 생성 |

---

## 볼륨 관리

![전체 볼륨 관리](../../assets/admin-volume.png)
*전체 프로젝트의 볼륨을 시계열 차트와 함께 일괄 조회 — 양수 상태만 노출하는 상태·프로젝트 필터, 현재 page 선택, 확인 기반 부분 성공 일괄 삭제, 단건 수정·삭제 지원*

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/volumes/status-summary` | 전체 선택 scope의 상태별 개수·도메인별 개수/GiB 및 상세 필터 합계 | - |
| `GET` | `/api/v1/admin/volumes/{volume_id}` | 볼륨 상세 조회 | - |
| `PATCH` | `/api/v1/admin/volumes/{volume_id}` | 이름/설명 수정 | `name`, `description` (모두 선택) |
| `DELETE` | `/api/v1/admin/volumes/{volume_id}` | 볼륨 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/volumes/bulk-delete` | 최대 50개 볼륨 일괄 삭제, ID별 성공/실패 반환 | `volume_ids` (중복 없는 1~50개) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/force-delete` | 강제 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/extend` | 용량 확장 | `new_size` (현재보다 커야 함) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/reset-status` | 상태 강제 초기화 | `status` (기본 `available`) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/transfer` | native 대기 전송 생성·once-only ID/키 발급 | 선택적 `{name}`, `201` |
| `POST` | `/api/v1/admin/volumes/transfer/{transfer_id}/accept` | 실제 대상 프로젝트 자격으로 수신 | `{auth_key,target_domain_id,target_project_id}` |
| `GET` | `/api/v1/admin/volumes/{volume_id}/transfers` | 정확한 볼륨의 대기 ID 복구(키 없음) | native all_tenants 목록과 볼륨 상태 대조 |
| `DELETE` | `/api/v1/admin/volumes/transfer/{transfer_id}` | 관리자 명시 취소 | 자동 취소/재전송 없음 |
| `GET` | `/api/v1/admin/volumes/{volume_id}/delete-diagnostics` | 삭제 실패 원인 진단 | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/recover-delete` | 삭제 실패 복구 시도 | - |

**제한**: `force-delete` / `reset-status`는 Cinder의 정상 상태 전이를 우회하므로 데이터 정합성 위험이 있습니다. 오류 상태 복구 용도로만 사용하고, `extend`는 축소가 불가능합니다.

`bulk-delete`는 요청 순서대로 모든 ID를 처리하며 한 볼륨의 Cinder 거부가 다음 삭제를 중단하지 않습니다. 응답은 `{ "results": [{ "id": "...", "ok": true, "error": null }] }` 형태이고, 연결·상태 경쟁으로 삭제할 수 없는 볼륨은 `ok: false`와 항목별 오류 메시지를 반환합니다. 관리자 화면의 전체 선택은 현재 marker page에만 적용되며, 필터·page size·page·project scope 변경 시 초기화됩니다. 성공한 ID만 선택에서 제거하고 실패한 ID는 재확인을 위해 유지합니다. 상태 card와 선택지는 `status-summary`에서 count가 0보다 큰 상태만 표시합니다.

`status-summary`는 전체 선택 domain/project scope 기준 `total`, `total_gb`, `attached_count/attached_gb`, `available_count/available_gb`, `statuses`와 `domains`를 반환합니다. `domains`는 개요와 같은 native ownership 집계 형식이며 현재 marker page에 제한되지 않습니다. 상세 목록과 같은 `status/name/volume_type/min_size/max_size`를 보내면 `filtered_total/filtered_gb`로 그 결과도 별도 제공합니다. 상태·도메인 합계와 상세 검색 합계는 서로 다른 수치입니다. GiB는 Cinder에 할당된 논리 용량이지 게스트 파일시스템 사용량이나 backend 물리 점유량이 아닙니다.

새 filter/page/project 결과를 기다릴 때 이전 행을 즉시 지워 stale 선택을 막습니다. 확인 대기 중 결과 경계나 user/project가 바뀌면 요청을 보내지 않습니다. 같은 결과의 백그라운드 새로고침은 기존 행을 유지합니다. 항목별 실패는 고정된 공개 메시지이며 upstream 응답·접속 정보·credential을 응답이나 activity에 복제하지 않습니다.

두 endpoint는 요청 token으로 만든 **system-admin connection**을 그대로 사용하며 volume project로 재범위화하지 않습니다. Cinder message는 원인 추정용 evidence일 뿐 삭제 허용 근거가 아닙니다. 진단은 Cinder volume/attachment/snapshot/backup/clone/group·migration, Nova attachment, 선택적 Ceph RBD 상태를 각각 `present | absent | unknown`으로 반환합니다. 필수 check 하나라도 `unknown`이면 fail-closed로 `recovery_available=false`이고 복구는 `blocked`입니다. 401/403, timeout, SDK/CLI parse 오류를 `absent`로 바꾸지 않습니다.

RBD 검사가 활성화되면 `backend`에 `mode`, `classification`, pool, image name/id, size/order, parent를 반환합니다. Cinder의 404만으로 `already_deleted`를 확정하지 않습니다. RBD image/header/data/trash가 남아 있으면 `api_absent_backend_present`, 조회가 불완전하면 `backend_lookup_unknown`입니다. `rbd_id.volume-<uuid>`만 빠지고 directory·image id·size/order·parent·watcher/snapshot/child 상태가 일치할 때만 mapping을 복원합니다. 반대로 stale mapping 제거는 Cinder와 모든 backend artifact의 부재가 확인되고 mapping payload가 예상 image id와 정확히 같을 때만 실행합니다. Image data/header/trash 자체는 이 API가 삭제하지 않습니다.

복구 결과 `status` 계약:

- `deleted`, `already_deleted`: Cinder 부재와 활성화된 RBD backend 부재가 검증된 terminal success
- `delete_submitted`: Cinder 삭제 요청은 수락됐지만 아직 Cinder record가 남아 있음
- `backend_residue`: Cinder record는 사라졌지만 RBD residue가 확인됨
- `backend_unverified`: Cinder record는 사라졌지만 RBD 검사가 비활성 또는 `unknown`
- `blocked`: dependency, attachment, fresh `deleting`, 권한/인증, backend 불일치 또는 unknown 때문에 mutation하지 않음
- `failed`: 허용된 mutation 자체가 실패함

`verified_deleted`는 `deleted`/`already_deleted`에서만 `true`입니다. `backend_verification`은 `verified | unavailable | residue | unknown`, `quota_verification`은 `verified | mismatch | unavailable`을 별도로 반환합니다. UI는 terminal success에서만 상세 패널을 닫고 `delete_submitted`, residue, unverified 결과에서는 check·backend evidence를 유지한 채 상세를 새로고침합니다.

Recovery는 볼륨별 Redis `NX EX=600` lock을 잡습니다. 같은 볼륨의 동시 요청은 HTTP 409, Redis 장애는 fail-closed HTTP 503이며 lock은 `finally`에서 소유 token과 일치할 때만 해제합니다. 모든 결과와 단계, backend/quota 검증은 감사 로그에 기록됩니다.

---

## 네트워크·라우터·포트·Floating IP

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/networks/{network_id}` | 네트워크 상세 | - |
| `GET` | `/api/v1/admin/subnets/{subnet_id}` | 서브넷의 IP 사용량·할당·포트·DHCP 배치 | - |
| `POST` | `/api/v1/admin/networks` | 네트워크 생성 (`201`) | `name`(필수), `is_external`, `is_shared`, `cidr`, `enable_dhcp` |
| `PUT` | `/api/v1/admin/networks/{network_id}` | 네트워크 수정 | `name`, `is_shared` (선택) |
| `DELETE` | `/api/v1/admin/networks/{network_id}` | 네트워크 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/floating-ips` | Floating IP 생성 (`201`) | `floating_network_id` (필수) |
| `DELETE` | `/api/v1/admin/floating-ips/{fip_id}` | Floating IP 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/floating-ips/pool-stats` | Floating IP 풀 사용 통계 | - |
| `POST` | `/api/v1/admin/routers` | 라우터 생성 (`201`) | `name`(필수), `external_network_id` (선택) |
| `PUT` | `/api/v1/admin/routers/{router_id}` | 라우터 수정 (`null`이면 게이트웨이 제거) | `name`, `external_network_id` (선택) |
| `DELETE` | `/api/v1/admin/routers/{router_id}` | 라우터 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/ports` | 포트 생성 (`201`) | 네트워크/고정 IP 지정 |
| `PUT` | `/api/v1/admin/ports/{port_id}` | 포트 이름 수정 | `name` (선택) |
| `DELETE` | `/api/v1/admin/ports/{port_id}` | 포트 삭제 (`204`) | - |

`cidr`을 지정하면 네트워크와 함께 서브넷도 생성됩니다.

### 서브넷 IP 사용량과 연결 대상

`GET /api/v1/admin/all-networks`의 `is_external`, `is_shared`, `project_id`와 기존 `GET /api/v1/admin/projects/names`를 함께 사용한다. 외부와 공유는 독립된 플래그이며 내부는 두 플래그 모두 false인 경우다. 이름 디렉터리가 실패하거나 프로젝트가 목록에 없어도 소유 프로젝트 ID를 보존한다. 네트워크 상세의 `subnet_details[].ip_version`은 실제 Neutron 값이다.

관리자 목록은 외부·공유·내부 조건을 AND로 결합하고 네트워크 이름/전체 ID, 소유 프로젝트 이름/전체 ID 및 현재 언어의 유형 이름을 단어별로 검색한다. 검색은 NFKC·대소문자·주변/반복 공백을 정규화한다. 결과 수와 초기화 동작을 제공하며 inventory 실패와 이름 디렉터리 실패를 구분한다. 네트워크 상세의 각 서브넷에서 IP 조사를 펼칠 수 있고 `/admin/subnets/{subnet_id}`는 같은 조사 UI를 독립 상세로 사용한다. 연결 IP/포트 목록은 각각 20행 pagination 상태를 유지하며 조회 실패는 기존 결과를 경고와 함께 보존한다.

서브넷 상세는 시스템 관리자 인가에 더해 실제 공급자 토큰의 `admin` 역할과 관리자 프로젝트 문맥이 필요하다. 이 문맥을 확인할 수 없으면 Neutron inventory를 읽기 전에 `403`을 반환한다. 플랫폼 관리자 할당만으로 다른 프로젝트의 포트까지 조회했다고 간주하지 않으며 서비스 자격 증명으로 자동 승격하지 않는다.

필수 `ip_usage`의 수량은 모두 **부호 없는 10진 문자열**이다. IPv6 값의 정밀도를 위해 JavaScript `Number`로 변환하지 않는다.

| 필드 | 의미 |
|---|---|
| `total_pool_ips` | 양 끝을 포함한 allocation pool 구간의 합집합 크기. 겹치거나 반복된 구간을 중복 계산하지 않는다. CIDR 전체 host 수가 아니다. |
| `allocated_ips` | 정확히 이 서브넷에 연결된 포트 fixed IP의 정규화된 고유 주소 수. 풀 밖 주소도 포함한다. |
| `allocated_pool_ips` | 풀 합집합 안에 있는 고유 할당 주소 수. |
| `reserved_pool_ips` | 풀 안의 게이트웨이가 아직 포트에 할당되지 않았으면 `"1"`, 그렇지 않으면 `"0"`. |
| `available_pool_ips` | 풀 전체 − 풀 안 할당 − 예약. IPv6 자동 주소 방식에서는 `null`. |
| `outside_pool_ips` | 고유 할당 주소 중 풀 밖에 있는 수. |
| `allocation_mode` | `pool`, `slaac`, `dhcpv6-stateless`. IPv6 address mode 또는 RA mode가 자동 주소 방식이면 해당 방식을 사용한다. |

유효한 풀 목록이 비어 있으면 풀 크기는 `"0"`이며 풀 밖 할당은 그대로 반환한다. 게이트웨이는 동일 IP 버전의 off-subnet 주소나 IPv6 link-local 주소도 허용하며 실제 풀 안에 있을 때만 예약한다. 주소 공간을 열거하지 않고 정수 구간을 합친다. CIDR·풀·해당 서브넷의 fixed IP가 잘못되거나 포트 목록의 후속 페이지가 실패하면 오류를 반환하고 남은 용량을 만들어 내지 않는다.

`allocations`와 `ports`는 서로 다른 포트에 같은 IP가 있으면 각각의 연결 관계를 유지한다. `device_owner`, `device_id`, `project_id`, `binding_host_id`를 보존하고 참조된 인스턴스·라우터마다 한 번씩 이름을 조회하여 `device_name`을 추가한다. 이름 조회가 실패하면 `device_names_available=false`이며 원래 ID와 IP 집계는 유지한다.

`dhcp_bindings`는 실제 DHCP agent와 binding host가 일치하는 포트만 연결한다. DHCP scheduler 정보를 읽을 수 없으면 `dhcp_agent_data_available=false`이고 포트에서 확인한 IP·host 배치를 `source="port"`로 보존한다. 이 inventory는 Neutron 주소 할당 상태이며 게스트의 실제 연결성이나 트래픽을 증명하지 않는다.


---

## 파일 스토리지 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/file-storage` | 전체 Afterglow 파일 스토리지(Manila share) 목록 (prebuilt + dynamic) |
| `POST` | `/api/v1/admin/file-storage/build` | 사전 빌드 share 생성 트리거 (`202`) — `library_id` (query, 필수) |
| `GET` | `/api/v1/admin/file-storage/builds` | 진행 중/대기 중 빌드 목록 |
| `GET` | `/api/v1/admin/file-storage/{file_storage_id}/delete-diagnostics` | share 삭제 실패 진단 |
| `POST` | `/api/v1/admin/file-storage/{file_storage_id}/force-delete` | share 강제 삭제 (`202`) |

**build 오류**: `404` 알 수 없는 `library_id`, `409` 이미 존재하는 사전 빌드 스토리지.

---

## 라이브러리 관리 (squashfs 레이어)

관리자 라이브러리 화면은 squashfs 레이어 워크플로우(레이어 artifact·프로필·소비 인스턴스)를 관리합니다. prefix는 `/api/v1/admin/libraries`이며 `/api/v1/admin/layers` alias는 제공하지 않습니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/admin/libraries/build` | squashfs 레이어 빌드 시작 |
| `GET` | `/api/v1/admin/libraries/builds` | 레이어 빌드 목록 |
| `GET` | `/api/v1/admin/libraries/builds/{id}` | 레이어 빌드 상세 |
| `POST` | `/api/v1/admin/libraries/builds/{id}/cancel` | 레이어 빌드 취소 |
| `GET` | `/api/v1/admin/libraries/artifacts` | 봉인된 레이어 artifact 목록 |
| `GET` | `/api/v1/admin/libraries/artifacts/{id}/delete-preview` | artifact 삭제 영향 미리보기 |
| `DELETE` | `/api/v1/admin/libraries/artifacts/{id}` | artifact 삭제 |
| `POST` | `/api/v1/admin/libraries/profiles` | 레이어 프로필 생성/갱신 |
| `DELETE` | `/api/v1/admin/libraries/profiles/{profile_name}` | 레이어 프로필 삭제 |
| `POST` | `/api/v1/admin/libraries/consume` | 프로필 또는 완료된 Dockerfile 작업의 고정 artifact ID로 소비 인스턴스 생성 |
| `GET` | `/api/v1/admin/libraries/consumes` | 소비 인스턴스 목록 |

---

## Zun 컨테이너 관리

Zun 서비스 활성화 시에만 사용 가능합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/containers/{container_id}` | 컨테이너 상세 |
| `GET` | `/api/v1/admin/containers/{container_id}/logs` | 컨테이너 로그 |
| `POST` | `/api/v1/admin/containers/{container_id}/start` | 컨테이너 시작 |
| `POST` | `/api/v1/admin/containers/{container_id}/stop` | 컨테이너 정지 |
| `DELETE` | `/api/v1/admin/containers/{container_id}` | 컨테이너 삭제 (`204`) |

---

## 가입 정책·개인 프로젝트 quota와 승인 대기열

시스템 관리자 → 설정에서 제어합니다. 모든 경로는 `/api/v1/admin` 기준이고 read도 fresh native `system:all` admin 검증을 요구합니다. Domain/project manager나 저장된 브라우저 flag는 권한이 아닙니다. 응답은 no-store/private입니다.

| 메서드·경로 | 입력 | 성공 |
|---|---|---|
| `GET /enrollment-policy` | 없음 |200 정책 DTO |
| `PUT /enrollment-policy` | `{revision,public_signup_enabled,public_signup_button_visible,approval_mode,personal_quotas}` |200 갱신된 정책; stale revision409 |
| `GET /signup-requests` | `status=pending\|approved\|rejected\|all`, optional UUID `cursor` |200 `{items,next_cursor}`; 최대50개 |
| `POST /signup-requests/{request_id}/approve` | 없음 |200 확정한 request DTO |
| `POST /signup-requests/{request_id}/reject` | 없음 |200 확정한 request DTO |
| `GET /personal-project-quotas` | 선택 `cursor` |200 `{items,next_cursor}`; exact Personal 전체 프로젝트를100개씩 조회 |
| `GET /personal-project-quotas/{project_id}/preview` | 없음 |200 policy/current usage+reserved·owner·`preview_id`·`can_apply/blocked_fields`; native write 없음 |
| `POST /personal-project-quotas/{project_id}/apply` | `{preview_id}`64hex |200 기존 `DomainQuotaOperation` 결과·operation_id; stale preview409 |

정책 DTO는 revision/public_signup_enabled/public_signup_button_visible/approval_mode/personal_quotas/quota_fields/defaults_future_only:true/smtp_configured입니다. Approval은 auto/admin, personal_quotas는 지원 key→strict integer(-1 이상)의 sparse object이며 blank는 native 기본값,0은 금지,-1은 unlimited입니다. 비활성 Manila template entry는 보존·omitted로 표시합니다. 저장은 앞으로 생성하는 각 personal project에만 적용하고 기존 프로젝트나 shared domain budget을 변경하지 않습니다. Accounts user와 personal project는 disabled staging·본인 직접 native member 하나·raw/effective provenance·동결 native quota readback 뒤 활성화합니다. 새 owner/reader·domain manager·Default는 생성하지 않으며 기존 personal grant는 보존합니다.

`public_signup_button_visible`은 로그인 화면의 회원가입 링크 노출만 제어하는 별도 strict boolean입니다. `public_signup_enabled` 및 SMTP readiness와 함께 public `signup_button_visible`로 투영되지만, 숨김 값 자체는 `/signup` 직접 접근·검증 링크 발급/소비·OIDC enrollment·기존 조직 admission을 막거나 허용하지 않습니다. 시스템 관리자만 이 전역 표시 정책을 저장하며 domain manager는 자기 domain의 이메일/admission 정책만 관리합니다. 최초 row 부재의 설정 fallback은 `[auth].public_signup_button_visible=true`이며 기존 row에는 additive migration101의 true만 추가합니다. 기존 signup opt-in·approval·quota·revision은 덮어쓰지 않습니다.

최초 policy row 부재만 config의 공개 가입 opt-in·auto와 source 기본2 vCPU·4096MiB RAM·1024GiB Cinder, instances2·volumes10·snapshots10 및 보조 network count로 시작합니다. DTO는 `personal_quota_source:source_defaults|administrator`와 `source_default_personal_quotas`도 반환합니다. 기존 저장 template(0 포함)은 그대로 유지하므로 새 제공값을 원하면 UI의 **제공 기본값 사용**으로 draft를 채운 뒤 명시 저장합니다. SQL 장애는503이며 source default로 우회하지 않습니다. 디스크 값은 quota이지 실제 볼륨 생성이 아닙니다.

기존 프로젝트는 **개인 프로젝트 불러오기→paged 선택→현재 사용량과 정책 미리 확인→확인 checkbox→적용** 순서입니다. Fresh system authority, exact Personal·활성 user/project·소유 marker, accepted member SQL provenance 또는 검증된 legacy native-owner primary를 요구합니다. Native member-only catalog에 project_owner 프리셋을 추가하지 않습니다. 현재 in_use+reserved가 새 limit를 초과하거나 reservation을 확인하지 못하면 적용 불가입니다. Apply는 policy/사용량/소유권·preview fingerprint를 다시 검사하고 기존 native quota journal/readback을 사용합니다. 결과 unknown은 원 호출 종료·기존 domain quota settlement 전 반복 적용하지 않습니다. 원래 personal provisioning intent의 동결 quota·계정/권한/리소스는 수정하지 않습니다.

대기열은 전달된 email link 또는 검증된 provider subject에서만 생성합니다. DTO는 ID/source/email/target domain/provider/status/생성·review 시각과 reviewer ID를 공개하되 identity/binding hash·password·OAuth code·bearer는 반환·저장하지 않습니다. 소비 시각과 생성 사용자 ID는 내부 SQL provenance이며 대기열 DTO에는 없습니다. 상태는 pending→approved/rejected, 성공한 새 계정 생성 뒤 approved→consumed입니다. `all`은 consumed도 포함합니다. Pending만 review할 수 있고 확정한 결정은 재승인·취소·자동 재전송하지 않습니다. Auto로 바꿔도 기존 pending/rejected/consumed 요청을 우회하지 못합니다.

Email 승인은 공개 가입 enabled이면 **새 검증 메일**, invitation-only면 원래 검증 초대 재조회 안내를 보냅니다. 승인 메일 오류503 `signup_approval_notification_failed; approval remains approved`는 결정이 이미 approved로 확정됐다는 뜻입니다. 상태를 다시 조회하고 필요하면 새 email 검증 링크/초대를 별도로 요청해야 하며 approve POST를 자동 재시도하지 않습니다. OIDC/GitHub는 관리자 승인 뒤 **새 provider 로그인**을 시작하며 이전 code를 재사용하지 않습니다. 기존 계정 로그인/조직 초대 수락은 신규 승인과 별개이며 기존 home을 이동하지 않습니다.

---

## 도메인 관리와 관측

모든 `/api/v1/admin/domains` route는 verified system admin 전용입니다. 기본 DTO는 `{id,name,enabled,description}`입니다. **`id`가 identity·인가·scope 경계이고 `name`은 중복 가능한 표시 이름**입니다. 공통 `domain_display.display_name`은 native `afterglow_display_name`을 읽고, 속성이 없는 기존 도메인은 기존 native `name`을 fallback으로 사용합니다. 새 managed 도메인의 native name은 `afterglow-<새 UUID의 hex>`이며 domain ID 자체나 표시 이름과 같지 않습니다. PATCH `name`은 표시 속성만 변경하고 native name을 보존·readback합니다. 기존 도메인 native name이나 운영자 설정을 일괄 변경하지 않습니다. API 호출에는 표시 이름이 아니라 정확한 domain ID를 사용하세요.

새 도메인은 canonical `Default`, 생성자의 직접 `manager`와 `project_reader`, manager용 native 읽기 projection을 준비하고 응답에 `default_project_id`를 포함합니다. 생성자는 다른 identity 도메인 소속이어도 기존 계정 ID를 그대로 사용합니다. Domain은 먼저 enabled 상태, Default는 disabled 상태로 만들고 권한·projection·미래 프로젝트 quota 기본값을 확인한 뒤 Default를 활성화합니다. 요청 `enabled=false`는 준비가 끝난 domain을 마지막에 비활성화합니다. Native 응답 유실은 생성 실패의 증거가 아니므로 이름으로 재시도하거나 기존 리소스를 추측 삭제하지 않습니다. 확인된 새 ID만 보상 대상이며 불확실한 잔여 상태는 관리자 복구가 필요합니다.

| 메서드·경로 | 입력 | 응답 |
|---|---|---|
| `GET /api/v1/admin/domains` | 없음 | 200 `{items:[Domain]}`, name/id 정렬 |
| `POST /api/v1/admin/domains` | `{name,description?,enabled?}` | 201 Domain |
| `POST /api/v1/admin/domains/{domain_id}/default` | `{creator_id}` 필수 | 201 `{domain_id,default_project_id,creator_id}`; 기존 도메인 명시적 bootstrap |
| `PATCH /api/v1/admin/domains/{domain_id}` | `{name?,description?,enabled?}` | 200 Domain |
| `GET /api/v1/admin/domains/{domain_id}/monitoring` | `window=24h\|7d\|30d`, 기본24h | 200 monitoring DTO |
| `GET /api/v1/admin/domains/{domain_id}/members` | 없음 | 200 `{domain_id,items:[{id,name,email,enabled,domain_id}]}`; 활성 home/joined membership 후보 |
| `GET /api/v1/admin/domains/{domain_id}/managers` | 없음 | 200 `{items,roles,default_project_id}` |
| `POST /api/v1/admin/domains/{domain_id}/managers` | `{user_id,role_id}` | 201 `{items,roles,default_project_id}` |
| `DELETE /api/v1/admin/domains/{domain_id}/managers` | query `user_id`, `role_id` 필수 | 204 |
| `GET /api/v1/admin/domains/{domain_id}/enrollment-operations` | 없음 | 200 `{items:[EnrollmentOperation]}`; interrupted/failed 등록·초대·관리자 사용자 생성 작업 |
| `POST /api/v1/admin/domains/{domain_id}/enrollment-operations/{operation_id}/reconcile` | `{native_writes_settled:true}` (strict boolean) | 200 operation DTO; 원 native 요청 종료 확인 후 provenance/readback 기록 |
| `DELETE /api/v1/admin/domains/{domain_id}/enrollment-operations/{operation_id}` | 없음 | 204; 검증된 해당 작업의 추가 효과만 보상하고 취소 |

`GET /domains/{domain_id}/members`는 verified system admin용 membership 후보 directory이며 `Cache-Control: no-store, private`입니다. 공통 `domain_iam.directory_users`의 fresh native home/joined 목록에서 enabled 사용자만 반환하고 pagination/query 필터는 없습니다. 최상위 `domain_id`는 선택한 working domain, 각 item의 `domain_id`는 계정의 immutable native home입니다. `protected` 필드·credential metadata·blob·secret은 반환하지 않습니다. 이 목록은 project/group 역할·membership 후보를 위한 것이며 `/admin/users?domain_id=...`의 home-only profile 관리나 credential owner/project 검증을 확장하지 않습니다. 단순 후보 응답은 실제 mutation 인가를 대신하지 않습니다.

이 candidate endpoint만 exact native **user GET404**로 확인한 부재 계정을 생략합니다. 삭제 사용자 ID가 남은 역할 할당과 목록/개별 조회 사이의 삭제가 해당되며, 사용자403/5xx·home-domain404·ID 불일치·불명 역할 graph를 빈 후보나 부분 성공으로 바꾸지 않습니다. 다른 directory 소비자와 실제 membership/manager mutation은 기존 strict 권위 검사를 유지합니다. Group 사용자 목록은 `{id,name,email,domain_id,identity_read_only,enabled}`를 유지하고 조회 중 provider 오류는 빈/부분200이 아닙니다. UI의 멤버·후보는 이름/이메일/전체 UUID/home-domain ID를 표시하고 이름·이메일·UUID·home ID로 검색하며, 같은 이름도 별도 UUID로 선택합니다. Candidate 조회 실패는 성공한 멤버 목록과 독립 표시하고 명시적으로 재조회합니다.

Create/PATCH body는 extra field 금지·문자열 앞뒤 공백 제거. Name 1–64자, description 최대4096·기본 `""`, enabled 기본true입니다. PATCH의 null/생략은 unchanged, 실제 변경 없음은 `422 domain_invalid_input`. Native 실패는 403 `domain_native_denied`, 404 `domain_not_found`, 409 `domain_conflict`, 400/422 `domain_native_invalid`, 503 `domain_unavailable`입니다. 도메인 삭제 API는 없습니다.

Domain disable은 공유 role-graph lease 아래 현재 enabled effective system admin과 영향을 받는 Default manager를 검사합니다. 마지막 usable system admin을 모두 잠그는 disable은422, 활성 대상 도메인의 마지막 manager를 제거하는 변경은409입니다. 외부 manager의 계정 소속 도메인을 비활성화할 때도 대상 프로젝트 읽기 projection과 권위 cache를 정리합니다. 비활성 계정·도메인, 명시적 보안 회수와 native 로그인 증명 무효는 기존대로 인증·접근을 차단합니다. Native에 반영된 뒤 응답만 실패한 경우에도 이 정리를 수행하고 원래 요청은 오류로 유지합니다.

Managers의 `roles`는 canonical global `manager` 하나의 `{id,name,grantable}` 배열입니다. `items`는 `{user_id,user_name,user_domain_id,role_id,role_name,direct}`이며 Default의 **활성 effective manager**를 직접·그룹·상속·역할 추론까지 포함해 표시합니다. `direct`는 해당 사용자의 canonical manager 직접 grant가 있는지를 뜻합니다. 외부 identity 소속 활성 사용자에게도 manager를 부여할 수 있지만 대상 Default와 계정 소속 도메인의 활성 상태를 검증합니다. POST user/role ID는1–255자이며 다른 역할은422 `domain_manager_role_invalid`입니다. DELETE는 canonical manager의 직접 grant만 제거하며 없으면404 `domain_manager_direct_grant_not_found`; 간접 권한은 그 원본 group/grant/graph에서 변경합니다. 마지막 유효 manager는409로 보호됩니다.

Default가 없는 기존 도메인의 manager 추가는409 `domain_default_bootstrap_required`이며 system admin이 provenance를 확인한 `creator_id`로 `/default`를 호출해야 합니다. 기존 native membership으로 로그인하는 경로는 보존하지만 로그인이나 조회가 임의의 첫 사용자에게 manager를 부여하지 않습니다. 모호한 Default/역할과 native/lease 확인 실패는 fail-closed입니다. Bootstrap은 활성 도메인에서 수행하며 기존 Default를 다른 ID로 바꾸거나 실패 시 기존 프로젝트를 삭제하지 않습니다. Grant/revoke는 authority·기존 세션 검증 cache와 native 읽기 projection을 함께 정리하되 Afterglow 로그인 family를 일괄 삭제하지 않습니다. Native가 group membership 변경으로 로그인 증명까지 회수하면 재로그인이 필요합니다. 관리자용 generic project/group/role 변경에서도 Default anchor, reserved projection과 마지막 manager 불변식을 우회할 수 없습니다.

Enrollment operation은 원래 admission target domain_id와 실제 identity_domain_id, personal_domain_id/personal_project_id/personal_project_name, kind/status/user/project/role·native_writes_settled/recovery_required·시각 metadata를 가집니다. Historical personal_domain_name은 새 생성 입력이 아닙니다. Interrupted/failed 상태만 목록에 포함하며 token/password/native marker는 공개하지 않습니다. 기존 reconcile body는 native_writes_settled:true이고 운영자가 원 native 요청 종료를 확인한 뒤 exact readback합니다. 이후 DELETE도 이번 작업의 exact owned-empty project/account·추가 grant만 정리하며 shared account/personal domain과 기존 user는 삭제하지 않습니다. 안전하게 확정할 수 없으면503 recovery를 유지하고 accepted/revoked 취소는409입니다.

### Shared topology·OIDC organization settlement

아래 경로도 `/api/v1/admin` 기준이며 fresh native system-admin을 graph lease 안에서 재검증합니다. Operator는 원 native call이 더 이상 실행 중이지 않음을 별도 확인해야 하고 `native_calls_settled`는 strict boolean true여야 합니다. 다른 field는422입니다. 기존 enrollment의 native_writes_settled와 혼동하지 마세요.

| 메서드·경로 | 입력 | 의미 |
|---|---|---|
| `GET /account-topology/operations` | 선택64-hex cursor | secret-free shared_domains/personal_projects/next_cursor |
| `POST /account-topology/shared-domains/{kind}/settle` | `{native_calls_settled:true}` | 새 accounts/personal exact shared marker readback; historical account receipt는 별도 보존·settlement하며 absent settlement는 history 보존 후 별도 새 intent만 허용 |
| `POST /account-topology/personal-projects/{operation_id}/settle` | `{native_calls_settled:true}` | 본인 직접 member/native-provenance/frozen-quota 프로젝트 수용 또는 exact owned-empty staged project만 정리; 과거 owner/reader intent는 실제 journal 계획 역할로 검증 |
| `GET /organization-bindings` | 없음 | secret-free unsettled binding·native candidate ID |
| `POST /organization-bindings/{binding_key}/settle` | `{intent_id,native_calls_settled:true}` |64-hex issuer/org binding과 exact intent/creator/native marker·활성 Default/owner/manager 재검증 |

조직 candidate가 정확히 하나이고 완성된 경우만 active로 수용합니다. Candidate0이며 기록된 returned ID도 없으면 native를 건드리지 않고 SQL intent를 release할 수 있습니다. Partial/ambiguous/recorded-ID mismatch는409 organization_settlement_incomplete로 fenced 상태를 유지합니다. Native create/grant 재전송·추측 adoption·기존 계정/공유 domain 삭제는 하지 않습니다.


### Monitoring DTO와 수집 범위

응답 최상위는 `{domain,directory,resources,requests,logins,sessions,activity,coverage}`입니다. `domain={id,name,enabled}`의 name은 공통 표시 이름입니다. `directory.projects`는 exact native domain 프로젝트 수이며 disabled 프로젝트도 포함합니다. `directory.users`는 **native home 사용자와 현재 활성 프로젝트의 명시적 source/effective membership으로 확인된 joined 사용자의 합집합**입니다. Joined 외부 계정은 계정과 home domain이 활성일 때만 포함하며 stale manager projection만으로 부활시키지 않습니다. 따라서 이 사용자 수는 home만 나열하는 `GET /admin/users?domain_id=...`의 total과 같지 않을 수 있습니다. Directory 실패는 snapshot을 중단하며 native 조회 오류는 403 `domain_monitoring_native_denied`, 404 `domain_not_found`, 503 `domain_monitoring_directory_unavailable` 등으로 반환합니다. Joined IAM directory 검증 오류는 해당 서비스의 오류 계약을 그대로 사용할 수 있습니다.

- `resources[]`: `{service,metric,kind,value,unit,status,error?}`. Kind는 `count/utilization/allocation`, status는 `ready/partial/denied/unavailable/disabled/unlimited`. 명시적 owner project가 domain inventory에 속한 리소스만 귀속하며 ownerless row는 추정하지 않습니다. 일부 owner 누락은 known lower-bound count·partial, 전부 owner 누락은 null/unavailable(`owner_unavailable`). Nova vcpu/RAM과 Cinder volume GiB utilization은 실제 provisioned 자원 합계이며 실시간 CPU 사용률이 아닙니다. 필요한 크기 값 누락은 null/partial(`value_unavailable`).
- Count metric은 Nova instances/keypairs, Cinder volumes/snapshots/backups, Neutron floating_ips/networks/subnets/routers/security_groups, Octavia load_balancers, Glance images, Trove database_instances/backups, Drover k3s_clusters, Waygate gateways, Zun containers, Magnum clusters, Manila shares/snapshots/networks/security_services, Swift buckets, Palimpsest packages, Barbican secrets입니다. `keypairs`, Trove, Drover, Waygate, Magnum, Swift, Palimpsest, Barbican은 usable cross-project API가 없어 **null/unavailable `domain_aggregate_unsupported`**입니다. 비활성 선택 서비스는 null/disabled `service_disabled`; native 거부/장애는 `native_denied`/`native_unavailable`입니다.
- Allocation은 Nova instances/cores/ram과 Cinder volumes/gigabytes의 project quota 한도 합입니다. Domain 최대100개 프로젝트·동시8개 조회; 초과는 null/partial `project_limit_exceeded`. 무제한(-1)은 null/unlimited이며 finite 합계로 표시하지 않습니다.
- `requests={state,window,total,errors,services,timeline}`: token으로 domain이 귀속된 Afterglow **backend 요청**만입니다. Services는 `{service,requests,errors}`, timeline은 UTC `{at,requests,errors}`. State `ready/partial/unavailable/disabled`; empty store는 partial이며 total/errors/timeline은 null입니다. Frontend 익명 pageview나 cloud 전체 요청은 아닙니다.
- `logins={state,successes,recorded_failures,failure_history,timeline}`: 보존 SQL Afterglow auth/login 관측입니다. `failure_history="not_collected"`이며 실패0은 실제 실패 없음의 증거가 아닙니다. Timeline은 UTC `{at,successes,recorded_failures}`. `activity={state,recent_users,events,last_seen,hour_distribution}`는 domain 프로젝트 활동과 domain-only auth 관측이며 hour distribution은 UTC `{hour,events}`. 최대10000 row를 넘으면 partial·집계 수치 null; DB 장애는 unavailable·null입니다.
- `sessions={state,valid_count,observed_recent_count,unattributed_count,online_count}`: Redis retained refresh record를 최대50000개·batch500으로 스캔하며 timeout/expiry/blacklist를 확인합니다. Domain metadata 없는 유효 record는 unattributed_count로 분리하고 귀속하지 않습니다. Cap/잘못된 row는 partial이며 반환 count는 확인된 관측만입니다. Redis 장애는 unavailable·count null. 최근300초 last_seen은 observed_recent일 뿐, `online_count`는 **항상 null**입니다.
- `coverage={window,observed_at,partial,notes}`: notes는 번역된 문장이 아닌 안정된 코드입니다. `login_failure_history_not_collected`, `activity_is_afterglow_audit_only`, `sessions_are_not_online_presence`, `activity_observation_limit_exceeded`, `activity_storage_unavailable`, `sessions_incomplete`, `sessions_without_domain_attribution`, `resources_incomplete`, `requests_token_attributed_partial`을 사용합니다. Null/unsupported/partial을 정상0 또는 실제 온라인 사용자로 표시하지 않습니다.

### 도메인 리소스·사용자별 관측과 IAM 경계

System-admin `/domains/{domain_id}/monitoring`은 위 집계 DTO이며 별도 `/admin/domains/{domain_id}/resources`나 `/users` 상세 endpoint를 제공하지 않습니다. Domain manager의 상세 관측은 **`GET /api/v1/iam/monitoring`**이며 live working-domain manager 검증 후 서버의 admin-project connection으로 exact domain만 읽습니다. System admin이라고 이 IAM 경계를 자동 우회하지 않습니다. 관리자는 [도메인 IAM](iam.md)의 권한 계약과 함께 사용하세요.

IAM monitoring 응답은 `{domain,projects,users,resources,inventory,coverage}`입니다.

- `projects[]`: `{id,name,enabled,quotas,resources}`. `quotas`는 공통 native quota DTO의 서비스별 실제 limit·in_use·제공되는 reserved와 availability/errors입니다. Resource metric에는 프로젝트별 allocation과 실제 provisioned utilization을 구분합니다.
- `users[]`: `{id,name,domain_id,enabled,project_ids,membership_state,resources}`. `domain_id`는 immutable native home이며 working domain으로 덮어쓰지 않습니다. Project membership은 해당 domain 프로젝트의 effective native assignment에서 읽고 실패는 `membership_state="unavailable"`로 표시합니다. 실패 중 남은 project_ids를 완전한 목록으로 해석하지 않습니다.
- `inventory[]`: `{category,id,name,project_id,user_id,status}`의 안전한 metadata입니다. 명시적 owner project가 선택 domain에 속하는 row만 포함하고 사용자 귀속은 native `user_id` 또는 지원되는 snapshot user 속성으로만 판단합니다. 알려진 사용자로 귀속할 수 없으면 user_id는 null이며 category별 `user_attribution_unavailable`/partial을 표시합니다. 사용자별 사용량 합이 domain 전체와 같다고 보장하지 않습니다.
- `resources`는 domain 합계이며 공통 category의 unsupported/disabled/denied/unavailable 및 allocation의 unlimited를 보존합니다. `coverage={observed_at,partial,notes}`에 `project_memberships_unavailable`, `<category>:user_attribution_unavailable`, `resources_incomplete`를 표시할 수 있습니다. 위 admin 집계의 100-project allocation cap을 IAM 상세 quota 수집의 계약으로 확대하지 않습니다.

이 API는 **프로젝트 native 쿼터를 사용자별 enforcement로 표현하지 않으며**, request/login/session history·자격 증명/secret을 manager 상세에 가져오지 않습니다. 사용자 이름이나 이메일로 다른 domain 자원을 추정 합산하지 않습니다.

## Identity 도메인 선택 계약

아래 user/project/group identity route는 domain 선택을 명시적으로 처리합니다. 시스템 admin의 inventory·global observation은 **사용자 workspace selector와 별개**입니다. `/admin/domains`의 전역 목록이나 `/admin/projects/names`의 전역 picker를 사용자 세션 전환 권한으로 사용할 수 없습니다. Selector는 현재 home/created/joined domain과 실제 project membership(또는 domain manager의 enabled project 읽기 projection)만 사용하며 system:all은 그 목록을 전역으로 확장하는 bypass가 아닙니다. 관리자 필터 변경은 active session scope를 바꾸지 않으며 `X-Project-Id`도 native 인증 범위를 바꾸지 않습니다.

| 경로·메서드 (`/api/v1/admin` 기준) | `domain_id` 계약 |
|---|---|
| `GET /users`, `/users/stats`, `/users/activity`, `/projects`, `/groups` | non-empty query 필수; 생략/빈 값422 |
| `GET /users/lock-status` | `username` 및 non-empty domain_id query 필수 |
| `POST /users`, `/projects`, `/groups` | non-empty body domain_id 필수 |
| `POST /users/unlock-account` | `{username,domain_id}` 필수 |
| `GET /projects/names` | 선택 query; 생략 시 system-wide picker, 응답 row는 `{id,name,domain_id}`; malformed native metadata는503 |
| `PATCH /users/{user_id}`; `POST /users/{user_id}/revoke-sessions`; `GET /users/{user_id}/sessions`, `/permissions` | 선택 non-empty query; 지정하면 user의 domain을 확인 |
| `DELETE /users/{user_id}` | non-empty query 필수; 정확한 native home domain과 user ID를 같은 관리자 executor로 재검증 |
| `GET/PATCH/DELETE /projects/{project_id}`; `GET /projects/{project_id}/deletion-check`, `/members`; `POST /projects/{project_id}/sync-monitoring-sg`; `GET/PUT /quotas/{project_id}`; `PUT /compute-policy/{project_id}` | 선택 non-empty query; 지정하면 project의 domain 확인 |
| `PATCH/DELETE /groups/{group_id}`; `GET /groups/{group_id}/users`; `PUT/DELETE /groups/{group_id}/users/{user_id}` | 선택 non-empty query; 지정하면 group이 선택 domain에 속하는지 확인. 관계의 user는 정확한 native identity로 검증하며 다른 home도 허용 |
| `POST/DELETE /roles/assign`, `/roles/assign-group` | 선택 query; grant는 생략해도 대상 project의 native domain을 anchor로 확인. user/group principal은 다른 native home일 수 있고 role은 global 또는 anchor domain 소유여야 함 |
| 역할 catalog/CRUD/implication/preset·system-roles·security-policy·identity summary | domain 선택 query 없음; 역할 생성의 body domain_id는 선택(global role 기본) |

선택 domain과 **anchor object** 또는 role의 domain 불일치는 **403 `identity_domain_mismatch`**입니다. 단일 user/profile/session/permissions route에 domain을 지정하면 그 user의 native home을 검사하므로 joined working domain을 profile 관리 domain으로 대체할 수 없습니다. 단일 object route는 domain 미선택 시 system-wide native 동작입니다. User permissions의 선택 domain 필터는 system scope를 유지하고 해당 domain/project scope만 남기지만 앞선 home 검증도 적용됩니다.

Project/group member 관계는 다른 home의 principal을 목록에서 숨기지 않습니다. Project 사용자 row와 group 사용자 row는 native `domain_id`를 반환하며 선택 domain과 home이 다르면 `identity_read_only:true`를 표시합니다. 이는 그 관계에서 profile/password 편집을 허용한다는 뜻이 아닙니다. Verified system admin의 generic 관계 API는 native cross-home principal을 다룰 수 있지만 domain manager/project owner의 IAM·초대 경로는 live joined membership 및 safe-role ceiling을 별도로 검사합니다. Domain 미선택 DELETE는 과거 cross-domain 관계 정리를 허용하며 명시적 선택 시 anchor·role 검증은 유지합니다. Project activity 등 다른 router는 이 계약을 자동 상속하지 않습니다. Credential API는 별도의 엄격한 owner/project home-domain 검증을 유지하며 joined membership만으로 외부 home의 credential/blob을 공개하지 않습니다.

## 사용자 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/users` | 선택 domain **native home** 사용자 목록 (페이지네이션; joined 외부 사용자 목록 아님) | 필수 query `domain_id` |
| `GET` | `/api/v1/admin/users/stats` | 선택 native home domain 사용자 통계 `{total,enabled,disabled}` | 필수 query `domain_id` |
| `GET` | `/api/v1/admin/users/activity` | 선택 native home domain 사용자 변경 로그; limit 기본50·1–200, before_id 선택 | 필수 query `domain_id` |
| `POST` | `/api/v1/admin/users` | Accounts identity 생성; personal member primary는 첫 성공 로그인까지 deferred, 관측 domain 자동 admission 없음 (`201`) | `name`, `email`, `password`, `domain_id` 필수; `enabled` 기본true |
| `PATCH` | `/api/v1/admin/users/{user_id}` | 사용자 수정 | `name`, `email`, `enabled`, `password` (선택) |
| `DELETE` | `/api/v1/admin/users/{user_id}` | 단일 native 계정 영구 삭제 (`204`), 세션 폐기·inventory 무효화; 프로젝트/자원 cascade 없음 | 필수 query `domain_id` |
| `POST` | `/api/v1/admin/users/{user_id}/revoke-sessions` | 사용자 세션 전체 무효화 | - |
| `GET` | `/api/v1/admin/users/{user_id}/sessions` | 사용자의 활성 세션 목록 | - |
| `GET` | `/api/v1/admin/users/{user_id}/permissions` | 사용자의 현재 유효 프로젝트·도메인·시스템 역할 | - |
| `POST` | `/api/v1/admin/users/unlock-account` | domain별 로그인 잠금 해제 | `{username,domain_id}` |
| `GET` | `/api/v1/admin/users/lock-status` | domain별 계정 잠금 조회 | query `username`, `domain_id` 필수 |

**주의**: `revoke-sessions`는 해당 사용자의 토큰/세션 캐시를 즉시 무효화합니다.

생성 body는 extra field 금지이며 name1–255자, email3–255자, password12–1024자, domain_id non-empty입니다. domain_id는 관측 context로 존재만 확인하고 home/admission target으로 사용하지 않습니다. 요청 enabled 값의 Accounts identity와 accepted managed_create enrollment·같은 token/name·동결 quota의 deferred personal intent를 함께 commit하며 이 요청은 프로젝트/grant를 만들지 않습니다. 응답은 id/name/email/enabled/protected:true·user_id, **Accounts domain_id/domain_name**과 identity_domain_id/identity_domain_name, personal_domain_id, personal_project_deferred:true, personal_project_id:null 및 **예약된 personal_project_name**입니다. enabled:false는 명시 활성화 뒤 실제 로그인 proof가 필요합니다. 첫 로그인은 Personal disabled staging에 본인 직접 member 하나·동결 quota·native provenance를 확인한 뒤 활성화합니다. 기존 ID/home/credentials/grants·리소스 및 관측 domain의 Default는 변경하지 않습니다. Journal의 관측 domain_id는null이고 unknown 작업은 system-only settlement 전 재전송하지 않습니다. 조직 참여는 별도 초대/신뢰된 OIDC admission입니다.

마지막 enabled effective system admin을 비활성화하는 PATCH는 공유 role-graph lease 아래 재검증해 `422`로 거부합니다. 권한 회수와 동시 비활성화도 같은 보호를 사용합니다. 현재 project owner는 먼저 소유권을 이전해야 하며 비활성화는 `409`입니다. 관련 unresolved ownership operation이 있어도 user/domain disable을 차단합니다. 이는 단순한 마지막 manager 보호와 별도입니다.

### 명시적 사용자 계정 삭제

사용자 목록의 table·compact card에서 **삭제**를 선택하면 이름·전체 user ID·native home domain을 표시합니다. 전체 ID를 정확히 입력해야 제출할 수 있습니다. 모르는 이름·연합 계정·이메일 부재만으로 자동 삭제하지 않으며, 이 작업은 프로젝트 멤버십 제거가 아니라 계정 영구 삭제입니다. 자기 계정 버튼은 비활성화합니다. 확인을 열 때 native 목록을 새로 읽고, actor/session/home/project/권한·선택 domain의 변경과 ABA·unmount 후의 확인/응답은 폐기합니다.

삭제 API는 fresh system-admin과 기존 configured native admin-project executor를 사용합니다. Graph lease 안에서 대상 home·UUID, ownership/identity-transfer journal, Personal 소유·provisioning/enrollment, 현재 system-admin/domain-manager 보존을 검사하고 dispatch 직전 요청자 권위를 다시 검증합니다. 정확한 actor/executor, 설정된 `os_username`과 같은 native 이름, native admin/service/system 권위를 가진 계정은 보호합니다. Kolla service 계정은 `service` role 없이 service project의 `admin`만 가질 수 있으므로 `admin`/`service`의 실제 role-ID DAG와 raw system user/group grant도 검사합니다. 다른 도메인의 같은 configured 이름도 보수적으로 보호합니다. Privileged 계정은 기존 보호된 권한 회수 절차를 먼저 거쳐야 하며, service 운영 계정 정리를 이 기능으로 대신하지 않습니다.

현재 owned Personal primary/추가 프로젝트는 native role이 member여도 삭제를 차단합니다. 프로젝트·VM·볼륨을 함께 지우거나 소유자를 잃은 자원으로 남기지 않습니다. 먼저 별도의 프로젝트 삭제/소유권 처리와 미완료 provisioning을 정산해야 합니다. 이미 해소된 빈 accepted/cancelled/deferred intent만 있다는 이유로 계정을 영구 차단하지는 않습니다. 세션 저장소·native 권위·SQL journal 조회 실패도 fail-closed이며 새 schema/config/dependency는 추가하지 않습니다. 기존 SQL102 등 현재 source의 journal schema는 필요합니다.

Native 삭제는 `ignore_missing=False`입니다. 대상 부재404를 성공으로 바꾸지 않고403/409/5xx를 표시합니다. 실제 dispatch 뒤에는 성공·응답 유실 모두 대상 세션 폐기와 권위/inventory 무효화를 수행하고 감사 기록을 남깁니다. 불확실한 응답/401/408/5xx는 브라우저에서 자동 replay하지 않으며 창을 닫고 삭제를 다시 열어 현재 디렉터리를 확인해야 새 확인을 시작할 수 있습니다. 기존 로그인 없이 남은 orphan grant, native DB 직접 정리 또는 관련 프로젝트 삭제는 이 endpoint의 범위가 아닙니다.


### 사용자별 프로젝트 및 유효 역할

사용자 목록에서 사용자를 선택하면 수정 창에 활성 세션과 권한 목록을 함께 표시합니다. 권한 조회는 시스템 관리자 전용이며 역할 변경이나 세션 폐기를 실행하지 않습니다.

`GET /api/v1/admin/users/{user_id}/permissions`는 `{items: [{scope_type, scope_id, scope_name, roles: [{id, name}]}], count}`를 반환합니다. `scope_type`은 `project`, `domain`, `system`이며 프로젝트 이름·전체 ID와 역할 ID 기반 목록을 제공합니다. 시스템의 `all` 범위는 프로젝트로 표시하지 않습니다. `count`는 프로젝트만이 아닌 모든 범위 항목의 수입니다.

검증된 요청자의 Keystone connection에서 대상 사용자를 확인하고 `user_id`, `effective=true`, `include_names=true`로 할당을 새로 조회합니다. 그룹 및 범위 상속은 Keystone이 확장하며 역할 암시 상속은 실제 역할 ID 그래프로 확장·중복 제거합니다. 프로젝트 이름이 응답에 없으면 해당 범위를 한 번만 직접 조회하며 전체 프로젝트·사용자 목록을 순회하지 않습니다. 역할 이름으로 관리자 여부·직접 할당·소유권을 추측하지 않습니다.

유효 상속 응답에서도 `scope`에는 대상 `project`와 `OS-INHERIT:inherited_to="projects"`가 함께 남을 수 있습니다. 범위 키(`project`/`domain`/`system`)는 정확히 하나인지 확인하고 상속 marker는 별도로 검증합니다. Marker를 프로젝트 이름·ID나 다른 범위로 해석하지 않습니다. Marker가 있는 경우 대상은 프로젝트여야 하며 잘못된 값·범위 혼합·알 수 없는 metadata는 `503`으로 거부합니다.

대상 사용자 부재는 `404`, 관리자 거부는 `403`, 공급자 장애·미완료 목록·불일치 metadata는 오류로 반환하며 성공한 빈 권한으로 축소하지 않습니다. 응답은 현재 조회 시점의 표시용 snapshot이고 토큰 발급·서비스 인가 입력이 아닙니다. 운영자가 Keystone에서 동시에 수정하는 동안 전체 directory를 원자적으로 고정하지는 않습니다.

---

## 프로젝트 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/projects` | 선택 domain inventory 검색·필터·최신 생성순 후 marker 페이지네이션 | 필수 query `domain_id` |
| `GET` | `/api/v1/admin/projects/names` | project id/name picker (페이지네이션 없음) | 선택 query `domain_id` |
| `POST` | `/api/v1/admin/projects` | 프로젝트 생성 (`201`) | `name`, `domain_id` 필수; `description`, `enabled` 선택 |
| `GET` | `/api/v1/admin/projects/{project_id}` | 프로젝트 상세 | - |
| `PATCH` | `/api/v1/admin/projects/{project_id}` | 프로젝트 수정 | `name`, `description`, `enabled` (선택) |
| `GET` | `/api/v1/admin/projects/{project_id}/deletion-check` | 대상 프로젝트의 실제 할당 리소스를 캐시 없이 검사 | - |
| `DELETE` | `/api/v1/admin/projects/{project_id}` | 새 리소스 검사를 통과한 빈 프로젝트만 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/projects/{project_id}/members` | 사용자·그룹 역할 할당 목록 | - |
| `GET` | `/api/v1/admin/projects/{project_id}/activity` | 프로젝트 활동 로그 | - |
| `POST` | `/api/v1/admin/projects/{project_id}/sync-monitoring-sg` | 모니터링용 보안 그룹 동기화 | - |
| `POST` | `/api/v1/projects/{project_id}/ownership-transfer/reconcile` | **관리자 전용이지만 `/admin` prefix 밖**; 원 native 요청 종료 확인 후 소유권 journal/readback 정산 | `operation_id`, `native_calls_settled:true` (strict boolean), 선택 `domain_id` (생략 시 현재 working domain) |

`GET /projects` query는 필수 non-empty `domain_id`, `limit`(기본20, 1–100), `marker`, `search`(이름·ID·설명의 trim/casefold 부분 검색), 선택 `enabled`를 받습니다. Domain inventory를 읽고 조건을 AND로 결합해 필터·정렬 후 페이지를 나눕니다. `{items,next_marker,count,total,domain_ids}`이며 total은 필터 결과 수, domain_ids는 검색 전 선택 domain inventory의 도메인 후보입니다. 마지막 next_marker는 null; 사라졌거나 현재 결과에 없는 marker는400입니다.

프로젝트·그룹 `created_at`은 Keystone의 유효한 시각을 우선하고, 없으면 해당 resource ID의 성공한 `project.create`/`project_create`/`identity.project.created` 또는 대응 group 생성 이벤트의 가장 이른 UTC 시각을 사용합니다. 수정·실패·단순 최초 활동 시각은 생성일로 사용하지 않습니다. UTC 마이크로초를 보존해 생성일 내림차순, 동률은 ID 내림차순으로 정렬하며 기록이 없거나 activity DB를 읽을 수 없으면 `null` 항목을 마지막에 둡니다. Afterglow 이전 또는 외부에서 생성된 항목, 수집되지 않았거나 보존기간 밖의 생성 이벤트는 생성 순서를 복원할 수 없습니다.

관리자 생성은 새 resource ID를 포함한 성공 이벤트를 기록합니다. 프로젝트 생성·수정·삭제와 셀프서비스 생성은 프로젝트 inventory 및 이름 cache를 무효화합니다. UI의 검색·상태·도메인 변경은 첫 페이지로 돌아가고, 백그라운드 갱신과 다음 페이지 prefetch는 현재 조건을 유지합니다.

같은 backend 프로세스·event loop에서는 mutation의 cache 무효화가 이전 조회 flight를 분리하고 늦은 snapshot의 cache 재저장을 막습니다. 무효화 이전 호출자는 이전 결과를 받을 수 있으나 이후 목록 조회는 그 작업에 합류하지 않습니다. 정상 cache I/O에 대한 국소 순서 보장이며 다른 worker의 진행 중 조회까지 fence하는 분산 보장은 아닙니다.

`GET /projects/{project_id}/members` 응답에는 사용자 할당과 그룹 할당(`type: "group"`, `group_id` 포함)이 함께 반환됩니다.

### 생성·활성화와 단일 소유권

`POST /admin/projects`는 대상 domain의 canonical Default와 활성 manager가 없으면 `409 domain_default_bootstrap_required` / `domain_default_manager_required`입니다. `Default`(case-insensitive) 이름은 예약됩니다. 공유 role-graph lease 아래 새 프로젝트를 **disabled**로 만들고 정확한 새 ID/domain/name을 확인한 뒤 실제 생성자를 단일 직접 `project_owner`로 초기화합니다. 이 privileged 생성은 verified system admin이 아직 가입하지 않은 대상 domain에도 새 프로젝트의 owner membership을 설정할 수 있지만 기존 project의 owner를 덮어쓰는 API는 아닙니다. Manager 읽기 projection과 domain quota defaults/budget를 검증하고 요청 `enabled`(기본true)를 마지막에 반영합니다. 응답은 `{id,name,description,enabled,domain_id}`입니다. 실패 보상은 이번 시도의 정확한 새 ID만 disable·readback·빈 프로젝트 검사 후 삭제하며 불확실하면 `503 created_project_cleanup_unavailable`로 남깁니다.

셀프서비스 `POST /api/v1/projects`는 현재 joined domain의 live manager 또는 domain-scoped `project_creator` capability가 필요하고 동일하게 owner/default quota 확인 후 활성화합니다. 이 경로의 불확실한 생성은 blind retry/삭제하지 않고 관리자에게 보이는 disabled 프로젝트로 남을 수 있습니다. `PATCH /admin/projects/{id}`의 재활성화도 unresolved owner journal, managed project의 unique owner, 현재 domain allocation을 검사하지만 **미래-project defaults를 기존 project에 재적용하지 않습니다**. Default의 rename/disable/delete는 `422 domain_default_is_immutable`입니다.

Owner는 한 명의 직접 canonical `project_owner`여야 합니다. admin/member/reader는 여러 명일 수 있으나 `manager > owner`는 domain 관리 우선순위이지 manager→project_owner 전역 inference가 아닙니다. 기존 group/inherited/multiple owner 충돌에서 임의 owner를 고르거나 자동 revoke하지 않습니다. Generic admin role assign/revoke·group mutation·owner-bearing implication은 이 workflow를 우회할 수 없습니다.

소유권 조회와 이전은 [프로젝트 API](projects.md)의 `GET /api/v1/projects/{id}/ownership`, `POST /api/v1/projects/{id}/ownership-transfer` (`{user_id}`)입니다. 현재 sole owner 또는 live domain manager가 활성 joined 사용자를 대상으로 수행하며 system admin flag만으로 이 scoped 이전 권한을 얻지 않습니다. 조회는 `{project_id,owner_user_id,status,owners,transfer_operation,can_transfer,can_delete}`이며 ownership status는 `unique/conflict/missing`입니다. SQL journal은 native revoke/grant **전에** 단계별 intent를 저장하고 새 owner를 unique로 readback한 뒤 `completed`가 됩니다. 실패·응답 유실은 `unknown`, 진행 중은 `applying`이며 새 이전·삭제·관련 변경을 `409 project_ownership_native_operation_unresolved`로 막습니다.

관리자 정산 route는 exact operation/project/domain과 fresh system authority를 확인합니다. `native_calls_settled:true`는 타임아웃된 원 호출이 더 이상 실행 중이지 않다는 **운영자 확인**이지 현재 GET만으로 추론하는 값이 아닙니다. 정산은 native 권한을 쓰지 않으며 unique 관측은 실제 owner가 기존/요청 owner와 달라도 그대로 받아 `completed`로 기록합니다. 초기 owner grant에서 old=target이고 관측이 missing인 경우에도 `completed`로 정산하지만 activation은 unique owner를 별도 요구합니다. 그 외에는 `settled`로 남고 삭제는 계속 차단됩니다. 재개는 같은 from/to 대상만 허용하며 conflict를 자동 해결하지 않습니다. 정산 응답의 `can_transfer/can_delete`는 false이므로 새 scoped ownership 조회로 실제 권한을 다시 판단하세요.

### 프로젝트 삭제 전 리소스 재확인

프로젝트 목록에서 삭제를 선택하면 기존 확인 modal 안에서 새 검사를 시작합니다. 검사 중에는 삭제가 비활성화되고, 남은 리소스 수와 유형별 최대 5개 이름·ID, 조회 실패 사유를 표시합니다. **리소스 다시 확인**은 이전 빈 결과를 폐기하고 새로 조회합니다. 선택 프로젝트·사용자·인증 프로젝트·토큰 변경이나 modal 닫기 뒤의 늦은 결과는 사용하지 않습니다. 긴 결과 목록만 `40dvh` 안에서 스크롤하여 취소·삭제 버튼을 유지합니다.

두 endpoint는 검증된 요청자의 `get_os_conn`을 그대로 사용합니다. 쿼터·dashboard cache·프런트엔드 서비스 활성화 flag는 빈 프로젝트의 증거가 아닙니다. 각 공급자의 모든 페이지와 실제 소유권을 확인하며, 중지·오류·shelved VM과 연결되지 않은 `available` 볼륨도 포함합니다. 명시적으로 다른 프로젝트 소유인 공유·외부 리소스는 제외하지만 대상 소유인 외부 네트워크는 포함합니다.

검사 범위는 다음 28개 cloud 유형에 **Keystone `child_projects` 검사**를 더합니다. 핵심 서비스는 필수이고, 선택 서비스는 **인증된 catalog에서 부재가 확인된 경우에만** 건너뜁니다. Child 목록 전체를 읽고 ID/parent_id를 확인하며 불확실하면 `status:"unavailable"`, `reason:"project_hierarchy_unavailable"`로 차단합니다.

| 서비스 | 검사 유형 |
|---|---|
| Nova | `instances`, `server_groups` |
| Cinder | `volumes`, `volume_snapshots`, `volume_backups` |
| Neutron | `networks`, `subnets`, `routers`, `ports`, `floating_ips`, `security_groups` |
| Glance | `images` — hidden/visible 두 구간과 community/shared 이미지 포함 |
| Octavia | `load_balancers` |
| Manila | `shares`, `share_snapshots`, `share_networks`, `security_services` |
| Swift/RGW | `object_containers` — 빈 컨테이너·segment/trash 등도 포함 |
| Barbican | `secrets`, `secret_containers`, `secret_orders` — payload는 조회·반환하지 않음 |
| Trove | `database_instances`, `database_backups`, `database_configurations` |
| Zun | `containers` |
| Magnum | `clusters`, `cluster_templates` |
| Heat | `stacks` — nested/hidden stack 포함 |

대상 소유 보안 그룹 중 `name=default`인 한 개만 자동 baseline 예외로 제외합니다. 공개 API의 이름 판정이며 DB `is_default` 판정을 주장하지 않습니다. 같은 이름의 대상 소유 그룹이 여러 개면 소유권이 모호한 것으로 차단합니다. Neutron은 GET 과정에서 자동 기본 그룹을 보장할 수 있지만 검사기가 명시적 자원 생성·삭제를 요청하지는 않습니다.

#### 다른 프로젝트를 조회하는 관리자 인증 범위

관리자 목록의 대상 프로젝트와 토큰의 실제 프로젝트는 다를 수 있습니다. 논리적 `X-Project-Id`만으로 account-scoped 목록을 대상 소유라고 추정하거나 서비스 password로 재인증하지 않습니다.

**native admin 전제:** Afterglow 시스템 관리자 판정은 Keystone `system:all` 등 별도 역할 할당을 사용하지만 공급자는 요청의 project-scoped 토큰을 인가합니다. Cinder `all_tenants`, Neutron `project_id`, Glance `owner`, Heat 목록은 관리자 문맥이 없으면 HTTP 200으로 호출자 범위만 반환할 수 있습니다. 따라서 토큰에 `admin` 역할(대소문자 무시)과 `is_admin_project=true`(Keystone이 값을 생략하면 기본 `true`)가 없으면 공급자 조회 없이 28개 유형 전체를 `admin_authority_unverified`로 반환하고 DELETE는 `503`입니다. UI는 admin 역할이 있는 관리자 프로젝트로 전환한 뒤 재확인하라고 안내합니다.

| 서비스 | 다른 프로젝트 검사 정책 |
|---|---|
| Trove DB | `/mgmt/instances` 관리자 목록에서 실제 owner를 검사 |
| Trove 백업 | `/backups?all_projects=True&project_id=<target>` 관리자 조회 후 owner 재검사 |
| Trove 구성 | 관리자 전체 목록을 확인하지만 2025.2 목록 응답은 owner를 반환하지 않음. 행이 있으면 target token이어도 `resource_ownership_unverified`; 빈 전체 목록만 빈 것으로 인정 |
| Magnum | 관리자 전체 목록 사용. cluster는 owner를 유지하는 `/clusters/detail`, template은 `/clustertemplates`; 실제 `project_id` 검사 |
| Heat | 기본 정책이 `deny_everybody`인 `global_tenant`는 쓰지 않음. 관리자 문맥의 일반 `/stacks?tenant=<target>&show_nested=True&show_hidden=True`가 반환하는 `project`를 검사 |
| Swift/RGW | 실제 토큰 프로젝트가 대상과 같고 account endpoint가 `AUTH_<target>`인 경우만 검사 |
| Barbican | 실제 토큰 프로젝트가 대상과 같은 경우만 프로젝트의 secret/container/order 목록 검사 |

권한 부족·정책 거부·소유권 누락은 빈 목록으로 축소하지 않습니다. Swift/Barbican의 범위 불일치는 **관리자 범위에서 확인 불가**와 대상 프로젝트에 admin 역할이 있는 관리자 계정으로 프로젝트를 전환한 뒤 재확인하라는 조치를 표시합니다. 역할을 자동 부여하지 않으며, 권한이 없으면 삭제는 계속 차단됩니다. Trove 구성은 cloud 어디에든 구성 그룹이 있으면 owner를 확인할 수 없어 차단될 수 있으며, target token으로도 보완되지 않습니다. 강제 우회는 없습니다. Heat는 공급자의 `context_is_admin` 기본값(`role:admin and is_admin_project:True`)과 Afterglow 전제가 일치한다고 가정합니다. 이 정책을 변경한 배포에서 빈 결과는 검증 공백입니다.

관련 공급자 계약: [Trove 백업 관리자 조회](https://raw.githubusercontent.com/openstack/trove/stable/2025.2/trove/backup/service.py), [Trove 구성 전체 조회](https://raw.githubusercontent.com/openstack/trove/stable/2025.2/trove/configuration/models.py)와 [소유권 미제공 응답](https://raw.githubusercontent.com/openstack/trove/stable/2025.2/trove/configuration/views.py), [Magnum cluster detail/관리자 목록](https://raw.githubusercontent.com/openstack/magnum/stable/2025.2/magnum/api/controllers/v1/cluster.py), [Heat 목록](https://raw.githubusercontent.com/openstack/heat/stable/2025.2/heat/api/openstack/v1/stacks.py)·[global_index 정책](https://raw.githubusercontent.com/openstack/heat/stable/2025.2/heat/policies/stacks.py)·[관리자 tenant 필터](https://raw.githubusercontent.com/openstack/heat/stable/2025.2/heat/db/api.py).

#### 응답과 최종 삭제

GET은 검사 결과가 차단이어도 `200`과 `{project_id, checked_at, can_delete, resources}`를 반환합니다. `checked_at`은 검사 완료 UTC 시각이며 원자적 cloud snapshot을 뜻하지 않습니다. `resources`의 각 항목은 `{kind, service, status, count, samples, reason}`입니다.

| `status` | `count` | 의미 |
|---|---|---|
| `ok` | 0 이상의 정수 | 해당 유형의 전체 조회와 대상 소유권 검사 완료 |
| `unavailable` | `null` | 조회·전체 페이지·소유권·인증 범위를 확인하지 못함. 0개가 아님 |
| `skipped` | `null` | 인증된 catalog에서 선택 서비스가 없음 (`service_not_present`) |

샘플은 제한된 ID·이름·상태만 반환합니다. 조회 실패 시 부분 count/샘플은 폐기하고 원본 provider 오류·토큰·endpoint URL·secret payload는 공개하지 않습니다. 공개 사유는 `resource_check_failed`, `resource_ownership_unverified`, `admin_authority_unverified`, `project_scope_unverified`, `service_catalog_unavailable`, `service_not_present`와 child 검사 `project_hierarchy_unavailable`입니다.

DELETE는 GET 결과의 시각이나 UI 확인 여부에 의존하지 않고 같은 검사를 **다시 수행**합니다. 하나라도 `unavailable`이면 잔여 리소스 유무보다 불확실성을 우선하여 `503`, 확인된 할당이 남으면 `409`입니다. 오류 `detail`은 `{code, message, check}`이며 code는 각각 `project_resource_check_failed` / `project_has_resources`입니다. 어느 경우에도 Keystone DELETE를 호출하지 않습니다. 모든 적용 항목이 `ok/count=0` 또는 확인된 `skipped`인 경우에만 정확한 프로젝트를 삭제하고 inventory/name cache를 무효화합니다. UI는 최종 거부 보고서를 표시하며 확인 창을 유지합니다. 취소된 검사 thread가 끝나기 전에 요청 connection을 닫지 않고, 검사 도중 요청 취소는 Keystone 삭제를 예약하지 않습니다.

관리자 `GET /projects/{id}/deletion-check`와 DELETE는 모두 resource/child 검사 전에 정확한 native 프로젝트, Default 불변식과 unresolved owner journal을 확인합니다. Default는 `422 domain_default_is_immutable`, 미해결 ownership operation은 `409 project_ownership_native_operation_unresolved`로 차단합니다. Preflight는 조회 시점의 결과이지 이후 삭제를 예약하거나 허가하는 token이 아니므로 최종 DELETE에서 모든 검사를 다시 수행합니다. Scoped 셀프서비스 삭제는 domain manager 또는 `project_creator` capability를 가진 현재 sole owner만 가능하며, 그 경로도 새 inventory와 직전 live authority를 다시 확인합니다. System-admin DELETE에 creator/sole-owner 조건을 추가 적용하는 것은 아닙니다.

**한계:** 자원 자동 정리·force 옵션·cloud-wide freeze는 없습니다. 최종 재검사는 이전 확인 결과의 stale race를 줄이지만 독립 서비스 간 분산 트랜잭션이 아니므로 마지막 조회 뒤 새 자원이 생성되는 경쟁까지 제거하지 않습니다.

---

## 쿼터 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/quotas/{project_id}` | 대상 프로젝트의 Nova·Cinder·Neutron·선택적 Manila 쿼터 한도와 사용량 조회 |
| `PUT` | `/api/v1/admin/quotas/{project_id}` | 요청 본문에 포함된 쿼터만 대상 프로젝트에 적용 |

`GET` 응답의 `compute`, `volume`, `network`, `file_storage`는 각 서비스의 `{필드명: {limit, in_use, reserved?}}` 객체입니다. `limit: -1`은 무제한, 0은 실제 0 한도이며 사용량·예약량과 다릅니다. `reserved`는 공급자가 유효한 비음수 정수로 제공할 때만 포함하며 누락을 0으로 채우지 않습니다. 상세 사용량을 조회하지 못한 서비스는 **`null`**이며 `availability[서비스] = false`, `errors[서비스] = "quota_unavailable"`입니다. Manila가 비활성화되었으면 `file_storage: null`과 `errors.file_storage = "service_disabled"`입니다. 배포 환경이 노출하지 않는 개별 필드는 생략하므로 해당 항목을 조정할 수 없습니다. 다른 서비스 조회 실패가 정상 서비스의 쿼터를 숨기지는 않습니다.

| 서비스 | `GET` 필드 (프로바이더 이름) | `PUT` 필드 (변경할 항목만 전송) |
|--------|------------------------------|-----------------------------------|
| `compute` (Nova) | `instances`, `cores`, `ram` (MB), `metadata_items`, `key_pairs`, `server_groups`, `server_group_members`, `injected_files`, `injected_file_content_bytes`, `injected_file_path_bytes` | 동일 |
| `volume` (Cinder) | `volumes`, `snapshots`, `gigabytes` (볼륨·스냅샷의 총 GiB) | 동일 |
| `network` (Neutron) | `network`, `subnet`, `port`, `router`, `floatingip`, `security_group`, `security_group_rule` | 동일 |
| `file_storage` (Manila) | `shares`, `gigabytes`, `snapshots`, `snapshot_gigabytes`, `share_networks`, `share_groups`, `share_group_snapshots` | `shares`, `share_gigabytes`, `share_snapshots`, `share_snapshot_gigabytes`, `share_networks`, `share_groups`, `share_group_snapshots` |

```json
{
  "project_id": "project-uuid",
  "compute": {"instances": {"limit": 20, "in_use": 5}, "cores": {"limit": 40, "in_use": 10}, "ram": {"limit": 81920, "in_use": 20480}},
  "volume": {"volumes": {"limit": 10, "in_use": 3}, "snapshots": {"limit": 10, "in_use": 2}, "gigabytes": {"limit": 1000, "in_use": 200}},
  "network": {"security_group": {"limit": 20, "in_use": 4}, "security_group_rule": {"limit": 100, "in_use": 12}},
  "file_storage": {"shares": {"limit": 10, "in_use": 2}, "share_groups": {"limit": 5, "in_use": 1}},
  "availability": {"compute": true, "volume": true, "network": true, "file_storage": true},
  "errors": {}
}
```

`PUT`은 최상위 JSON **strict 정수** 필드로 한도 `-1` 이상을 받습니다. 빈 본문·`null`·미지원 필드는 `422`이며 생략한 필드는 변경하지 않습니다. 이 route, `/api/v1/admin/compute-policy/{project_id}`의 Nova 변경, manager project quota 변경, 일반/Default/개인-domain 프로젝트 생성의 defaults 적용은 **공통 `domain_quotas` orchestration과 `quota_native` transport**를 사용합니다. 관리자 직접 수정도 domain budget를 우회하지 않습니다. GPU DB 한도/flavor access는 별도 정책이며 compute-policy는 Nova 결과가 verified updated가 아니면 후속 GPU/access 효과를 진행하지 않습니다.

공유 renewable role-graph lease를 바깥 경계로 두고 SQL policy/journal을 사용합니다. 변경 전 disabled 프로젝트를 포함한 **모든 domain 프로젝트의 native limit**을 읽어 대상 값만 치환해 합산합니다. 지정 finite ceiling에서 unknown/unlimited는 `409 quota_budget_unverifiable:<field>`, 초과는 `409 quota_budget_exceeded:<field>`이며 대상 필드 native 조회 불가는 쓰기 전 `503 quota_native_preflight_unavailable`입니다. 외부 관리자 drift는 증가를 허용하지 않되 검증 가능한 strictly decreasing repair를 허용할 수 있습니다. SQL/lease 장애에서는 fail-closed이며 서로 독립적인 서비스들을 원자적 transaction으로 주장하지 않습니다.

각 서비스의 `writing` intent를 durable 저장한 후 native PUT을 재시도 없이 한 번 보내고 성공/예외 모두 readback합니다. 값 일치만 verified updated에 포함합니다. 예외 뒤 readback이 일치해도 원 호출 종료 증거가 아니므로 `unknown`이며 뒤 서비스는 pending/not_attempted로 멈춥니다. 정상 응답 뒤 불일치는 `partial`입니다. `status`는 `updated/partial/unknown`, `updated`는 검증된 서비스 목록, `errors`는 `native_outcome_unknown`, `native_readback_mismatch`, `native_readback_unavailable`, `not_attempted` 등입니다. HTTP 성공만으로 전체 완료를 판단하지 말고 operation 상태와 새 quota GET을 확인하세요.

```json
{"status":"updated","project_id":"project-uuid","domain_id":"domain-uuid","operation_id":"operation-uuid","updated":["network"],"errors":{}}
```

### Domain allocation budget·기본값·작업 정산

| 메서드·경로 | 권한·입력 | 응답/효과 |
|---|---|---|
| `GET /api/v1/admin/domains/{domain_id}/quotas` | verified system admin, exact domain ID | domain allocation snapshot |
| `PUT /api/v1/admin/domains/{domain_id}/quotas` | system admin; `{revision,ceilings:{quota_key:limit}}` | ceiling map 전체 교체·revision 증가 후 snapshot |
| `POST /api/v1/admin/domains/{domain_id}/quotas/operations/{operation_id}/reconcile` | system admin; `{native_calls_settled:true}` strict boolean | 원 호출 종료 확인 후 native readback으로 journal 정산·snapshot |
| `GET /api/v1/iam/quotas` | 현재 working-domain manager | 같은 domain allocation snapshot |
| `PUT /api/v1/iam/quotas/defaults` | manager; `{revision,defaults:{quota_key:limit}}` | 미래-project default map 전체 교체; 기존 project 변경 없음 |
| `GET /api/v1/iam/projects/{project_id}/quotas` | manager; project가 현재 domain에 속해야 함 | 위 공통 native quota DTO |
| `PUT /api/v1/iam/projects/{project_id}/quotas` | manager; flat quota patch | 위 durable operation 응답 |

Ceilings/defaults key는 위 PUT 필드와 같은 **API 이름**(예: Manila `share_gigabytes`)이고 값은 strict integer ≥ -1입니다. Revision은 strict integer ≥ 0이며 stale revision은 `409 quota_policy_revision_conflict`입니다. 두 policy body는 extra field를 거부합니다. 전체 map 교체이므로 빈 map은 해당 정책을 비우며 누락 key는 별도 ceiling/default가 없다는 뜻입니다. Ceiling `-1` 또는 미설정은 Afterglow allocation 제한 없음이지 공급자의 프로젝트 quota가 무제한이라는 뜻이 아닙니다. Defaults의 finite ceiling 초과/무제한은 `409 quota_default_exceeds_ceiling:<field>`이고 ceiling 축소도 기존 allocation·defaults를 확인합니다. Defaults를 저장할 때 남은 전체 budget를 예약하지 않으므로 실제 생성 시 allocation이 안 맞으면 생성을 활성화하지 않습니다. 새 disabled 프로젝트에 defaults를 적용하되 생략 필드는 native 기본 한도로 남고 그 실제 한도도 ceiling 계산에 포함합니다.

Snapshot은 `{domain_id,revision,ceilings,defaults,enforcement_scope,allocations,projects,operations,allocation_blocked,blocking_operation_id,drift,defaults_future_only}`입니다. 기본 policy는 revision0/빈 map이고 `enforcement_scope="afterglow_project_allocations"`, `defaults_future_only=true`입니다. `allocations[quota_key]={limit,status,error?,within_budget}`는 **limit 합계**이며 사용량 합계가 아닙니다. `status=ready/unlimited/unavailable`, limit은 유한 합계/-1/null, within_budget은 true/false/null을 구분합니다. Drift는 현재 관측에서 false인 항목이 있을 때 true이므로 drift=false가 unknown 항목의 정상 증거는 아닙니다. `projects`는 enabled/disabled를 모두 포함한 `{id,name,enabled}` 목록입니다. 외부 native 관리자의 쓰기는 이 lease를 따르지 않으므로 universal native domain usage cap이나 cloud 전체 enforcement를 보장하지 않습니다.

`operations`는 unresolved 우선·최신순 최대50개 `{id,project_id,status,requested,sections,created_at}`이며 원 요청의 secret은 없습니다. `applying/unknown` 하나라도 있으면 해당 domain의 다음 quota/default/ceiling 변경과 생성 allocation 검증은 `409 quota_native_operation_unresolved`로 막힙니다. `partial`의 verified 효과는 자동 rollback하지 않습니다. 정산은 운영자가 원 native 호출 종료를 확인한 뒤 실행하며 **재전송/재시도/원 요청값 강제 적용이 아닙니다**. 실제 관측값을 `observed`로 수용하고 pending은 `not_attempted`, 보상 삭제된 프로젝트는 native GET 404와 domain inventory 부재를 함께 확인해 `project_deleted`로 기록합니다. Readback 불가는 `503 quota_native_readback_unavailable`로 fence를 유지하고 성공은 `reconciled`로 해제하되 drift는 계속 표시합니다. 정산 뒤 snapshot과 프로젝트 quota GET으로 현재 한도를 읽고 필요한 후속 변경을 새 요청으로 결정하세요.

---

## 그룹 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/groups` | 선택 domain 그룹 목록, nullable 생성일·최신순 | 필수 query `domain_id` |
| `POST` | `/api/v1/admin/groups` | 그룹 생성 (`201`) | `name`, `domain_id` 필수; `description` 선택 |
| `PATCH` | `/api/v1/admin/groups/{group_id}` | 그룹 수정 | `name`, `description` (선택) |
| `DELETE` | `/api/v1/admin/groups/{group_id}` | 그룹 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/groups/{group_id}/users` | 그룹 멤버 목록 | - |
| `GET` | `/api/v1/admin/groups/{group_id}/candidates` | 명시한 계정 소속 도메인의 활성 사용자 후보 | 필수 query `domain_id`, `user_domain_id` |
| `PUT` | `/api/v1/admin/groups/{group_id}/users/{user_id}` | 그룹에 사용자 추가 (`204`) | 선택 query `user_domain_id`; 명시 시 `domain_id` 필수 |
| `DELETE` | `/api/v1/admin/groups/{group_id}/users/{user_id}` | 그룹에서 사용자 제거 (`204`) | - |

그룹 응답은 배열이며 nullable `created_at`을 포함합니다. 필수 domain_id는 서버에서 native inventory를 제한합니다. 이름·ID·설명 검색은 그 inventory에서 브라우저가 수행합니다. 조회·갱신 후 조건을 유지하며 mutation은 inventory cache를 무효화합니다. Native 실패는 `identity_native_denied`403 / `identity_not_found`404 / `identity_unavailable`503 등으로 반환하며 부분 성공 목록으로 바꾸지 않습니다.

기본 검색은 기존 `/domains/{domain_id}/members`의 home/joined 후보를 사용합니다. 특정 다른 계정 소속 도메인을 선택하면 `/groups/{group_id}/candidates?domain_id=<group-domain>&user_domain_id=<identity-home>`에서 `{domain_id,user_domain_id,items:[{id,name,email,enabled,domain_id}]}`를 받습니다. 최상위 두 ID는 각각 group 소유 domain과 선택한 identity home이며 item domain은 후자와 정확히 일치합니다. Accounts도 조회할 수 있지만 전역/all-domain 목록이나 조직 manager 권한으로 노출하지 않습니다. 응답은 `Cache-Control: no-store, private`; exact enabled group/두 domain 확인 뒤 native source-domain LIST의 고유 ID·정확한 home·boolean enabled·name/email 형식을 검증해 활성 후보를 구성합니다. 사용자별 GET은 하지 않으며 LIST/provider403/5xx·home404·불명/중복/잘못된 metadata는 부분 성공으로 숨기지 않습니다. 목록은 조회 시점 후보이지 추가 권한 proof가 아니므로 이후 삭제·비활성·home 변경은 다음 명시 PUT의 fresh exact 검증에서 거부됩니다.

명시 `user_domain_id` PUT은 graph lease 안에서 native system-admin을 다시 검증하고 group anchor·활성 source/target domain·정확한 활성 사용자 UUID/home을 재조회합니다. Group 자신의 domain에 아직 가입하지 않은 Accounts 사용자도 이 명시 작업으로 추가할 수 있고 기존 group 역할이 적용됩니다. Group의 다른 domain project/domain grant에는 기존 membership을 계속 요구합니다. Source ID를 생략한 기존 PUT·일반 조직 IAM/credential/role API는 바뀌지 않습니다. Owner-bearing group409·projection group403·마지막 manager/system-admin·권위/lease/native 실패 보호를 유지하며 별도 역할을 자동 부여하거나 계정을 이동하지 않습니다. Browser source 선택은 관리 domain/workspace를 변경하지 않고 늦은 source 응답과 ABA를 폐기합니다.

**주의**: 멤버십 변경 시 Keystone이 관련 토큰을 revoke할 수 있어 관련 세션 캐시가 함께 삭제됩니다.

---

## 역할·시스템 역할 관리

프로젝트 스코프 역할(assign/assign-group)과 시스템 스코프 역할(system-roles)을 구분해 관리합니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/roles` | 실제 역할과 직접·간접 상속을 매번 native 조회 | - |
| `GET` | `/api/v1/admin/roles/presets` | 변경 없는 프로젝트/서비스 역할·상속 프리셋 미리보기 | - |
| `POST` | `/api/v1/admin/roles/presets/apply` | 기존 ID를 재사용하는 명시적 멱등 프리셋 적용 | 시스템 관리자 확인 뒤 호출 |
| `POST` | `/api/v1/admin/roles` | 역할 생성 (`201`) | `name`, 선택 `description`, `domain_id` (body) |
| `PATCH` | `/api/v1/admin/roles/{role_id}` | 이름·설명 편집 | 변경할 `name` 또는 `description` (body); 도메인은 변경 불가 |
| `DELETE` | `/api/v1/admin/roles/{role_id}` | 할당·연결이 없는 역할 삭제 | - |
| `PUT` | `/api/v1/admin/roles/{prior_role_id}/implies/{implied_role_id}` | 직접 하위 역할 선택·연결 | 상위·하위의 정확한 역할 ID |
| `DELETE` | `/api/v1/admin/roles/{prior_role_id}/implies/{implied_role_id}` | 해당 직접 연결만 해제 | 간접 상속 경로는 유지될 수 있음 |
| `POST` | `/api/v1/admin/roles/assign` | 사용자에게 프로젝트 역할 할당 | `user_id`, `project_id`, `role_id` (body) |
| `DELETE` | `/api/v1/admin/roles/assign` | 사용자 프로젝트 역할 회수 | `user_id`, `project_id`, `role_id` (query) |
| `POST` | `/api/v1/admin/roles/assign-group` | 그룹에 프로젝트 역할 할당 | `group_id`, `project_id`, `role_id` (body) |
| `DELETE` | `/api/v1/admin/roles/assign-group` | 그룹 프로젝트 역할 회수 | `group_id`, `project_id`, `role_id` (query) |
| `GET` | `/api/v1/admin/identity/system-roles` | 시스템 스코프 역할 할당 목록 | - |
| `POST` | `/api/v1/admin/identity/system-roles/grant` | canonical system:all admin 부여 | `{user_id}` |
| `POST` | `/api/v1/admin/identity/system-roles/revoke` | 직접 system:all admin 회수 | `{user_id}` |
| `GET` | `/api/v1/admin/identity/security-policy` | count-only 응답 `{system_admin_count}` | - |
| `GET` | `/api/v1/admin/identity/summary` | identity 도메인 요약(사용자·프로젝트·역할 수) | - |

역할 CRUD·상속·프리셋 적용은 verified system admin 전용입니다. 프로젝트 `admin` 이름이나 DB manager는 권한이 아닙니다. 프로젝트 owner/admin은 [프로젝트 API](projects.md), 도메인 관리자는 [도메인 IAM](iam.md)의 현재 safe role ID를 사용합니다. 일반 identity 응답은 표시용 이름·OpenStack can_write·서비스별 service_permissions를 구분합니다. 초대 role_ids도 IAM의 safe catalog로 검증합니다.

프로젝트 `POST /roles/assign`·`/roles/assign-group`는 native 이름이 `admin`인 실제 role ID의 새 할당을422 `Native admin project grants are removal-only`로 거부합니다. 기존 user/group direct admin은 해당 DELETE로 회수할 수 있고 관리자 UI도 이미 체크된 admin만 해제할 수 있습니다. 미할당 admin은 비활성이고 해제 뒤 재선택할 수 없습니다. 사용자/도메인 IAM replacement·초대에도 신규 admin grant가 허용되지 않으며 `project_admin`·서비스 `*_admin`의 기존 정책은 유지합니다. 예외는 전용 `/identity/system-roles/grant`·`/revoke`의 canonical `system:all` admin이며 기존 마지막 유효 관리자 보호·세션 회수 계약을 그대로 따릅니다.

목록 항목은 `id`, `name`, `description`, `domain_id`, `protected`, `system_only`, `implied_role_ids`(직접 하위), `inherited_role_ids`(전체 하위), `parent_role_ids`(직접 상위)를 반환합니다. `A → B`는 A 보유자가 B 권한을 얻는다는 뜻입니다. 화면의 `admin → manager → member → reader`는 실제 Keystone에 저장된 연결을 표시하며, 목록 조회로 기본 계층을 자동 생성하지 않습니다. 이름·ID·상속 수 정렬, 이름/ID/설명 검색, 다중 부모·공유 역할을 표시하는 상속 트리를 제공합니다.

새 역할 및 이름 변경은 `area_grade` 형식입니다. 영역과 등급을 각각 소문자로 바꾸고 연속 공백을 `-`로 치환합니다(경계 공백도 동일). 예: `My Area_Read Only` → `my-area_read-only`. UI는 영역/등급 입력과 전송될 정확한 이름을 미리 보여줍니다. native core 역할과 `project_owner`는 이름 변경·삭제를 보호합니다.

프리셋 미리보기는 읽기 전용이며 `roles`, `project_roles`, 추가할 native project `implications`, 제거 대상인 과거 관리 서비스 `retired_implications`를 반환합니다. **Native 서비스 정책을 먼저 배포해야 합니다.** 적용은 부족한 role·native project edge만 추가하고 정확히 이전 프리셋에서 생성한 서비스 edge를 제거합니다. 기존 role ID·직접 할당·운영자 custom edge는 보존합니다. 현재 그래프와 제거 후 그래프의 전역 binding·권한 ceiling을 첫 native 변경 전에 검증하고 삭제 readback을 확인합니다. 중간 실패는 `created_roles`, `created_implications`, `removed_implications`와 원인을 반환하므로 현재 목록을 새로 확인한 뒤 재시도합니다. 이미 없는 edge를 다시 삭제하거나 role을 재생성하지 않습니다.

독립적인 서비스 grade role 이름은 `<service>_admin/editor/user/reader`, 세부 role은 `<service>-<area>_<grade>`입니다. Grade는 Keystone에서 leaf로 확장하지 않고 서비스의 `policy.yaml`에서 action에 직접 대응합니다. 운영자는 기본 admin/editor/user/reader 규칙을 표준 `oslo.policy` 문법으로 override할 수 있습니다. 서비스 admin이나 프로젝트 admin 이름만으로 system-only API·builder/GC·외부 native provider 권한을 얻지 않습니다. 일반 역할 assign/assign-group API에서 owner 계층을 우회할 수 없으며 소유권은 프로젝트 전용 workflow를 사용합니다.

서버는 최신 그래프와 endpoint별 Redis lease 아래 변경을 검사합니다. 자기 상속·직접/간접 순환·기본 역할의 역방향 승격·사용자 정의 역할의 `admin`/`manager` 상속은 `409`입니다. 도메인 역할은 같은 도메인 또는 전역 하위 역할만 상속할 수 있고, 전역 역할은 전역 하위 역할만 상속할 수 있습니다. 기본 네 역할은 이름 변경·삭제가 금지되며 설명과 안전한 하위 연결만 편집합니다. 역할 삭제는 사용자·그룹 할당이나 직접 상위/하위 연결이 있으면 `409`, 대상이 없으면 `404`, 그래프·잠금·변경 완료 검증이 불가능하면 `503`입니다. Native 반영 뒤 응답이나 readback이 실패할 수 있으므로 오류 이후 재시도 전에 목록을 새로 확인합니다.

시스템 관리자는 프리셋 이름 밖의 전역 사용자 정의 역할도 명시적으로 연결할 수 있습니다. 예를 들어 `project_reader → audit`는 실제 그래프에 저장되며 기존 상위 `project_member/project_admin/project_owner`에도 전이됩니다. 프리셋 재적용은 승인된 custom edge를 보존합니다. 다만 custom 이름을 경유해 core/project/서비스의 알려진 권한 경계를 넘거나 도메인 역할을 섞는 연결은 계속 거부합니다. `audit`이라는 이름만으로 native 정책의 읽기 전용 권한을 보증하지 않으므로 운영자는 연결 전 해당 서비스 policy를 검토해야 합니다. 일반 `project_reader` 사용자에게 전역 역할 편집 권한을 부여하는 기능이 아닙니다.

프로젝트 직접·그룹 role 할당, 역할명·상속 연결 변경은 관련 권위·역할·기존 토큰 검증 cache를 무효화하고 감사를 남기며, Afterglow 로그인 family를 일괄 폐기하지 않습니다. 새 요청은 현재 native 권한으로 검증하므로 회수된 권한을 다음 로그인까지 유지하지 않습니다. HTTP 요청 취소 이후에도 이미 진행된 변경과 후속 정리를 끝냅니다. Native가 그룹 멤버 제거 등으로 사용자 전체 로그인 증명을 회수하면 재로그인이 필요하며 이를 우회하지 않습니다. 목록 조회 실패를 빈 정상 목록으로 바꾸지 않으며, UI는 이전 행을 남기되 최신 조회가 성공할 때까지 변경을 비활성화합니다. Lease는 Afterglow 간 변경을 직렬화할 뿐 Keystone CLI 등 외부 변경을 잠그는 분산 트랜잭션은 아닙니다. 아래 명시적 시스템 권한 grant/revoke와 사용자 세션 폐기는 별도의 기존 보안 회수 경계를 유지합니다.

시스템 grant/revoke는 공유 role-graph lease를 사용하며 contention은409입니다. 성공은200 `{status:"granted"|"revoked"}`이고 대상 세션 회수·authority cache 무효화를 수행합니다. 직접 grant가 없는 revoke는404 `system_admin_grant_not_found`, 마지막 enabled effective admin을 없애는 회수는422입니다. Group/inherited authority도 마지막 관리자 판정에 반영합니다. `security-policy`는 실제 system:all 직접 admin 목록 수 `{system_admin_count}`만 반환하며 password/lockout 설정을 노출하지 않습니다. `migrate-from-project`는 제거되었고 project admin을 system admin으로 자동 승격하는 API는 없습니다.

---

## Flavor 관리

> 태그: `admin-flavors`

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/flavors` | 전체 flavor 목록(공개+비공개) | `limit`, `marker`, `is_public` (query) |
| `POST` | `/api/v1/admin/flavors` | flavor 생성 (`201`) | `name`, `vcpus`, `ram`(MB), `disk`(GB), `is_public`, `description` |
| `DELETE` | `/api/v1/admin/flavors/{flavor_id}` | flavor 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/flavors/{flavor_id}/access` | 비공개 flavor 접근 허용 프로젝트 목록 | - |
| `POST` | `/api/v1/admin/flavors/{flavor_id}/access` | 프로젝트 접근 권한 추가 | `project_id` |
| `DELETE` | `/api/v1/admin/flavors/{flavor_id}/access/{project_id}` | 프로젝트 접근 권한 제거 (`204`) | - |
| `POST` | `/api/v1/admin/flavors/{flavor_id}/extra-specs` | extra_spec 추가/수정 (GPU 지정 등) | `key`, `value` |
| `DELETE` | `/api/v1/admin/flavors/{flavor_id}/extra-specs/{key}` | extra_spec 삭제 (`204`) | - |

`extra-specs`는 `resources:VGPU` = `1` 처럼 GPU 리소스 요청 지정에 사용됩니다.

---

## GPU 호스트·디바이스·쿼터

> 태그: `admin-gpu`

![GPU 리소스 관리](../../assets/admin-gpu-list.png)
*GPU 타입별 전체/사용 중/사용 가능 수량과 호스트별 GPU 구성 및 가동률*

### GPU 호스트 모니터링

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/gpu-hosts` | Placement 기반 호스트별 GPU 집계(개별/병합/요약/타입) |
| `GET` | `/api/v1/admin/gpu-hosts/raw` | Placement 원본 데이터(디버깅용) |

`gpu-hosts` 응답은 `hosts`(PCI 주소 단위) · `aggregated_hosts`(호스트명 병합) · `summary`(total/used/available) · `gpu_types`(모델별 집계)로 구성됩니다.

### GPU 디바이스 카탈로그

vendor_id/device_id → 표시 이름 매핑을 관리합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/gpu-devices` | GPU 디바이스 이름 매핑 목록 |
| `GET` | `/api/v1/admin/gpu-devices/export` | 디바이스 매핑 내보내기 |
| `POST` | `/api/v1/admin/gpu-devices` | 디바이스 매핑 추가/수정 |
| `DELETE` | `/api/v1/admin/gpu-devices/{vendor_id}/{device_id}` | 디바이스 매핑 삭제 (`204`) |
| `POST` | `/api/v1/admin/gpu-devices/import` | 디바이스 매핑 일괄 가져오기 |

### GPU 쿼터

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/gpu-aliases` | GPU alias 목록 (모델 → 사용자 친화 이름) |
| `GET` | `/api/v1/admin/gpu-quotas/defaults` | 기본 GPU 쿼터 조회 |
| `PUT` | `/api/v1/admin/gpu-quotas/defaults` | 기본 GPU 쿼터 수정 (신규 프로젝트에 적용) |
| `DELETE` | `/api/v1/admin/gpu-quotas/defaults/{gpu_type}` | 기본 쿼터 유형별 삭제 (`204`) |
| `GET` | `/api/v1/admin/gpu-quotas/{project_id}` | 프로젝트 GPU 쿼터 (없으면 기본값 반환) |
| `PUT` | `/api/v1/admin/gpu-quotas/{project_id}` | 프로젝트 GPU 쿼터 수정 |
| `DELETE` | `/api/v1/admin/gpu-quotas/{project_id}/{gpu_type}` | 프로젝트 쿼터 유형별 삭제 → 기본값 복귀 (`204`) |

모든 CPU/GPU Flavor는 Public/Private와 무관하게 target project의 instances·vCPU·RAM 및 GPU 잔여 quota를 검사합니다. Redis cache hit의 dict payload는 `FlavorInfo`로 해석하지만 현재 native 가시성과 private 프로젝트 접근은 별도 fresh 조회로 제한합니다. Public Flavor에 프로젝트 ACL을 요구하지 않고 Private Flavor에만 native `addTenantAccess`가 추가로 필요합니다. GPU quota DB·native usage·metadata 장애는0사용이나 unlimited로 대체하지 않고 `eligibility.selectable=false`와 unavailable blocker로 처리합니다.

GPU 사용량은 인증된 project scope와 대상 `project_id`가 다를 때만 Nova의 all-project inventory를 조회한 뒤 대상 project로 제한합니다. 같은 scope의 connection은 전역 inventory를 요청하지 않습니다. Microversion 2.47+ embedded flavor snapshot(`original_name` + `extra_specs`)은 `extra_specs`가 비어 있어도 authoritative로 취급하며 legacy snapshot만 flavor 상세를 조회합니다. 저장된 legacy alias(`RTX3090Ti` 등)는 읽기에서 canonical alias로 정규화하며 같은 alias의 중복 row는 `updated_at`이 가장 최신인 row(동률이면 `id`가 큰 row)의 limit를 사용합니다. PUT/DELETE도 같은 기준으로 survivor를 고른 뒤 중복 row를 제거합니다. Migration `079_normalize_gpu_quota_types.sql`은 동일 규칙으로 중복을 정리하고 `gpu_type`만 정규화하며 `updated_at`을 보존합니다.

관리자 쿼터 화면은 `GET /api/v1/admin/gpu-aliases`의 클러스터 전체 alias(Flavor `pci_passthrough:alias` + Placement inventory), 전체 기본값, 선택 프로젝트의 effective quota/usage를 합쳐 GPU 타입 행을 구성합니다. 따라서 프로젝트에 저장된 row나 현재 사용량이 없어도 RTX3060·RTX3090 같은 클러스터 GPU 타입이 표시되며 즉시 프로젝트 limit을 설정할 수 있습니다. 별도 기본값이 없는 타입의 effective limit은 `0`입니다.

GPU quota 변경은 Flavor Access를 추가하거나 회수하지 않습니다. 기존 `afterglow:access_mode` metadata는 권한 근거가 아니며 `access-mode`·`access-reconcile` 경로와 quota 연동 UI는 퇴역했습니다. 기존 native ACL은 보존합니다. Private Flavor 접근 편집의 도메인 선택은 현재 native 프로젝트 후보를 제한하는 UI이며, 실제 변경은 선택한 정확한 project UUID에 대한 Nova `addTenantAccess`/`removeTenantAccess`입니다. Native Nova에는 domain flavor grant가 없고 미래 프로젝트로 자동 상속하지 않습니다. Public도 동일한 compute/GPU quota와 생성용 same-host capacity 검사를 받습니다.

---

## 이미지 관리

> 태그: `admin-images`

전체 프로젝트의 Glance 이미지를 관리합니다. 상태 전이(deactivate/reactivate)와 삭제는 사용자 부팅에 영향을 줄 수 있으므로 대상 확인이 필요합니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/images` | 전체 이미지 목록 | `limit`, `marker`, `search`, `visibility` (query) |
| `GET` | `/api/v1/admin/images/{image_id}` | 이미지 상세 | - |
| `PATCH` | `/api/v1/admin/images/{image_id}` | 이미지 메타데이터 수정 | 이름·가시성 등 |
| `PATCH` | `/api/v1/admin/images/{image_id}/properties` | 이미지 커스텀 속성 수정 (`ImageDetail`) | 속성 key/value |
| `DELETE` | `/api/v1/admin/images/{image_id}` | 이미지 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/images/{image_id}/deactivate` | 이미지 비활성화(부팅 불가) | - |
| `POST` | `/api/v1/admin/images/{image_id}/reactivate` | 이미지 재활성화 | - |

---

## Notion 연동

> 태그: `admin-notion`

OpenStack 리소스를 Notion 데이터베이스와 동기화하는 관리자 기능입니다. 단일 연동 설정(`config`)과 다중 동기화 대상(`targets`)을 관리합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/notion/config` | Notion 연동 설정 조회(토큰은 마스킹) |
| `POST` | `/api/v1/admin/notion/config` | Notion 연동 설정 저장 |
| `DELETE` | `/api/v1/admin/notion/config` | Notion 연동 설정 삭제 |
| `POST` | `/api/v1/admin/notion/test` | 연동 설정 연결 테스트 |
| `GET` | `/api/v1/admin/notion/targets` | 동기화 대상(DB) 목록 |
| `POST` | `/api/v1/admin/notion/targets` | 동기화 대상 추가 |
| `PATCH` | `/api/v1/admin/notion/targets/{target_id}` | 동기화 대상 수정 |
| `DELETE` | `/api/v1/admin/notion/targets/{target_id}` | 동기화 대상 삭제 |
| `POST` | `/api/v1/admin/notion/targets/{target_id}/test` | 특정 대상 동기화 테스트 |

![Notion 연동](../../assets/admin-notion.png)
*Notion Integration 설정 — 다중 데이터베이스(인스턴스 DB·이미지 DB·GPU Spec DB) 연결, 즉시 동기화 및 마지막 동기화 시각 표시*

---

## 고아 리소스 정리 (orphans)

> 태그: `admin-orphans`

프로젝트가 사라졌거나 장기 미사용/미연결 상태인 리소스를 탐지·정리합니다. **삭제는 되돌릴 수 없으므로** 정리 전 스캔 결과 검토가 필수이며, 정리 시 race-safe 재검증 후 각 결과가 audit log에 기록됩니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/orphans` | 전체 프로젝트 orphan 후보 스캔 | `min_age_days` (query, 1~365, 기본 14) |
| `POST` | `/api/v1/admin/orphans/cleanup` | ID 목록 일괄 정리 | `kind`, `ids[]` (min 1) |

- `kind`: `floating_ip`(port 미연결) / `volume`(available·attachments 없음) / `manila_share`(프로젝트 소멸) / `security_group`(자동생성 후 미연결).
- 응답은 `deleted[]`와 `failed[]`(`{id, error}`)로 분리됩니다.

---

## 워커 런타임 관리

> 태그: `admin-worker-runtime`

백그라운드 워커(`drover`, `notion_worker`)의 관측 상태와 희망 레플리카 수를 관리합니다. 런타임 모드는 `static` / `docker` / `kubernetes` 중 하나이며, 모드가 관리 불가(`capable=false`)이면 변경이 거부될 수 있습니다.

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/worker-runtime/status` | 런타임 능력 + 워커별 상태 (`WorkerRuntimeStatus`) | - |
| `PATCH` | `/api/v1/admin/worker-runtime/desired` | 희망 레플리카 수 오버라이드 | `workers[]` (`name`, `desired_replicas≥0`; 1~2개, 이름 유일) |
| `POST` | `/api/v1/admin/worker-runtime/reconcile` | 희망 상태로 즉시 재조정 | - |

**제한**: `workers[].name`은 `drover` 또는 `notion_worker`만 허용되며 중복 불가. `desired_replicas`는 `max_replicas`를 넘을 수 없습니다.

---

## Key Manager(Barbican) 쿼터

> 태그: `admin-key-manager`

Barbican(key-manager) 서비스가 활성화된 경우에만 마운트됩니다. 프로젝트별 시크릿/컨테이너 쿼터를 관리하며 rate limit(30/min)이 적용됩니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/key-manager/project-quotas` | 전체 프로젝트 쿼터 목록 |
| `GET` | `/api/v1/admin/key-manager/project-quotas/{project_id}` | 프로젝트 쿼터 조회 |
| `PUT` | `/api/v1/admin/key-manager/project-quotas/{project_id}` | 프로젝트 쿼터 설정 |
| `DELETE` | `/api/v1/admin/key-manager/project-quotas/{project_id}` | 프로젝트 쿼터 초기화 (`204`) |

---

## 서비스 상태 모니터링

> 태그: `admin-services`

### GET /api/v1/admin/services

Nova·Cinder·Neutron·Manila·Heat·Zun 서비스 상태, API 엔드포인트, 스토리지 풀 정보를 종합 조회합니다. `refresh` (query) 지원.

응답은 `compute` / `block_storage` / `network` / `shared_file_system` / `orchestration` / `container` / `container_infra` / `endpoints` / `storage_pools` 필드로 구성됩니다.

### 관리자 화면의 필터·정렬

`/admin/services`의 9개 탭은 조회한 category 데이터 안에서 필터·검색·정렬합니다. 필터 조작은 추가 API 요청이나 클라우드 서비스 상태 변경을 일으키지 않습니다.

| 탭 | 조합 가능한 조건 | 정렬 |
|---|---|---|
| Compute / Block Storage / File Storage / Orchestrator / Container / Magnum | Binary, Host, 표시되는 경우 Zone, Status, State | 표시되는 모든 열; Updated는 UTC 시각 기준 |
| Network | Agent Type, Binary, Host, Zone, Alive, Admin State | 표시되는 모든 열; Alive와 Admin State는 독립 |
| API Endpoints | 이름, 서비스 유형, 리전 | 이름, 서비스 유형, 리전 |
| Storage Pools | backend, protocol, vendor | 이름, backend/protocol/vendor, 전체·남은·할당 용량(숫자) |

- 조건은 AND로 적용합니다. 예: Network에서 `Alive=down`, `Host=compute2`, `Admin State=UP`을 동시에 선택할 수 있습니다. Alive 미확인은 down과 별개입니다.
- 검색은 대소문자와 양끝 공백을 무시하고 공백으로 나눈 모든 검색어를 메타데이터에서 찾습니다. API Endpoints의 URL과 Storage Pools의 driver version도 검색 대상입니다.
- 문자열은 `host2`가 `host10`보다 앞서는 자연 정렬이며, 용량은 표시 문자열이 아닌 숫자 기준입니다. 비어 있거나 유효하지 않은 정렬 값은 오름차순·내림차순 모두 마지막에 둡니다. 같은 값의 원래 순서는 유지합니다.
- 표 머리글의 버튼은 클릭 또는 키보드로 방향을 전환하며 `aria-sort`를 제공합니다. 작은 화면에서는 표를 가로 스크롤하지 않고 상단 정렬 선택기와 방향 버튼을 사용할 수 있습니다.
- 탭별 검색·필터·정렬은 페이지가 유지되는 동안 탭 전환과 수동/자동 새로고침 뒤에도 남습니다. 다른 페이지 이동이나 전체 새로고침 이후의 영속화는 하지 않습니다.
- 초기 로딩과 백그라운드 새로고침을 구분합니다. 새로고침 중에는 기존 행에서 계속 필터·정렬할 수 있습니다. 선택지가 새 응답에서 사라져도 선택을 보존하며 `표시 / 전체` 건수와 초기화 동작을 제공합니다. 원본 0건과 조건에 맞는 결과 0건을 구분합니다.
- User/project identity가 바뀌면 이전 서비스 행을 즉시 비우고 늦게 도착한 응답을 차단합니다. 같은 identity의 token 갱신은 기존 행과 필터를 유지하면서 새 요청 세대를 사용합니다.
- 초기화는 현재 탭에만 적용하며 API Endpoints는 이름 오름차순, 나머지 탭은 응답 원본 순서로 돌아갑니다. 기존 lazy load·hover prefetch·선택 탭 refresh 계약은 바뀌지 않습니다.

---

## 공지사항 (announcements)

> 태그: `admin-announcements`
> prefix: `/api/v1/admin/announcements`

사용자에게 표시할 공지를 관리합니다(사용자 수신 측 API는 별도). 라우터 레벨에서 `require_admin`이 적용됩니다.

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/announcements` | 공지 목록 (`AnnouncementAdminResponse[]`) | - |
| `POST` | `/api/v1/admin/announcements` | 공지 생성 (`201`) | `title`, `body`, `severity`, `target_type`, `target_id`, `starts_at`, `ends_at`, `is_active` |
| `PATCH` | `/api/v1/admin/announcements/{announcement_id}` | 공지 수정 | 위 필드 부분 갱신 |
| `DELETE` | `/api/v1/admin/announcements/{announcement_id}` | 공지 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/announcements/meta/options` | severity/target_type 등 선택지 메타 | - |

- `severity`: `info` 등(기본 `info`).
- `target_type`: 대상 범위(전체/프로젝트 등), `target_id`로 특정 대상 지정.
- `starts_at`/`ends_at`으로 노출 기간, `is_active`로 활성 여부 제어.

관리자 화면의 특정 사용자·프로젝트 대상은 긴 native 선택 목록 대신 `SearchSelect`로 고릅니다. 팝오버 검색은 표시 이름과 stable ID를 모두 대상으로 하며 키보드 방향키·Enter·Escape를 지원합니다. 대상 유형을 바꾸면 이전 `target_id` 선택은 제거됩니다. 사용자 후보는 `/api/v1/admin/users?limit=100`, 프로젝트 후보는 `/api/v1/admin/projects/names` 응답을 사용하며 생성 payload와 서버 권한 계약은 바뀌지 않습니다.

---

## k3s 클러스터 관리 (admin)

관리자가 전체 프로젝트의 k3s 클러스터를 조회·스케일·삭제·인증서 관리하는 엔드포인트입니다. 사용자용 k3s API와 달리 프로젝트 소유권에 관계없이 접근합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/k3s-clusters` | 전체 k3s 클러스터 목록 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}` | 클러스터 상세 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}/kubeconfig` | kubeconfig 조회(복호화) |
| `PATCH` | `/api/v1/admin/k3s-clusters/{cluster_id}/scale` | 노드그룹 스케일 조정 |
| `DELETE` | `/api/v1/admin/k3s-clusters/{cluster_id}` | 클러스터 삭제 (`204`) |
| `POST` | `/api/v1/admin/k3s-clusters/{cluster_id}/delete-async` | 클러스터 비동기 삭제 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}/ca-certificate` | 클러스터 CA 인증서 조회 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}/certificate-expiry` | 인증서 만료 정보 |
| `POST` | `/api/v1/admin/k3s-clusters/{cluster_id}/rotate-certs` | 클러스터 인증서 회전 |
| `GET` | `/api/v1/admin/k3s-cluster-templates` | k3s 클러스터 템플릿 목록 |

**주의**: `delete`/`delete-async`는 VM·볼륨·네트워크 등 클러스터 리소스를 함께 정리하며 되돌릴 수 없습니다. `rotate-certs`는 진행 중 클러스터 접속에 일시적 영향을 줄 수 있습니다.
