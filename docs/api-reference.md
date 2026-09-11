---
title: API 레퍼런스
nav_order: 20
has_children: true
---

# Afterglow API 레퍼런스

Afterglow 백엔드는 FastAPI로 구현된 REST API이며, 모든 OpenStack 서비스와 통신하는 단일 게이트웨이 역할을 합니다.
이 페이지는 API 도메인 인덱스입니다. 각 도메인 문서에서 엔드포인트별 **입력 파라미터 · 파라미터 의존성 · 제한
사항 · 출력 스키마 · 사용 예 · 오류 응답**을 확인할 수 있습니다.

---

## API 버전 규칙

모든 라우터는 **`/api/v1` 단독 마운트**입니다(2026-06-18 전환 완료). 문서의 모든 경로는 `/api/v1/...` 기준입니다.

예외로, cloud-init에 baked되어 기존 VM 재배포 없이는 경로를 바꿀 수 없는 **레거시 3종**만 `/api`·`/api/v1`
양쪽으로 dual-mount됩니다.

| 엔드포인트 | 용도 |
|-----------|------|
| `POST /api/k3s/callback` | k3s 서버 VM → 백엔드 kubeconfig/node_token 콜백 |
| `POST /api/instances/{id}/health/report` | VM 헬스 에이전트 보고 |
| `POST /api/instances/{id}/credentials/rotate-cephx` | VM cephx 자격 회전 |

> 신규 레거시 `/api` 경로 추가는 금지됩니다. 위 3종 외 모든 경로는 `/api/v1` 만 유효합니다.

---

## 인증 헤더

인증이 필요한 모든 엔드포인트에 다음 헤더를 포함해야 합니다.

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | 예 | `Bearer <access_token>` 형식. `POST /api/v1/auth/login` 응답의 access JWT(`token`) |
| `X-Project-Id` | 아니오 | 요청을 처리할 프로젝트 UUID. 생략 시 JWT에 담긴 프로젝트로 처리하며, 다른 값을 주면 서버가 해당 프로젝트로 rescope(전환) |

> Afterglow는 **JWT(access + refresh) 쌍** 기반 인증을 사용합니다. 로그인 시 Keystone 토큰은 서버 Redis
> 세션에 보관되고, 클라이언트에는 access/refresh JWT가 발급됩니다. (구 `X-Auth-Token` 헤더는 더 이상
> 사용하지 않습니다.) 자세한 토큰 수명·회전 모델은 [인증 (Auth)](api/auth.md)를 참고하세요.

`POST /api/v1/auth/login`, `GET /api/v1/health`, `GET /api/v1/metrics`는 인증이 필요하지 않습니다.
Prometheus SD(`/api/v1/sd/...`)와 VM 에이전트용 baked 경로는 별도의 Bearer 토큰을 사용합니다(각 문서 참조).

> **선택 서비스**: 일부 도메인은 `afterglow.conf`의 `[services]`(또는 해당 섹션)에서 활성화된 경우에만
> 마운트됩니다. 아래 표의 "선택" 표시를 참고하세요.

---

## API 도메인 인덱스

### 인증 및 사용자

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [인증 (Auth)](api/auth.md) | `/api/v1/auth` | Keystone 토큰 발급/갱신, 세션 관리, 프로젝트 스코프 전환 |
| [프로필 (Profile)](api/profile.md) | `/api/v1/profile` | 사용자 프로필 조회/수정, 비밀번호 변경, 활동 로그 |
| [프로젝트·초대 (Projects)](api/projects.md) | `/api/v1/projects`, `/api/v1/invitations` | 프로젝트 self-service, 멤버·매니저·초대 관리 |

### 관리자

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [관리자 (Admin)](api/admin.md) | `/api/v1/admin` | 클러스터 개요, 사용자/프로젝트/쿼터/그룹/역할, Flavor·GPU·이미지, 마이그레이션, 고아 리소스, 워커 런타임 등 (전 엔드포인트 `require_admin`) |

### 컴퓨트

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [인스턴스 (Instances)](api/instances.md) | `/api/v1/instances` | VM 생성/조회/제어/삭제, OverlayFS 생성(SSE), 볼륨·인터페이스·보안그룹·FIP·메트릭 |
| [인스턴스 헬스 (Instance Health)](api/instance-health.md) | `/api/v1/instances` | VM 헬스 에이전트 보고/조회, cephx 자격 회전 (baked 경로) |
| [이미지 (Images)](api/images.md) | `/api/v1/images` | Glance 이미지 카탈로그, 업로드, 속성/멤버 관리 |
| [플레이버 (Flavors)](api/flavors.md) | `/api/v1/flavors` | Nova 플레이버 목록 |
| [키페어 (Keypairs)](api/keypairs.md) | `/api/v1/keypairs` | SSH 키페어 생성/삭제 |

### 스토리지

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [볼륨 (Volumes)](api/volumes.md) | `/api/v1/volumes`, `/api/v1/volume-snapshots` | Cinder 볼륨, 백업, 스냅샷, 이전(transfer), 자동 백업 |
| [파일 스토리지 (File Storage)](api/file-storage.md) | `/api/v1/file-storage` | Manila CephFS 공유, 접근 규칙 — *선택* |
| [공유 스냅샷·네트워크 (Share Mgmt)](api/share-management.md) | `/api/v1/share-snapshots`, `/api/v1/share-networks`, `/api/v1/security-services` | Manila 스냅샷/네트워크/보안 서비스 — *선택* |

### 네트워크

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [네트워크 (Networks)](api/networks.md) | `/api/v1/networks` | Neutron 네트워크, 서브넷, Floating IP, 토폴로지 |
| [라우터 (Routers)](api/routers.md) | `/api/v1/routers` | Neutron 라우터, 인터페이스, 게이트웨이 |
| [로드밸런서 (Load Balancers)](api/loadbalancers.md) | `/api/v1/loadbalancers` | Octavia LB, 리스너, 풀, 멤버, 헬스 모니터 |
| [보안 그룹 (Security Groups)](api/security-groups.md) | `/api/v1/security-groups` | Neutron 보안 그룹, 규칙 관리 |

### 유니온 레이어

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [Palimpsest 레이어](api/union.md) | `/api/v1/palimpsest`, `/api/v1/admin/libraries`, `/api/v1/libraries/squashfs` | 레이어드 VM — squashfs 레이어 빌드/소비, digest 검색, 부모 체인. (구 `/api/v1/union` 은 제거됨 — [palimpsest.md](palimpsest.md)) |

### 컨테이너 · Kubernetes

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [컨테이너 (Containers)](api/containers.md) | `/api/v1/clusters`, `/api/v1/containers` | Magnum 클러스터, Zun 컨테이너 — *선택* |
| [k3s 클러스터 (k3s)](api/k3s.md) | `/api/v1/k3s/clusters` | 경량 Kubernetes 프로비저닝(SSE), 스케일, kubeconfig, 인증서, 노드그룹 — *선택* |
| [k3s 리소스 관리](api/k3s-resources.md) | `/api/v1/k3s/clusters/...` | 클러스터 내부 k8s 리소스(pods/deployments/services/configmaps/secrets/shell) — *선택* |

### 데이터 · 키 · 부가 서비스

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [데이터베이스 (Trove)](api/database.md) | `/api/v1/database-instances` | Trove DBaaS 인스턴스, databases/users, 백업 — *선택* |
| [오브젝트 스토리지 (Swift)](api/object-storage.md) | `/api/v1/object-storage` | Swift 컨테이너/오브젝트, 업로드, 다운로드 토큰, 휴지통 — *선택* |
| [키 관리 (Barbican)](api/secrets.md) | `/api/v1/secrets`, `/api/v1/secret-containers`, `/api/v1/secret-orders` | Barbican 시크릿/컨테이너/오더, ACL, 쿼터 — *선택* |
| [VPN (VPNaaS)](api/vpn.md) | `/api/v1/vpn/servers` | VPN 서버/클라이언트, config 다운로드, 에이전트 콜백 — *선택* |

### 대시보드 · 시스템

| 문서 | 기본 경로 | 설명 |
|------|-----------|------|
| [대시보드 (Dashboard)](api/dashboard.md) | `/api/v1/dashboard`, `/api/v1/libraries` | 프로젝트 리소스 요약, 쿼터, 라이브러리 카탈로그 |
| [시스템 서비스](api/system-services.md) | `/api/v1/announcements`, `/api/v1/tutorials`, `/api/v1/sd`, `/api/v1/grafana`, `/api/v1/site-config`, `/api/v1/user-dashboard` | 공지, 튜토리얼, Prometheus SD, Grafana 임베드, 사이트 설정, 개인 대시보드 |
| [채팅 (Chat)](api/chat.md) | `/api/v1/chat` | Lumen AI API 프록시 및 SSE 스트리밍 (BFF) — *선택* |
| [메트릭 (Metrics)](api/metrics.md) | `/api/v1/metrics`, `/api/v1/health` | Prometheus 메트릭, 헬스 체크 (인증 불필요) |

---

## 아키텍처 문서

현재 시스템 경계·ownership·runtime·데이터 정본은 [루트 `ARCHITECTURE.md`](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md)를 참고하세요. 이 사이트의 [아키텍처 상세](architecture.md)는 도메인별 문서 진입점이며 전체 root snapshot의 복사본이 아닙니다. 모듈 관계는 [클래스·workflow 다이어그램](class-diagrams/)에서 확인할 수 있습니다.
