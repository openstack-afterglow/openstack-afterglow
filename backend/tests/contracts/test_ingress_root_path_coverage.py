"""Regression coverage for root-scoped FastAPI routes and static Ingress routing."""

from pathlib import Path

import pytest
import yaml

from app.main import app
from app.services.mcp_control_plane.transport import MCP_PATH

ROOT = Path(__file__).resolve().parents[3]

# These routes are nulled when AFTERGLOW_ENV=production, which every k8s backend Deployment sets.
FASTAPI_DOC_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})
EXPECTED_ROOT_ROUTES = frozenset(
    {
        "/.well-known/oauth-protected-resource/{resource_path:path}",
        "/.well-known/oauth-authorization-server/{issuer_path:path}",
        "/{mcp_path:path}/oauth/register",
        "/{mcp_path:path}/oauth/authorize",
        "/{mcp_path:path}/oauth/token",
        "/{mcp_path:path}/oauth/revoke",
        # Origin-root MCP resource only: Helm routes exact "/", /oauth and /.well-known of a
        # dedicated MCP host to the backend. Shared web hosts keep /oauth on the frontend consent page.
        "/.well-known/oauth-protected-resource",
        "/oauth/register",
        "/oauth/authorize",
        "/oauth/token",
        "/oauth/revoke",
    }
)
INGRESS_MANIFESTS = (
    "deploy/k8s-template/ingress.yaml",
    "deploy/k8s-template/overlays/dev/ingress.yaml",
    "deploy/k8s-template/overlays/prod/ingress.yaml",
)


def _is_api_path(path: str) -> bool:
    """Match the element-aware semantics of Kubernetes Ingress Prefix paths."""
    return path == "/api" or path.startswith("/api/")


def _root_scoped_route_paths() -> frozenset[str]:
    return frozenset(
        path
        for route in app.router.routes
        if (path := getattr(route, "path", None)) and not _is_api_path(path) and path not in FASTAPI_DOC_PATHS
    )


def test_root_scoped_routes_match_snapshot():
    assert _root_scoped_route_paths() == EXPECTED_ROOT_ROUTES, (
        "루트 경로 라우트가 변경되었습니다. deploy/k8s-template 의 Ingress 3종과 "
        "helm/afterglow/templates/ingress.yaml 에 대응 path 를 추가한 뒤 스냅샷을 갱신하세요."
    )


def test_default_mcp_transport_path_stays_under_api_prefix():
    assert MCP_PATH.startswith("/api/")


def test_api_prefix_filter_respects_path_boundaries():
    assert _is_api_path("/api")
    assert _is_api_path("/api/v1/mcp")
    assert not _is_api_path("/apiary")
    assert not _is_api_path("/api-v2")


@pytest.mark.parametrize("manifest", INGRESS_MANIFESTS)
def test_ingress_hosts_serving_api_also_serve_well_known(manifest):
    ingress = yaml.safe_load((ROOT / manifest).read_text(encoding="utf-8"))

    for rule in ingress["spec"]["rules"]:
        backend_paths = {
            path["path"]: path for path in rule["http"]["paths"] if path["backend"]["service"]["name"] == "backend"
        }
        if "/api" in backend_paths:
            message = f"{manifest}: {rule['host']} routes /api to backend but not /.well-known"
            assert "/.well-known" in backend_paths, message
            well_known = backend_paths["/.well-known"]
            assert well_known["pathType"] == "Prefix", message
            assert well_known["backend"]["service"]["port"]["number"] == 8000, message


@pytest.mark.parametrize("manifest", INGRESS_MANIFESTS)
def test_ingress_catch_all_routes_to_frontend(manifest):
    ingress = yaml.safe_load((ROOT / manifest).read_text(encoding="utf-8"))

    for rule in ingress["spec"]["rules"]:
        catch_all = next(path for path in rule["http"]["paths"] if path["path"] == "/")
        service = catch_all["backend"]["service"]
        assert service["name"] == "frontend"
        assert service["port"]["number"] == 3080
