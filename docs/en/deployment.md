---
title: Deployment
parent: English
lang: en
nav_order: 1
---

# Deployment Guide

**Language:** [한국어](../deployment.md) · English

Afterglow supports three deployment modes: Docker Compose (development / small scale), Kubernetes (production), and ArgoCD (GitOps).

---

## Prerequisites

### OpenStack Services

| Service | Required | Purpose |
|---|---|---|
| Keystone | Required | Authentication |
| Nova | Required | VM compute |
| Glance | Required | Image management |
| Cinder | Required | Block storage |
| Neutron | Required | Networking |
| Manila | Optional | Shared filesystem (OverlayFS feature) |
| Octavia | Optional | Load balancing |

---

## Docker Compose Deployment

Select one standalone manifest explicitly with `-f`: `docker-compose.yml` runs only the published Afterglow frontend/backend with external dependencies; `docker-compose.dev.yml` builds the full local source stack; `docker-compose.prod.yml` pulls GHCR images and uses TLS HAProxy ingress plus Keystone catalog service discovery. Do not merge dev and prod or reuse their data volumes across modes.

Functional tests also use the `test` profile in `docker-compose.dev.yml`; there is no separate test manifest. `npm run test:functional` starts only `mariadb`, `postgres`, and `test-redis` under the separate `afterglow-test` project on loopback 3307/5434/6380. No cloud credentials or sibling checkouts are required for test-only startup. Scoped teardown discards tmpfs test data, not development applications, named volumes or keys. Use `--no-start` to reuse externally managed services and `--keep` to leave test containers running for debugging (stopping them loses their tmpfs data).

### 1. Clone and Configure

```bash
git clone git@github.com:openstack-afterglow/openstack-afterglow.git
cd openstack-afterglow
cp afterglow.conf.example afterglow.conf
cp .env.example .env
```

Required `afterglow.conf` fields:

```toml
[openstack]
auth_url             = "https://keystone.example.com:5000/v3"
project_name         = "myproject"
project_domain_name  = "Default"
user_domain_name     = "Default"
region_name          = "RegionOne"

[app]
secret_key = "openssl-rand-hex-32-output"  # must be a random value, 32+ chars

[nova]
default_network_id = "your-network-uuid"
```

The base backend optionally reads `.env`; frontend never receives backend secrets. The dev runner creates and preserves separate random keys and a private configuration snapshot rather than relying on the sample insecure key. Production forces the insecure bypass off and requires a real secret and operator-provided TLS certificate.

### 2. Start Services

For current-source development, provide sibling checkouts `../lumen`, `../waygate`, `../drover`, and `../palimpsest`; the first three require `docker/Dockerfile` and Palimpsest requires `docker/hub/Dockerfile`. Docker Compose 2.24+, Python 3.12+, and actual OpenStack credentials are required. Set the dedicated `[openstack] service_project_id` in the private config or `OS_SERVICE_PROJECT_ID` in `.env`; there is no admin-project fallback.

```bash
npm run services:up

# Prepare private inputs for explicit Compose commands:
npm run services:config
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml up -d --build --wait

# Development-only monitoring:
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml --profile monitoring up -d

# Minimal baseline instead, with separately configured external DB/cache:
docker compose -f docker-compose.yml up -d
```

The remote Keystone/Nova/Neutron/etc configuration is unchanged. Select only owned-service
destinations with `SERVICE_WAYGATE_INTERNAL_URL`, `SERVICE_DROVER_INTERNAL_URL`,
`SERVICE_LUMEN_INTERNAL_URL`, `SERVICE_PALIMPSEST_INTERNAL_URL`, or `[services]`
`*_internal_url` values. Both BFF requests and Drover/Waygate SDK consumers use this choice.
The dev runner resolves shell/`.env` first (including explicit empty = catalog), then
nonempty values from `.local-services/afterglow.conf`, then local Compose DNS. It preserves
the resolved choice in private `compose.env`. An existing private snapshot is not overwritten
when the original config changes. Run `services:config/up` after changing inputs; restart
other directly launched consumers after changing their config.

For example, `SERVICE_LUMEN_INTERNAL_URL=http://lumen-api:8012` selects the local container;
`SERVICE_LUMEN_INTERNAL_URL=` selects the catalog, even when TOML specifies another URL.
Use `http://127.0.0.1:8012` only when the backend itself runs on the host. The equivalent
TOML field is `[services] lumen_internal_url`. Base/production default to catalog rather
than dev DNS and accept explicit trusted HTTPS endpoints in production.
See [endpoint examples and precedence](../openstack-service-catalog.md#로컬-direct-서비스-엔드포인트-오버라이드-direct-service-endpoint-overrides).

The reverse Lumen → Afterglow connection uses `LUMEN_MCP_CONTROL_PLANE_URL` (dev default
`http://backend:8000`). Browser `PUBLIC_API_BASE` and remote-VM
`WAYGATE_CALLBACK_BASE_URL`/`DROVER_CALLBACK_BASE_URL` are separate: use addresses reachable
from those callers, never container DNS or the development host's loopback for remote VMs.

Development keeps the existing `afterglow-local-services` project, volume identities and encryption keys. `.local-services/` is private (0700); the config snapshot is 0640 and only its mounting services receive the file's GID through `group_add`, preserving non-root image users on Linux. Keys and generated `compose.env` remain 0600; none of these files may be printed or committed. Datastore URLs are literal local addresses, preventing shell/environment production database settings from redirecting local migrations. Local Drover API/worker/migration explicitly disable Sentinel and clear its host list so copied production settings cannot redirect the cache. Sibling service traffic defaults to Compose DNS and accepts explicit endpoint selection. OpenStack itself remains real and external. Missing sibling source fails before startup; there is no installed-image development fallback.

### 3. Verify

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Browser
open http://localhost:3080
```

Container liveness is not dashboard success. Run `npm run services:smoke` with a short-lived `AFTERGLOW_SMOKE_TOKEN`, `LUMEN_SMOKE_MODEL_ID`, an owned `LUMEN_SMOKE_CONVERSATION_ID`, and optionally `AFTERGLOW_SMOKE_PROJECT_ID`. The smoke checks migrations, workers, authenticated BFFs, Lumen billing/context contracts and uncached dashboard summary/quotas/Drover stats. Drover must return `available: true`; upstream Nova 503 fails the whole smoke. No provider completion or cloud resource mutation is performed. Stop only this project with `npm run services:down`; volumes and unrelated applications remain intact.

### Service Layout

| Service | Port | Description |
|---|---|---|
| frontend | 3080 | SvelteKit web UI |
| backend | 8000 | FastAPI REST API |
| redis | 6379 | Cache / session (AOF persistence) |
| waygate-api / drover-api / lumen-api | 8010 / 8011 / 8012 | Local sibling APIs plus workers/migrations |
| palimpsest-api | 8020 | Existing local Hub API plus worker/bootstrap |
| afterglow-mariadb / service-mariadb / lumen-postgres | not published | Private local durable stores |
| opensearch | 9200 | Log search (monitoring) |
| prometheus | 9090 | Metrics collection (monitoring) |
| grafana | 3001 | Dashboards (monitoring) |

### Production images and TLS ingress

The default `afterglow-production` project runs published frontend/backend images, private persistent Redis and HAProxy 3.2. Only HAProxy publishes host ports: 80/443 plus optional sibling TLS catalog listeners 8010/8011/8012/8020. API, `/v1/`, well-known discovery and API documentation routes reach backend; other routes reach frontend. Docker DNS round-robin supports up to ten replicas per application pool; existing WebSocket and SSE connections remain on their selected backend.

Use a separate private production env file with real `SECRET_KEY`, `OS_PASSWORD`, external `DATABASE_URL`, HTTPS `ORIGIN`, HTTPS `PUBLIC_API_BASE` and absolute `TLS_CERTS_DIR`. Prepare the remaining Keystone/domain/project settings in `afterglow.conf`. The read-only certificate directory must contain valid domain certificate-chain/private-key PEM files. Missing/invalid certificates fail startup; no self-signed certificate is generated.

```bash
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml pull
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml up -d --no-build --wait
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml up -d --no-build --wait --scale frontend=2 --scale backend=2
```

Registry defaults to `ghcr.io/openstack-afterglow`. Pin a reviewed `IMAGE_TAG` or per-service tag; `AFTERGLOW_BACKEND_IMAGE`, `AFTERGLOW_FRONTEND_IMAGE`, `AFTERGLOW_WORKER_IMAGE` and sibling `*_API_IMAGE`/`*_WORKER_IMAGE` accept full tagged or digest-pinned references. Current Afterglow CI publishes amd64; ARM operators must check image support or explicitly use `DOCKER_DEFAULT_PLATFORM=linux/amd64` emulation. Development builds are native.

Production defaults to authenticated Keystone catalog discovery. Unset `SERVICE_*_INTERNAL_URL` variables leave TOML/default discovery intact; explicit environment values take precedence and explicit empty selects catalog. Configured production overrides require trusted HTTPS endpoints; dev HTTP URLs fail validation instead of silently selecting a different service. Optional `waygate`, `drover`, `lumen`, `palimpsest` profiles install published sibling API/worker images and gate them on migration/bootstrap completion; `notion` enables the Notion worker. Provide each service's external production DB, service credentials, callback URL and encryption key. Drover additionally needs `DROVER_OS_SERVICE_PROJECT_ID`; Lumen needs `LUMEN_CHECKPOINTER_POSTGRES_URL`, `LUMEN_ENCRYPTION_KEY`, shared `LUMEN_MCP_SERVICE_TOKEN`, and `LUMEN_MCP_CONTROL_PLANE_URL` pointing to Afterglow's published catalog endpoint, never backend container DNS. Catalog URLs must use operator DNS/certificates and the relevant TLS listener, such as `https://<service-host>:8012/v1`. Compose never rewrites the cloud catalog. Disabled sibling profiles do not prevent HAProxy startup; their listeners return 503.

---

## Kubernetes Deployment

Production deployment. Kustomize-based `base` + `overlay` layout separates dev and prod environments.

### Prerequisites

| Item | Minimum version |
|---|---|
| kubectl | 1.28+ |
| k3s or Kubernetes | 1.28+ |
| (Optional) ArgoCD | 2.8+ |

### Directory Layout

```
deploy/k8s-template/
├── configmap.yaml      # afterglow.conf ConfigMap
├── secret.yaml         # afterglow-secrets example
├── ingress.yaml
├── cert-manager.yaml
├── base/              # Shared Deployment/Service resources
│   ├── namespace.yaml
│   ├── backend/
│   ├── frontend/
│   ├── redis/
│   └── worker/
└── overlays/
    ├── dev/           # Development overlay
    └── prod/          # Production overlay
```

### 1. Create Production Namespace and Secrets

The static `configmap.yaml` and `secret.yaml` include `metadata.namespace: afterglow`, so these commands are production-namespace only. `overlays/dev` sets `namespace: afterglow-dev`; applying the root ConfigMap/Secret as-is does not make `afterglow-config` or `afterglow-secrets` visible to dev pods. To use the dev overlay directly, create equivalent ConfigMap/Secret objects in `afterglow-dev` or manage them through ArgoCD/ExternalSecret.

```bash
kubectl create namespace afterglow
# If Builder SSH is unused, an empty file is enough to satisfy the required Secret key.
# Use a real private-key file when Builder SSH is enabled.
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

### 2. Apply Production ConfigMap and Kustomize

```bash
# The afterglow.conf ConfigMap is not part of the prod overlay; apply it first.
kubectl apply -f deploy/k8s-template/configmap.yaml

# Production
kubectl apply -k deploy/k8s-template/overlays/prod
```

### 3. Verify

```bash
kubectl get all -n afterglow
kubectl get ingress -n afterglow

# Logs
kubectl logs -f deployment/backend -n afterglow
kubectl logs -f deployment/frontend -n afterglow
```

### Key ConfigMap Settings

`deploy/k8s-template/configmap.yaml` provides the runtime `afterglow.conf` inline. When generated by `generate_k8s.py`, the ConfigMap contains browser/frontend keys `APP_REDIS_URL`, `APP_ORIGIN`, `PUBLIC_S3_BASE`, `APP_GRAFANA_BASE`, plus `afterglow.conf`.

```yaml
data:
  APP_ORIGIN: "https://afterglow.example.com"
  APP_REDIS_URL: "redis://redis:6379/0"
  PUBLIC_S3_BASE: "https://s3.example.com"
  APP_GRAFANA_BASE: "https://grafana.example.com"
  afterglow.conf: |
    [openstack]
    auth_url = "https://keystone.example.com:5000/v3"
    # password is injected from afterglow-secrets/OS_PASSWORD
```

Do not put secret values in the ConfigMap. `OS_PASSWORD`, `SECRET_KEY`, `GITLAB_OIDC_CLIENT_SECRET`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL`, `PROMETHEUS_PASSWORD`, and `BUILDER_SSH_PRIVATE_KEY` come from `afterglow-secrets` as environment variables or a Secret volume.

`generate_k8s.py --config ./afterglow.conf --output-dir deploy/k8s-template` writes `configmap.yaml`, `secret.yaml`, and `grafana-deployment.yaml`. If `[app].secret_key` is empty, `change-me-in-production`, or shorter than 32 characters, `secret.yaml` generation fails to match the Kubernetes production guard.

### Ingress Domain

`deploy/k8s-template/ingress.yaml`:

```yaml
spec:
  rules:
    - host: afterglow.example.com
      http:
        paths:
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
                  number: 3000
```

> **Note**: The frontend's `PUBLIC_API_BASE` environment variable must point at an external URL reachable from the browser. Pointing it at a cluster-internal address (`http://backend:8000`) will fail because the browser cannot resolve it.

```yaml
# frontend Deployment environment
- name: PUBLIC_API_BASE
  value: "https://afterglow.example.com"
- name: ORIGIN
  value: "https://afterglow.example.com"
```

### Monitoring Stack

```bash
# Deploy the full monitoring stack
kubectl apply -k deploy/k8s-template/monitoring/

# Port-forward for local access
kubectl port-forward svc/grafana 3001:3000 -n afterglow
kubectl port-forward svc/prometheus 9090:9090 -n afterglow
```

### Runtime Config and Secret Contract

Kubernetes Python services use the production guard, unlike Docker Compose local development.

| Deployment | Config file | Secret references |
|---|---|---|
| `backend` | `/app/afterglow.conf` | `OS_PASSWORD`, `SECRET_KEY`, `GITLAB_OIDC_CLIENT_SECRET`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL`, `PROMETHEUS_PASSWORD`, `BUILDER_SSH_PRIVATE_KEY` |
| `drover` (`worker`) | `/app/afterglow.conf` | `OS_PASSWORD`, `SECRET_KEY`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL` |
| `notion-worker` | `/app/afterglow.conf` | `OS_PASSWORD`, `SECRET_KEY`, `K3S_KUBECONFIG_ENCRYPTION_KEY`, `DATABASE_URL` |

All three run with `AFTERGLOW_ENV=production`; do not put `AFTERGLOW_ALLOW_INSECURE=1` in Kubernetes manifests. If you generate manifests with `generate_k8s.py`, `[app].secret_key` must be set, must not be `change-me-in-production`, and must be at least 32 characters or `secret.yaml` generation fails.

### Helm Deployment

The Helm chart follows the same contract. `backend`, `drover`, and `notion-worker` mount `afterglow-config/afterglow.conf` at `/app/afterglow.conf` and read `afterglow-secrets/SECRET_KEY`.

Secret ownership has two supported modes.

1. **ExternalSecret/ArgoCD owns `afterglow-secrets`**: leave `values.yaml` `secrets.osPassword` empty. Helm will not render the Secret and Deployments will reference the existing Secret.
2. **Helm renders the Secret directly**: when `secrets.osPassword` is set, Helm creates `afterglow-secrets`; `secrets.secretKey`, `secrets.databaseUrl`, and `secrets.k3sKubeconfigEncryptionKey` are also required. Optional GitLab/Prometheus/Builder/Grafana secret keys are still emitted, even when their values are empty. Missing required values fail at template time.

```bash
helm template afterglow helm/afterglow --namespace afterglow \
  --set secrets.osPassword='<openstack-password>' \
  --set secrets.secretKey="$(openssl rand -hex 32)" \
  --set secrets.k3sKubeconfigEncryptionKey="$(openssl rand -hex 32)" \
  --set secrets.databaseUrl='mysql+asyncmy://afterglow:<db-password>@mariadb/afterglow'
```

---

## ArgoCD GitOps Deployment

Automatically syncs `dev` branch changes to the cluster.

### 1. Install ArgoCD (if not present)

```bash
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 2. Register Applications

```bash
kubectl apply -f argocd/00-namespace.yaml
kubectl apply -f argocd/01-appproject.yaml
kubectl apply -f argocd/03-ingress.yaml
kubectl apply -f argocd/04-server-config.yaml

# Generate Helm Applications. The generated files contain Secret values;
# never commit them.
backend/.venv/bin/python argocd/generate_helm_application.py dev
KUBECONFIG=/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig \
  kubectl apply -f deploy/k8s/argocd-application-dev.yaml

backend/.venv/bin/python argocd/generate_helm_application.py prod
KUBECONFIG=/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig \
  kubectl apply -f deploy/k8s/argocd-application-prod.yaml
```

`generate_helm_application.py` is the only supported Application generation path.
Both Applications use `helm/afterglow` as their source and include the Helm
valuesObject, `selfHeal`, Image Updater settings, and
`ignoreDifferences` for `afterglow-config`/`afterglow-secrets`.
Do not recreate or apply the removed `argocd/02-application.*.yaml`
Kustomize Applications.

### 3. Verify Sync

```bash
argocd app list
argocd app sync afterglow-dev
argocd app sync afterglow-prod
argocd app get afterglow-dev
```

### 3. Verify Sync

```bash
argocd app list
argocd app sync afterglow-dev
argocd app get afterglow-dev
```

---

## TLS / HTTPS

Use cert-manager to issue Let's Encrypt certificates automatically.

```bash
# Install cert-manager
kubectl apply -f deploy/k8s-template/cert-manager.yaml
```

Create a ClusterIssuer:

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

Add TLS to the Ingress:

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

## Upgrading

### Docker Compose

```bash
# Development: rebuild reviewed current source.
npm run services:up

# Production: synchronize a reviewed published tag/digest, never build locally.
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml pull
docker compose --env-file /path/to/production.env -f docker-compose.prod.yml up -d --no-build --wait
```

### Database Schema Migrations

`auto_create_tables` does not add columns to existing tables. Before rolling out an image that references a new ORM column, apply its SQL migration to the production database. Use the logical IDs in `backend/migrations/manifest.txt` to determine the required migrations and order; never rely on a numeric filename prefix alone.

Example for the 2026-08-02 chat message timezone migration in local Compose:

```bash
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml exec -T afterglow-mariadb sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' \
  < backend/migrations/070_chat_message_local_timestamps.sql
```

For Kubernetes or an external MariaDB, run the same SQL file through the approved production database access path. Do not place database passwords on the command line or in Git. Confirm both columns before rolling out the backend:

```sql
SHOW COLUMNS FROM chat_messages LIKE 'created_at_local';
SHOW COLUMNS FROM chat_messages LIKE 'created_timezone';
```

### Kubernetes

```bash
# Rolling restart after image, ConfigMap, or Secret updates
kubectl rollout restart deployment/backend -n afterglow
kubectl rollout restart deployment/frontend -n afterglow
kubectl rollout restart deployment/drover -n afterglow
kubectl rollout restart deployment/notion-worker -n afterglow
kubectl rollout status deployment/backend -n afterglow
```

When using ArgoCD, pushing to the `dev` branch triggers an automatic sync.

---

## Troubleshooting

### Backend Cannot Reach OpenStack

```bash
# Check logs
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml logs backend
kubectl logs -f deployment/backend -n afterglow

# Test Keystone connectivity
curl -s https://keystone.example.com:5000/v3 | python3 -m json.tool
```

### Redis Connection Errors

```bash
docker compose --env-file .local-services/compose.env -f docker-compose.dev.yml exec redis redis-cli ping
# or
kubectl exec -n afterglow deployment/backend -- redis-cli -u redis://redis:6379 ping
```

### Frontend Cannot Reach the API

1. Confirm `PUBLIC_API_BASE` resolves to a browser-reachable external URL
2. Restart the frontend after changing the domain:
   ```bash
   kubectl rollout restart deployment/frontend -n afterglow
   ```

### Pods Stuck Pending

```bash
kubectl describe pod -l app=backend -n afterglow
# Check PVC binding or resource pressure
kubectl get pvc -n afterglow
kubectl describe nodes
```
