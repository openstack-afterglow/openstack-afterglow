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

개발 환경 또는 단일 호스트 소규모 배포에 적합합니다.

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

Docker Compose 로컬 개발에서는 `.env`도 함께 읽습니다. `.env.example`에는 예시 `SECRET_KEY=change-me-in-production`과 이를 로컬에서만 허용하는 `AFTERGLOW_ALLOW_INSECURE=1`이 들어 있습니다. 운영·Kubernetes에서는 `AFTERGLOW_ALLOW_INSECURE`를 절대 설정하지 말고 실제 `SECRET_KEY`를 사용하세요.

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

### 2. 서비스 시작

```bash
# 기본 서비스 (backend + frontend + redis)
docker compose up -d

# 모니터링 스택 포함
docker compose --profile monitoring up -d
```

### 3. 접속 확인

```bash
# 헬스체크
curl http://localhost:8000/api/v1/health

# 브라우저
open http://localhost:3000
```

### 서비스 구성

| 서비스 | 포트 | 설명 |
|---|---|---|
| frontend | 3000 | SvelteKit 웹 UI |
| backend | 8000 | FastAPI REST API |
| redis | 6379 | 캐시 / 세션 (AOF 영속화) |
| opensearch | 9200 | 로그 검색 (모니터링) |
| prometheus | 9090 | 메트릭 수집 (모니터링) |
| grafana | 3001 | 대시보드 (모니터링) |

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
git pull origin dev
docker compose pull
docker compose up -d
```

### 데이터베이스 스키마 마이그레이션

`auto_create_tables`는 기존 테이블에 컬럼을 추가하지 않습니다. 이미지가 새 ORM 컬럼을 참조하는 릴리스는 **롤아웃 전에** 해당 SQL 마이그레이션을 운영 데이터베이스에 적용해야 합니다. 적용 대상과 순서는 `backend/migrations/manifest.txt`의 논리 ID를 기준으로 판단하며, 숫자 접두사만으로 판단하지 않습니다.

로컬 Compose의 2026-08-02 채팅 메시지 시간대 컬럼 마이그레이션 예시:

```bash
docker compose exec -T mariadb sh -c \
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
docker compose logs backend
kubectl logs -f deployment/backend -n afterglow

# Keystone 연결 테스트
curl -s https://keystone.example.com:5000/v3 | python3 -m json.tool
```

### Redis 연결 오류

```bash
docker compose exec backend redis-cli -u redis://redis:6379 ping
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
