# ArgoCD 자동 배포 설정

버전 변경 시 자동 배포를 위한 ArgoCD Application 설정입니다.

## 파일 구조

```
argocd/
  00-namespace.yaml              # argocd 네임스페이스
  01-appproject.yaml             # AppProject (권한 범위)
  03-ingress.yaml                # ArgoCD UI Ingress
  04-server-config.yaml          # ArgoCD server 설정 (insecure, URL 등)
  image-updater/
    install.yaml                 # Image Updater 공식 매니페스트 v1.1.1 + log.level=info
    imageupdater-prod.yaml       # ImageUpdater CR — prod app annotation 감시
```

Application 매니페스트는 `argocd/generate_helm_application.py`가
`deploy/k8s/argocd-application-{dev,prod}.yaml`로 생성합니다. 이 파일은 Secret 값을
포함하므로 git에 커밋하지 않습니다. `argocd/02-application.*.yaml` 형태의
Kustomize Application은 제거했으며, Helm Application만 사용합니다.

## 배포 흐름

```
helm/afterglow 차트 또는 이미지 변경
  → ArgoCD Helm Application 자동 sync
  → 새 Pod 롤아웃

환경별 설정 변경
  → helm/afterglow/values-<env>.yaml 또는 secrets-<env>.yaml 수정
  → generate_helm_application.py 실행
  → 생성된 Helm Application CR 적용

관리자 ConfigMap/Secret 변경
  → generate_k8s.py가 환경 프로필과 함께 매니페스트 생성
  → kubectl apply
  → ArgoCD ignoreDifferences가 직접 적용한 data를 보존
```

---

## 최초 설치 순서

### 1. ArgoCD 설치

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 2. ArgoCD Image Updater 설치 (선언적, 파일로 직접)

두 단계로 나눠 적용합니다. CRD 가 등록된 뒤에 ImageUpdater CR 을 생성해야 합니다.

```bash
# Step 1: CRD + RBAC + Deployment + ConfigMap (log.level=info 포함)
kubectl apply -f argocd/image-updater/install.yaml

# Step 2: ImageUpdater CR — CRD 등록 완료 후 적용
kubectl apply -f argocd/image-updater/imageupdater-prod.yaml
```

- `install.yaml` — CRD, RBAC, Deployment, ConfigMap 일괄 포함 (v1.1.1, log.level=info 내장)
- `imageupdater-prod.yaml` — ImageUpdater CR: afterglow-prod 앱의 annotation 읽어 digest 감시

업그레이드 시 `argocd/image-updater/install.yaml` 을 새 버전으로 교체 후 재적용.

### 3. GHCR pull-secret 생성 (필수 — private 패키지)

Image Updater 가 GHCR 이미지 digest 를 polling 하려면 인증이 필요합니다.
`argocd` 네임스페이스에 secret 을 생성하고, Application annotation 에 선언된
`pullsecret:argocd/ghcr-secret` 과 이름을 맞춥니다.

```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=openstack-afterglow \
  --docker-password=<GITHUB_PAT_READ_PACKAGES> \
  -n argocd
```

> 생성된 Helm Application의 Image Updater annotation이 이 secret을 가리킵니다.
> secret이 없으면 Image Updater가 401로 실패합니다.

### 4. GitHub 레포 등록

```bash
argocd repo add https://github.com/openstack-afterglow/openstack-afterglow.git \
  --username openstack-afterglow \
  --password <GITHUB_PAT>
```

### 5. ArgoCD 리소스 적용

```bash
# 네임스페이스와 AppProject 먼저 적용
kubectl apply -f argocd/00-namespace.yaml
kubectl apply -f argocd/01-appproject.yaml
kubectl apply -f argocd/03-ingress.yaml
kubectl apply -f argocd/04-server-config.yaml

# Helm Application 생성 및 적용 — dev/prod 모두 같은 경로 사용
backend/.venv/bin/python argocd/generate_helm_application.py dev
KUBECONFIG=/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig \
  kubectl apply -f deploy/k8s/argocd-application-dev.yaml

backend/.venv/bin/python argocd/generate_helm_application.py prod
KUBECONFIG=/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig \
  kubectl apply -f deploy/k8s/argocd-application-prod.yaml

# 최초 수동 sync (이후 자동)
argocd app sync afterglow-dev
argocd app sync afterglow-prod
```

---

## 동작 방식

### prod 환경
- ArgoCD가 `main` 브랜치의 `helm/afterglow` 차트를 추적.
- `afterglow-prod` Application은 `targetRevision: main`과 Helm valuesObject를 사용.
- Image Updater가 `:latest` digest 변경을 감지하면 Application을 patch하고 새 Pod를 롤아웃.

### dev 환경
- ArgoCD가 `dev` 브랜치의 `helm/afterglow` 차트를 추적.
- `afterglow-dev` Application은 `targetRevision: dev`와 Helm valuesObject를 사용.
- 이미지 digest 변경과 차트 변경을 ArgoCD가 자동 sync한다.

### 생성기 규칙
- `generate_helm_application.py`가 유일한 Application 생성 경로다.
- 생성된 Application에는 Helm source, `selfHeal`, Image Updater annotation,
  ConfigMap/Secret `ignoreDifferences`가 함께 들어간다.
- 삭제된 `argocd/02-application.*.yaml`을 다시 만들거나 적용하지 않는다.

### 관리자 ConfigMap/Secret 직접 반영

`afterglow-config`와 `afterglow-secrets`는 Helm이 최초 생성하지만, 두 리소스의
`data`는 관리자 운영 영역으로 지정되어 ArgoCD `ignoreDifferences`에 등록됩니다.
따라서 `selfHeal: true`를 유지하면서도 관리자가 직접 적용한 값은 자동 복구되지
않습니다. 이 설정은 `generate_helm_application.py`로 Application을 다시 생성하여
클러스터에 적용해야 활성화됩니다.

DB URL을 다른 schema/server로 바꾸는 경우에도 아래 **전체 Bash 블록**을 실행합니다.
Secret/ConfigMap만 적용하고 재시작하면 새 DB의 SQL106/107/108이 준비되지 않을 수 있습니다.
승인된 대상·원 DB/암호화 키·복구 지점을 먼저 확인하고, 자동 sync/Image Updater와
다른 운영자의 설정 변경·롤아웃이 이 절차에 끼어들지 않도록 조정하세요.
기존 Pod는 subPath/환경변수의 이전 설정을 계속 사용합니다. 이 절차는 기존 writer를
중지하거나 DDL의 implicit commit을 되돌리는 기능이 아니며, 필요한 writer 정지는 별도
maintenance 절차로 수행합니다. `--if-configured`는 **effective DB URL이 비어 있을 때만**
건너뛰며, 설정된 DB의 접속/권한/검증 실패를 성공으로 바꾸지 않습니다.
먼저 ArgoCD의 승인된 backend 대상 image를 immutable `repository@sha256:<digest>`
형태로 고정하고 rollout이 안정됐는지 확인합니다(`tag@sha256:<digest>`도 허용).
아래 절차는 실제 Deployment의 대상 image를 읽어 두 Job에 고정합니다. `:latest`/`:dev`
같은 mutable tag만 관측되면 config 반영 전에 중단하며, 생성기 기본 image와 실행
backend가 같다고 추정하지 않습니다. Image 교체가 필요하면 이 config-only 절차와
섞지 말고 해당 image의 사전 qualification 및 GitOps 고정을 먼저 완료하세요.
Application 정책 설치/갱신은 위 **최초 설치 순서 5**의 별도 사전 작업입니다.
그 작업이 완료된 뒤 maintenance용 자동 sync/Image Updater 중지를 적용하고 유지하세요.
`generate_helm_application.py`가 생성한 Application은 자동 sync/selfHeal을 다시 켜므로,
아래 guarded config-only 절차 안에서는 Application을 재생성하거나 적용하지 않습니다.

```bash
(
set +x
set -euo pipefail
umask 077
ENV=${ENV:-dev}
NAMESPACE=${NAMESPACE:-afterglow-dev}
KUBECONFIG=${KUBECONFIG:-/Users/pieroot/code/afterglow/deploy/k8s/kubeconfig}
export KUBECONFIG
PYTHON=${PYTHON:-backend/.venv/bin/python}
# 매번 새 디렉터리와 새 Job identity 사용. 생성물에는 Secret이 있으므로 출력/커밋 금지.
OUT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/afterglow-k8s-${ENV}.XXXXXX")
trap 'printf "%s\n" "Config update stopped; no further rollout. Inspect protected local artifacts." >&2' ERR

# dev는 반드시 환경별 URL 오버라이드를 함께 적용한다.
"$PYTHON" generate_k8s.py \
  --config afterglow.conf \
  --override "deploy/afterglow-$ENV.conf" \
  --namespace "$NAMESPACE" \
  --output-dir "$OUT_DIR" >"$OUT_DIR/generation.log" 2>&1

# Kustomize namespace/image 변환을 보존하되 전체 트리(workload)는 적용하지 않는다.
# 렌더 결과에는 Secret이 있으므로 stdout/log로 내보내지 않는다.
kubectl kustomize "$OUT_DIR" >"$OUT_DIR/rendered.yaml" 2>"$OUT_DIR/render.log"
kubectl -n "$NAMESPACE" get deployment/backend \
  -o 'jsonpath={.spec.template.spec.containers[?(@.name=="backend")].image}' \
  >"$OUT_DIR/backend-image.txt" 2>"$OUT_DIR/backend-image.log"
SCHEMA_JOB=$("$PYTHON" - "$OUT_DIR" "$NAMESPACE" <<'PY'
import copy
import re
import sys
from pathlib import Path

import yaml

out = Path(sys.argv[1])
resources = list(yaml.safe_load_all((out / "rendered.yaml").read_text()))
jobs = [item for item in resources if item and item.get("kind") == "Job"]
if len(jobs) != 1:
    raise SystemExit("Expected exactly one freshly generated schema Job")
job = jobs[0]
name = job["metadata"]["name"]
if not re.fullmatch(r"schema-bootstrap-sql108-[0-9a-f]{32}", name):
    raise SystemExit("Expected the freshly generated schema Job identity")
if job["metadata"].get("namespace") != sys.argv[2]:
    raise SystemExit("Schema Job namespace mismatch")
spec = job["spec"]
if spec.get("parallelism") != 1 or spec.get("completions") != 1 or spec.get("backoffLimit") != 0:
    raise SystemExit("Expected a singleton schema Job without automatic retries")
containers = spec["template"]["spec"]["containers"]
if len(containers) != 1 or containers[0].get("command") != [
    "python", "-m", "scripts.bootstrap_schema", "--if-configured"
]:
    raise SystemExit("Unexpected schema bootstrap command")
image = (out / "backend-image.txt").read_text().strip()
if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", image):
    raise SystemExit("Pin the intended backend Deployment image to an immutable digest first")
containers[0]["image"] = image
(out / "schema-bootstrap.yaml").write_text(yaml.safe_dump(job))
verify = copy.deepcopy(job)
verify["metadata"]["name"] = name + "-verify"
verify["spec"]["template"]["spec"]["containers"][0]["command"].append("--verify-only")
(out / "schema-verify.yaml").write_text(yaml.safe_dump(verify))
print(name)  # 비밀이 아닌 생성 identity만 shell에 전달한다.
PY
)

kubectl apply -f "$OUT_DIR/secret.yaml" >"$OUT_DIR/config-apply.log" 2>&1
kubectl apply -f "$OUT_DIR/configmap.yaml" >>"$OUT_DIR/config-apply.log" 2>&1

# 과거 Completed Job/label selector를 재사용하지 않는다. create 충돌도 즉시 중단한다.
kubectl -n "$NAMESPACE" create -f "$OUT_DIR/schema-bootstrap.yaml"
kubectl -n "$NAMESPACE" wait --for=condition=complete --timeout=600s "job/$SCHEMA_JOB"

# 같은 image/envFrom/config volume으로 새 DB를 읽기 전용 검증. DDL Job 성공만으로 재시작 금지.
kubectl -n "$NAMESPACE" create -f "$OUT_DIR/schema-verify.yaml"
kubectl -n "$NAMESPACE" wait --for=condition=complete --timeout=600s "job/${SCHEMA_JOB}-verify"

# 검증 도중 backend 대상 digest가 바뀌었다면 검증 결과를 재사용하지 않는다.
kubectl -n "$NAMESPACE" get deployment/backend \
  -o 'jsonpath={.spec.template.spec.containers[?(@.name=="backend")].image}' \
  >"$OUT_DIR/backend-image-before-rollout.txt" 2>"$OUT_DIR/backend-image-before-rollout.log"
cmp -s "$OUT_DIR/backend-image.txt" "$OUT_DIR/backend-image-before-rollout.txt"

# 두 exact Job이 성공한 뒤에만 subPath/Secret 소비 Pod를 롤링 재시작한다.
kubectl -n "$NAMESPACE" rollout restart deployment backend frontend notion-worker
for deployment in backend frontend notion-worker; do
  kubectl -n "$NAMESPACE" rollout status "deployment/$deployment" --timeout=600s
done
)
```

Bootstrap/읽기 전용 검증 Job 실패 또는 timeout이면 블록은 재시작 전에 중단합니다.
생성된 exact Job 이름으로 상태를 확인하고, 자격 증명/설정 원문이나 보호된 로컬 로그를
공유하지 마세요. 원인을 해결한 뒤 전체 생성 절차를 다시 실행하여 새 identity를 사용하며,
과거 Job 삭제·재사용이나 실패 무시로 gate를 우회하지 않습니다. ConfigMap/Secret은 이미
갱신됐을 수 있으므로 실패 후에도 자동 rollout을 계속 막고 대상 설정·복구 방침을 검토합니다.
검증 중 설정/image가 바뀌면 결과를 재사용하지 말고 승인된 동일 image/config로 다시 수행합니다.
Backend/worker replica의 read-only init gate도 그대로 유지하며 singleton DDL을 대신하지 않습니다.
`--namespace`는 환경 프로필을 필수로 선택합니다. `afterglow-dev`는
`deploy/afterglow-dev.conf`, `afterglow`는 `deploy/afterglow-prod.conf`를
자동으로 먼저 적용합니다. dev를 prod `afterglow.conf`로 생성하면
`https://cloud.dmslab.re.kr`이 들어갈 수 있으므로 dev 명령에서 환경 프로필을
생략하면 안 됩니다.
`afterglow-config`/`afterglow-secrets`를 Helm values로 바꿀 때는 `ignoreDifferences`
때문에 해당 values 변경만으로는 리소스 데이터가 갱신되지 않으므로, 위의 직접 적용
절차를 사용합니다. 데이터 전체를 무시하므로 키를 삭제하거나 잘못된 값을 넣었을 때의
검증과 롤백은 관리자가 담당해야 합니다.

---

## Image Updater 상태 확인

```bash
# pod 상태
kubectl -n argocd get pods -l app.kubernetes.io/name=argocd-image-updater

# 로그 (afterglow 관련 + 에러)
kubectl -n argocd logs deploy/argocd-image-updater-controller --tail=200 | \
  grep -Ei 'afterglow|error|warn|unauthorized'

# ImageUpdater CR 상태
kubectl -n argocd get imageupdater afterglow-prod -o yaml

# prod Application in-cluster image override 확인
kubectl -n argocd get app afterglow-prod \
  -o jsonpath='{.spec.source.kustomize.images}' && echo
```
