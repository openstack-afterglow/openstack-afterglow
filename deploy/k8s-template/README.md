# Afterglow Kubernetes 배포 가이드

## 디렉토리 구조

```
deploy/k8s-template/
├── configmap.yaml        # afterglow.conf ConfigMap
├── secret.yaml           # afterglow-secrets 예시
├── ingress.yaml
├── cert-manager.yaml
├── base/
│   ├── namespace.yaml
│   ├── backend/
│   ├── frontend/
│   ├── redis/
│   └── worker/           # drover + notion-worker
└── overlays/
    ├── dev/
    └── prod/
```

## 빠른 배포 방법

### 1. 이미지 빌드

```bash
docker build -t afterglow-api:latest ./backend
docker build -t afterglow:latest ./frontend
```

로컬 Kubernetes 클러스터(예: minikube)를 사용하는 경우, 이미지를 클러스터에 로드합니다.

```bash
# minikube 사용 시
minikube image load afterglow-api:latest
minikube image load afterglow:latest
```

### 2. 설정 수정

배포 전 반드시 다음 값을 실제 환경에 맞게 수정하세요.

- `configmap.yaml`: `afterglow.conf` 인라인 설정, `APP_ORIGIN`, `PUBLIC_S3_BASE`, `APP_GRAFANA_BASE`
- `secret.yaml`: `OS_PASSWORD`, `SECRET_KEY`, `GITLAB_OIDC_CLIENT_SECRET`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL`, `PROMETHEUS_PASSWORD`, `BUILDER_SSH_PRIVATE_KEY`
- `base/frontend/deployment.yaml`: `ORIGIN`, `PUBLIC_API_BASE`, `PUBLIC_S3_BASE`, `PUBLIC_GRAFANA_BASE`
- `ingress.yaml`: `host` 값 (실제 도메인)

`backend`, `worker`(drover), `notion-worker`는 모두 `/app/afterglow.conf`를 마운트하고 `afterglow-secrets/SECRET_KEY`를 환경변수로 읽습니다. 세 서비스 모두 `AFTERGLOW_ENV=production`으로 실행되므로 `AFTERGLOW_ALLOW_INSECURE=1`은 이 manifest에 넣지 않습니다.
`backend`와 `frontend` Deployment는 `/app/logs` 경로에 `emptyDir` 볼륨(`app-logs`)을 마운트하여 파드 실행 중 날짜/용량 기반 파일 로그를 작성합니다. `fsGroup: 1000` 권한으로 비최상위 사용자 쓰기가 보장되며, PVC나 hostPath 없이 파드 단위 수명주기를 가지는 휘발성(ephemeral) 스토리지입니다. 표준 출력/표준 에러(stdout/stderr) 수집기와 상충하지 않습니다.

> 이 빠른 배포 절차는 `afterglow` 네임스페이스용 프로덕션 정적 manifest만 다룹니다. `overlays/dev`는 `afterglow-dev` 네임스페이스를 사용하므로, dev 배포에는 `afterglow-dev`용 `afterglow-config` ConfigMap과 `afterglow-secrets` Secret을 별도로 생성하거나 ExternalSecret/ArgoCD로 관리해야 합니다.

### 3. 순서대로 배포

```bash
# 1. 네임스페이스 생성
kubectl apply -f deploy/k8s-template/base/namespace.yaml

# 2. ConfigMap 생성
kubectl apply -f deploy/k8s-template/configmap.yaml

# 3. Secret 생성 (파일 수정 후 적용 또는 아래 명령어 직접 사용)
kubectl apply -f deploy/k8s-template/secret.yaml
# 또는 kubectl로 직접 생성:
# Builder SSH를 쓰지 않으면 빈 파일로 키 존재만 보장합니다. 실제 사용 시 private key 경로를 지정하세요.
# touch builder.key
# kubectl create secret generic afterglow-secrets \
#   --namespace=afterglow \
#   --from-literal=OS_PASSWORD=실제OpenStack비밀번호 \
#   --from-literal=SECRET_KEY=$(openssl rand -hex 32) \
#   --from-literal=GITLAB_OIDC_CLIENT_SECRET='' \
#   --from-literal=K3S_KUBECONFIG_ENCRYPTION_KEY=$(openssl rand -hex 32) \
#   --from-literal=DATABASE_URL='mysql+asyncmy://afterglow:실제DB비밀번호@mariadb/afterglow' \
#   --from-literal=PROMETHEUS_PASSWORD='' \
#   --from-file=BUILDER_SSH_PRIVATE_KEY=builder.key

# 4. 전체 배포
kubectl apply -k deploy/k8s-template/overlays/prod
```

또는 한 번에 전체 배포 (순서 보장 필요 시 위 방법 사용):

```bash
kubectl apply -f deploy/k8s-template/base/namespace.yaml && \
kubectl apply -f deploy/k8s-template/configmap.yaml && \
kubectl apply -f deploy/k8s-template/secret.yaml && \
kubectl apply -k deploy/k8s-template/overlays/prod
```

### 4. 배포 상태 확인

```bash
kubectl get all -n afterglow
kubectl get ingress -n afterglow
```

## PUBLIC_API_BASE 설정 주의사항

`PUBLIC_API_BASE`는 **브라우저(클라이언트)에서 직접 접근 가능한 URL**이어야 합니다.

- Ingress를 사용하는 경우, `ORIGIN`과 동일하게 외부 도메인으로 설정합니다.
  ```
  PUBLIC_API_BASE=http://afterglow.example.com
  ```
- 클러스터 내부 서비스 주소(예: `http://backend:8000`)로 설정하면 **브라우저에서 접근할 수 없습니다.**
- HTTPS를 사용하는 경우 `http://` 대신 `https://`를 사용하세요.
- 도메인 변경 후에는 `kubectl rollout restart deployment/frontend -n afterglow`으로 프론트엔드를 재시작해야 합니다.

## 모니터링 선택 배포

모니터링 스택(Prometheus, Grafana, OpenSearch)은 선택적으로 배포할 수 있습니다.

```bash
# 전체 모니터링 스택 배포
kubectl apply -k deploy/k8s-template/monitoring/

# 개별 배포
kubectl apply -f deploy/k8s-template/monitoring/prometheus/
kubectl apply -f deploy/k8s-template/monitoring/grafana/
kubectl apply -f deploy/k8s-template/monitoring/opensearch/
```

### Grafana 접근

```bash
# 포트 포워딩으로 로컬 접근
kubectl port-forward svc/grafana 3001:3000 -n afterglow
# 브라우저에서 http://localhost:3001 접속
# 기본 계정: admin / admin
```

### Prometheus 접근

```bash
kubectl port-forward svc/prometheus 9090:9090 -n afterglow
# 브라우저에서 http://localhost:9090 접속
```

## 오브젝트 스토리지 업로드 타임아웃 설정

대용량 파일 업로드 시 Traefik 기본 60초 타임아웃으로 인해 업로드가 중단될 수 있습니다.
아래 절차로 Traefik 타임아웃을 600초(10분)로 설정하세요.

### 1. Middleware CRD 배포

```bash
kubectl apply -f k8s-template/middleware.yaml
```

### 2. Ingress 재배포

`ingress.yaml`에 Middleware 어노테이션이 이미 포함되어 있습니다.

```bash
kubectl apply -f k8s-template/ingress.yaml
```

### 3. k3s Traefik 엔트리포인트 타임아웃 설정 (필수)

Middleware만으로는 Traefik 엔트리포인트 레벨의 타임아웃을 변경할 수 없습니다.
k3s 노드에서 Traefik HelmChart 값을 수정해야 합니다.

```bash
# k3s 노드에서 실행
cat > /var/lib/rancher/k3s/server/manifests/traefik-config.yaml << 'EOF'
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    additionalArguments:
      - "--entryPoints.web.transport.respondingTimeouts.readTimeout=600"
      - "--entryPoints.web.transport.respondingTimeouts.writeTimeout=600"
      - "--entryPoints.web.transport.respondingTimeouts.idleTimeout=600"
      - "--entryPoints.websecure.transport.respondingTimeouts.readTimeout=600"
      - "--entryPoints.websecure.transport.respondingTimeouts.writeTimeout=600"
      - "--entryPoints.websecure.transport.respondingTimeouts.idleTimeout=600"
EOF
```

설정 적용 후 Traefik Pod가 자동으로 재시작됩니다.

### 타임아웃 체인 요약

| 구간 | 설정값 |
|------|--------|
| Swift 백엔드 (`swift_upload_timeout`) | 600초 |
| Ceph RGW HAProxy | 600초 |
| Traefik Ingress (위 설정 적용 후) | 600초 |

---

## 문제 해결

```bash
# Pod 로그 확인
kubectl logs -f deployment/backend -n afterglow
kubectl logs -f deployment/frontend -n afterglow

# Pod 상태 확인
kubectl describe pod -l app=backend -n afterglow

# ConfigMap 내용 확인
kubectl get configmap afterglow-config -n afterglow -o yaml
```
