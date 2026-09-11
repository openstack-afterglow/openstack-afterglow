# Afterglow

**Language:** 한국어 · [English](README.en.md)

> Horizon의 완성도 + Skyline의 현대적 UX를 결합한 차세대 OpenStack 대시보드

[![CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/test.yml/badge.svg)](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/test.yml)
[![Docker Build](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/docker-build.yml/badge.svg)](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/docker-build.yml)
[![License](https://img.shields.io/github/license/openstack-afterglow/openstack-afterglow)](LICENSE)

Afterglow는 OpenStack 클라우드를 위한 오픈소스 웹 대시보드입니다. Horizon의 기능 완성도와 안정성을 유지하면서 SvelteKit 기반의 현대적 UI/UX를 제공하고, Magnum을 대체하는 **k3s 기반 Kubernetes 프로비저닝**과 AI/ML 워크로드를 위한 **squashfs/NFS 기반 Palimpsest 라이브러리 레이어**를 내장합니다.

## 실제 운영 서비스

Afterglow는 현재 [DMS Cloud 연구 클라우드 제공 콘솔](https://cloud.dmslab.re.kr)로 운영되고 있습니다. 실제 사용 흐름은 연구원·실습팀이 프로젝트 범위에서 자원을 신청하고, 운영자가 쿼터와 권한에 따라 배정한 뒤, 사용량·상태·토폴로지를 관측하고, 라이브러리 레이어와 스냅샷으로 환경을 재사용하는 구조입니다.

저장소의 구현은 다음 운영 표면을 제공합니다.

- **컴퓨팅** — Nova 기반 VM에 GPU·vCPU·메모리·스토리지를 프로젝트 쿼터 안에서 배정하고, 이미지·네트워크·키페어를 조합합니다.
- **Kubernetes** — cloud-init으로 OpenStack VM에 k3s 클러스터의 제어 plane과 워커 노드를 구성하고 상태와 워크로드를 추적합니다.
- **공유 데이터와 라이브러리** — Manila CephFS/NFS share와 스냅샷을 사용하고, squashfs 기반 content-addressable 불변 AI/ML 레이어를 VM에서 OverlayFS로 조합해 재사용합니다.
- **운영과 관측** — 프로젝트·사용자·역할·쿼터, Grafana·Prometheus 연동, 감사 로그를 한 콘솔에서 관리합니다.

브라우저의 SvelteKit 앱은 설정된 API base의 FastAPI `/api/v1` 게이트웨이를 직접 호출하고, 백엔드는 `openstacksdk` 기반 OpenStack 서비스와 통신합니다. SvelteKit은 UI/auth shell이며 API 중계 서버가 아닙니다. Redis는 캐시와 세션을 담당합니다. 현재 구조의 정본은 [루트 아키텍처](ARCHITECTURE.md)이고, 상세 도메인은 [Palimpsest 레이어 문서](docs/palimpsest.md)를 참고하세요. 코드·설정 변경 후에는 `python3 scripts/check_architecture.py --stamp --summary "<검토 요약>"` 및 `python3 scripts/check_architecture.py --staged`로 freshness를 확인합니다.


## 주요 기능

- **OpenStack 전체 서비스 관리** — Nova · Glance · Cinder · Neutron · Manila · Octavia를 단일 대시보드에서
- **k3s 클러스터 프로비저닝** — Magnum 없이 VM에 k3s 직접 배포 (OCCM · Cinder/Manila CSI · Keystone Auth · Barbican KMS 플러그인)
- **squashfs/NFS 라이브러리 레이어 (Palimpsest)** — content-addressable 불변 레이어 체인을 Manila share에 저장하고 소비 VM에서 OverlayFS로 조합
- **모니터링 통합** — Grafana JWT 임베드, Prometheus HTTP SD, Monitoring 보안 그룹 자동화
- **Defense-in-depth 보안** — IDOR 가드, HKDF 키 분리 암호화, kubeconfig audit log, production 부팅 가드

## 빠른 시작

```bash
git clone git@github.com:openstack-afterglow/openstack-afterglow.git
cd openstack-afterglow
cp afterglow.conf.example afterglow.conf   # OpenStack 자격증명 입력
cp .env.example .env                       # 로컬 compose 전용: SECRET_KEY 교체 또는 dev-only allow 플래그 유지
docker compose up -d                 # http://localhost:3000
```

`afterglow.conf`가 유일한 애플리케이션 설정 파일입니다. `.env.example`의 `AFTERGLOW_ALLOW_INSECURE=1`은 Docker Compose 로컬 개발 전용이며 Kubernetes/production에는 넣지 않습니다.

### 공개 MCP/OAuth

MCP 공개는 기본적으로 비활성입니다. 활성화하려면 `SERVICE_MCP_ENABLED=true`와 함께 `MCP_PUBLIC_URL`(MCP resource URL) 및 `MCP_OAUTH_CONSENT_URL`(Afterglow 동의 화면 URL)을 설정합니다. `MCP_PUBLIC_URL`에 origin만 지정하면 `/api/v1/mcp`를 사용합니다. 외부 OIDC 로그인 콜백은 `GITLAB_OIDC_REDIRECT_URI`로, MCP 클라이언트의 OAuth `redirect_uri`는 DCR/CIMD 등록으로 각각 관리합니다.
Helm 차트는 별도 MCP host에도 resource와 `/.well-known` discovery 경로를 backend로 라우팅하고 TLS host에 포함합니다. raw Kubernetes manifest를 쓰면 같은 host·resource·`/.well-known` 라우팅을 ingress에 직접 추가해야 합니다.

Kubernetes · ArgoCD · kolla-ansible 배포와 상세 설정은 아래 문서를 참고하세요.

## 문서

📖 전체 문서: **<https://openstack-afterglow.github.io/openstack-afterglow/>**

| 문서 | 내용 |
|---|---|
| [루트 아키텍처](ARCHITECTURE.md) | 현재 ownership·runtime·데이터 경계와 갱신 규칙 |
| [상세 배포](docs/deployment.md) | Docker Compose · Kubernetes · ArgoCD · kolla-ansible |
| [k3s 클러스터](docs/k3s.md) | k3s 프로비저닝, 노드 구성, CoreOS 전환 |
| [상세 API](docs/api-reference.md) | 전체 REST API |
| [보안 모델](docs/security.md) | 인증·인가, IDOR 가드, HKDF 암호화, audit log |
| [국소 기능테스트](docs/testing.md) | 개발 중 빠른 국소 기능 검증 가이드 |
| [아키텍처 상세](docs/architecture.md) | 루트 정본에서 연결하는 historical/domain detail |

릴리스 변경사항은 [CHANGELOG](CHANGELOG.md), 작업 기록·로드맵은 [`openspec/`](openspec/)(`openspec list`, 구 [milestone.md](milestone.md)에서 이관)를 참고하세요.

## 기술 스택

| 구성 | 기술 |
|---|---|
| 프론트엔드 | SvelteKit · TypeScript · Tailwind CSS v4 |
| 백엔드 | FastAPI · openstacksdk (Python) |
| 캐시 / 세션 | Redis 7 |
| 배포 | Docker Compose · Kubernetes (Kustomize) · ArgoCD · kolla-ansible |

## 개발

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload   # 백엔드 :8000
cd frontend && npm install && npm run dev                       # 프론트엔드 :3000
npm run test:list                                               # 실행 가능한 국소 테스트 타깃 확인
npm run test:target -- auth                                     # 예: 인증/세션 관련 국소 기능테스트
npm run test:functional                                         # 일회용 전용 DB/캐시 기능테스트 (3307/5434/6380)
npm run test:unit                                               # 오케스트레이터 + 백엔드/프론트엔드 단위 계층
npm run test:gate                                               # 커밋/PR 전 확정 게이트 (test:all + lint:backend)
```

## 라이선스

MIT License — [LICENSE](LICENSE)
