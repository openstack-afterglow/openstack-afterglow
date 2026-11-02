#!/usr/bin/env bash
# Afterglow 배포 스크립트 — OCI Helm 차트 + 로컬 values/secrets 파일
#
# 사용법:
#   ./deploy/helm-upgrade.sh dev [--version 1.15.2] [--dry-run]
#   ./deploy/helm-upgrade.sh prod [--version 1.15.2]
#
# 필요 파일 (배포 서버 로컬, git 미추적):
#   helm/afterglow/values-<env>.yaml   ← deploy/values-dev-example.yaml 참조
#   helm/afterglow/secrets-<env>.yaml  ← deploy/secrets-example.yaml 참조

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHART_DIR="$REPO_ROOT/helm/afterglow"
OCI_REPO="oci://ghcr.io/openstack-afterglow/charts/afterglow"

# ── 인수 파싱 ──────────────────────────────────────────────────────────────
ENV="${1:-}"
shift || true

VERSION=""
DRY_RUN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)  VERSION="$2"; shift 2 ;;
    --dry-run)  DRY_RUN="--dry-run"; shift ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$ENV" ]] || [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "사용법: $0 <dev|prod> [--version X.Y.Z] [--dry-run]" >&2
  exit 1
fi

# ── 차트 버전 ──────────────────────────────────────────────────────────────
if [[ -z "$VERSION" ]]; then
  VERSION=$(grep '^version:' "$CHART_DIR/Chart.yaml" | awk '{print $2}')
fi

# ── 환경별 설정 ────────────────────────────────────────────────────────────
case "$ENV" in
  dev)  NAMESPACE="afterglow-dev";  RELEASE="afterglow-dev"  ;;
  prod) NAMESPACE="afterglow";      RELEASE="afterglow-prod" ;;
esac

VALUES_FILE="$CHART_DIR/values-$ENV.yaml"
SECRETS_FILE="$CHART_DIR/secrets-$ENV.yaml"

# ── 파일 존재 확인 ─────────────────────────────────────────────────────────
if [[ ! -f "$VALUES_FILE" ]]; then
  echo "환경 설정 파일 없음: $VALUES_FILE" >&2
  echo "  → deploy/values-dev-example.yaml 를 복사해 편집하세요" >&2
  exit 1
fi
if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "시크릿 파일 없음: $SECRETS_FILE" >&2
  echo "  → deploy/secrets-example.yaml 를 복사해 편집하세요" >&2
  exit 1
fi

# ── 배포 ──────────────────────────────────────────────────────────────────
echo "▶ 배포 시작 ${DRY_RUN:+(dry-run)}"
echo "  환경        : $ENV"
echo "  릴리즈      : $RELEASE"
echo "  네임스페이스: $NAMESPACE"
echo "  차트 버전   : $VERSION"
echo ""

helm upgrade --install "$RELEASE" \
  "$OCI_REPO" \
  --version "$VERSION" \
  -f "$VALUES_FILE" \
  -f "$SECRETS_FILE" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --wait \
  --timeout 10m \
  ${DRY_RUN}

if [[ -n "$DRY_RUN" ]]; then
  echo ""
  echo "✓ dry-run 완료 — 실제 배포하려면 --dry-run 없이 재실행"
  exit 0
fi

echo ""
echo "✓ 배포 완료: $RELEASE ($VERSION) → namespace/$NAMESPACE"
echo ""
echo "상태 확인:"
echo "  kubectl get pods -n $NAMESPACE"
echo "  kubectl rollout status deploy -n $NAMESPACE"
echo "  kubectl get svc,ingress -n $NAMESPACE"
