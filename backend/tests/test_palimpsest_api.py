"""Palimpsest 조회 API + digest 백필 회귀 테스트.

고정하는 계약:
- 검색 파라미터는 화이트리스트 검증 후에만 쿼리에 도달한다(422)
- 미공개 레이어는 **존재 여부조차 흘리지 않는다**(404)
- 관리자 전용 엔드포인트는 member 토큰을 거부한다
- 백필은 셸 인젝션을 막고, 실패해도 access rule 과 임시 VM 을 반드시 회수한다
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import _AUDIT_PREFIX_MAP
from app.services.palimpsest_backfill import BackfillError, backfill_digests, build_hash_command
from app.services.palimpsest_digest import DIGEST_FAILED, DIGEST_PENDING, DIGEST_READY, parse_digest_sentinels

_HEX_A = "a" * 64

# pytest 설정이 `asyncio_mode = "auto"` 이므로 async 테스트에 별도 마커가 필요 없다.
# 모듈 전역 asyncio 마커는 동기 테스트까지 잡아 경고를 낸다.


# ---------------------------------------------------------------------------
# 감사 매핑 / 라우트 등록
# ---------------------------------------------------------------------------


async def test_audit_prefix_map_covers_palimpsest_surfaces():
    # 이 매핑이 빠지면 fail-closed 감사 미들웨어가 조용히 무력화된다(CLAUDE.md §API 3).
    prefixes = {prefix for prefix, _ in _AUDIT_PREFIX_MAP}

    assert "/api/v1/palimpsest" in prefixes
    assert "/api/v1/admin/palimpsest" in prefixes


async def test_palimpsest_routes_are_mounted_under_v1_only():
    from app.main import app

    # 허브·빌드·패키지 경로는 각자의 테스트 파일이 고정한다 — 여기서는 레이어/관리자 표면만.
    excluded = ("/palimpsest/hub", "/palimpsest/builds", "/palimpsest/packages", "/palimpsest/package-keys")
    paths = {
        route.path
        for route in app.routes
        if "palimpsest" in route.path and not any(part in route.path for part in excluded)
    }

    assert paths == {
        "/api/v1/palimpsest/layers",
        "/api/v1/palimpsest/layers/{artifact_id}/ancestors",
        "/api/v1/admin/palimpsest/artifacts",
        "/api/v1/admin/palimpsest/artifacts/backfill-digest",
        "/api/v1/admin/palimpsest/digest-status",
    }
    # 레거시 /api 는 baked cloud-init 3종만 허용된다 — 신규 추가 금지
    assert not any(route.path.startswith("/api/palimpsest") for route in app.routes)


async def test_second_generation_union_surface_stays_removed():
    """2세대 `/api/v1/union` 은 폐기됐다 — 되살아나면 레이어 시스템이 다시 갈라진다.

    인프라(중앙 Manila share, CephX keyring, Builder VM)가 배포된 적 없는 설계였고,
    프론트 호출자도 nav 에서 도달 불가능한 고립 페이지뿐이었다. docs/palimpsest.md §1.
    `union_layers`/`union_templates`/`union_user_mounts` 테이블은 데이터 보존을 위해 남아 있으나
    ORM·API·서비스는 없다.
    """
    import importlib

    from app.main import _AUDIT_PREFIX_MAP, app

    assert not any(route.path.startswith("/api/v1/union") for route in app.routes)
    assert not any(prefix.startswith("/api/v1/union") for prefix, _ in _AUDIT_PREFIX_MAP)

    for gone in ("app.services.union_layers", "app.models.union", "app.api.union.layers"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(gone)

    import app.models.db as db_models

    for gone_orm in ("UnionLayer", "UnionTemplate", "UnionUserMount"):
        assert not hasattr(db_models, gone_orm), f"{gone_orm} ORM 이 되살아났다"

    # 3세대(= Palimpsest 코어) 표면은 그대로여야 한다
    paths = {route.path for route in app.routes}
    assert any(p.startswith("/api/v1/admin/libraries") for p in paths)
    assert any(p.startswith("/api/v1/libraries/squashfs") for p in paths)


# ---------------------------------------------------------------------------
# 검색 파라미터 검증
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("digest", "not-a-digest"),
        ("digest", "sha256:zz"),
        ("digest_prefix", "abc"),  # 4자 미만
        ("digest_prefix", "zzzz"),  # hex 아님
        ("md5", "abc"),
        ("chain_id", "nope"),
        ("name", "Bad Name"),
        ("name", "'; DROP TABLE layer_artifacts; --"),
        ("kind", "UPPER"),
    ],
)
async def test_search_rejects_malformed_filters(client, param, value):
    resp = await client.get("/api/v1/palimpsest/layers", params={param: value})

    assert resp.status_code == 422, resp.text


async def test_search_requires_authentication():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # dependency_overrides 없이 = 인증 의존성이 실제로 동작
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/palimpsest/layers")

    assert resp.status_code in (401, 403)


async def test_search_filters_are_applied_to_visible_rows_only(client):
    captured = {}

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, stmt):
            captured["sql"] = str(stmt)
            return _Result()

    with patch("app.api.palimpsest.layers.get_session_factory", return_value=lambda: _Session()):
        resp = await client.get(
            "/api/v1/palimpsest/layers",
            params={"digest_prefix": _HEX_A[:8], "kind": "uv"},
        )

    assert resp.status_code == 200
    sql = captured["sql"]
    # 가시성 조건이 항상 붙어야 한다
    assert "is_published" in sql
    assert "is_sealed" in sql
    assert "blob_digest" in sql


async def test_ancestors_hides_unpublished_layer_as_404(client):
    row = MagicMock(is_published=False, is_sealed=True)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, _model, _pk):
            return row

    with patch("app.api.palimpsest.layers.get_session_factory", return_value=lambda: _Session()):
        resp = await client.get("/api/v1/palimpsest/layers/1/ancestors")

    # 미공개 레이어의 존재를 확인해 주면 안 된다 — 403 이 아니라 404
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 관리자 전용
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/palimpsest/artifacts"),
        ("get", "/api/v1/admin/palimpsest/digest-status"),
        ("post", "/api/v1/admin/palimpsest/artifacts/backfill-digest"),
    ],
)
async def test_admin_endpoints_reject_member(non_admin_client, method, path):
    resp = await getattr(non_admin_client, method)(path, **({"json": {}} if method == "post" else {}))

    assert resp.status_code == 403


async def test_backfill_endpoint_validates_limit(admin_client):
    resp = await admin_client.post("/api/v1/admin/palimpsest/artifacts/backfill-digest", json={"limit": 0})

    assert resp.status_code == 422


async def test_backfill_endpoint_reports_missing_prerequisites_as_503(admin_client):
    with patch(
        "app.api.palimpsest.admin.backfill_digests",
        AsyncMock(side_effect=BackfillError("DB 연결이 초기화되지 않았습니다")),
    ):
        resp = await admin_client.post("/api/v1/admin/palimpsest/artifacts/backfill-digest", json={"limit": 5})

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 해시 명령 (셸 인젝션 방어)
# ---------------------------------------------------------------------------


def test_hash_command_output_is_parseable_by_the_same_parser():
    command = build_hash_command("10.0.0.1:/layers/uv", "uvbase-latest.sqsh", "uvbase")

    # 빌드 경로와 같은 sentinel 포맷이어야 파서를 재사용할 수 있다
    assert "::AFTERGLOW::DIGEST::layer=" in command
    fake_stdout = f"::AFTERGLOW::DIGEST::layer=uvbase sha256={_HEX_A} md5={'d' * 32} size=10\n"
    assert parse_digest_sentinels(fake_stdout)["uvbase"].blob_digest == f"sha256:{_HEX_A}"


@pytest.mark.parametrize(
    "export_path",
    [
        "10.0.0.1:/layers/uv; rm -rf /",
        "10.0.0.1:/layers/uv\nrm -rf /",
        "10.0.0.1:/layers/$(whoami)",
        "10.0.0.1:/layers/`id`",
    ],
)
def test_hash_command_rejects_injected_export_path(export_path):
    # Manila API 반환값도 신뢰하지 않는다 (CLAUDE.md §1)
    with pytest.raises(BackfillError):
        build_hash_command(export_path, "uvbase-latest.sqsh", "uvbase")


@pytest.mark.parametrize(
    "sqsh",
    ["../../etc/passwd", "uvbase-latest.sqsh; id", "uvbase latest.sqsh", "uvbase-latest.txt"],
)
def test_hash_command_rejects_injected_sqsh_filename(sqsh):
    with pytest.raises(BackfillError):
        build_hash_command("10.0.0.1:/layers/uv", sqsh, "uvbase")


def test_hash_command_mounts_read_only():
    command = build_hash_command("10.0.0.1:/layers/uv", "uvbase-latest.sqsh", "uvbase")

    # 백필은 절대 레이어를 건드리면 안 된다 — 봉인된 불변 레이어다
    assert "-o ro,nolock" in command
    assert "trap cleanup EXIT" in command


# ---------------------------------------------------------------------------
# 백필 오케스트레이션
# ---------------------------------------------------------------------------


class _FactorySession:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def execute(self, _stmt):
        return _ScalarResult(self.store["ids"])

    async def get(self, _model, pk):
        return self.store["rows"].get(pk)

    async def commit(self):
        self.store["commits"] += 1


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


def _pending_row(artifact_id: int):
    row = MagicMock()
    row.id = artifact_id
    row.name = "uvbase"
    row.share_id = "share-1"
    row.sqsh_filename = "uvbase-latest.sqsh"
    row.digest_state = DIGEST_PENDING
    row.blob_digest = None
    row.blob_md5 = None
    row.size_bytes = None
    return row


async def test_backfill_returns_early_without_touching_openstack_when_nothing_pending():
    store = {"ids": [], "rows": {}, "commits": 0}
    with (
        patch("app.services.palimpsest_backfill.get_session_factory", return_value=lambda: _FactorySession(store)),
        patch("app.services.palimpsest_backfill.create_ephemeral_vm", AsyncMock()) as create_vm,
    ):
        result = await backfill_digests(limit=10)

    assert result == {"scanned": 0, "updated": 0, "failed": 0, "chain_updated": 0, "details": []}
    # 대상이 없으면 VM 을 띄우지 않는다
    create_vm.assert_not_awaited()


async def test_backfill_updates_pending_row_and_always_releases_resources():
    row = _pending_row(1)
    store = {"ids": [1], "rows": {1: row}, "commits": 0}
    vm = MagicMock(
        server_id="vm-1", host="1.2.3.4", key_path="/k", username="ubuntu", internal_ip="10.0.0.9", fip_id="fip-1"
    )
    stdout = f"::AFTERGLOW::DIGEST::layer=uvbase sha256={_HEX_A} md5={'d' * 32} size=2048\n"

    with (
        patch("app.services.palimpsest_backfill.get_session_factory", return_value=lambda: _FactorySession(store)),
        patch(
            "app.services.resource_policy_store.get_service_project_connection",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.resource_policy_store.resolve_policy_snapshot",
            new=AsyncMock(
                return_value={
                    "builder.flavor": {"id": "flavor-1", "name": "builder"},
                    "builder.network": {"id": "network-1", "name": "network"},
                }
            ),
        ),
        patch(
            "app.services.resource_policy_store.get_policy_snapshot",
            new=AsyncMock(return_value={"builder.floating_network": None}),
        ),
        patch("app.services.palimpsest_backfill.create_ephemeral_vm", AsyncMock(return_value=vm)),
        patch("app.services.palimpsest_backfill.delete_ephemeral_vm", AsyncMock()) as delete_vm,
        patch("app.services.palimpsest_backfill.manila") as manila_mod,
        patch(
            "app.services.palimpsest_backfill.ssh_executor.run_command",
            AsyncMock(return_value=(0, stdout, "")),
        ),
        patch("app.services.palimpsest_backfill._refresh_chain_ids", AsyncMock(return_value=3)),
    ):
        manila_mod.ensure_nfs_access_rule.return_value = {"access_id": "acc-1"}
        manila_mod.get_export_locations.return_value = ["10.0.0.1:/layers/uv"]
        result = await backfill_digests(limit=10)

    assert result["updated"] == 1
    assert result["failed"] == 0
    assert result["chain_updated"] == 3
    assert row.blob_digest == f"sha256:{_HEX_A}"
    assert row.size_bytes == 2048
    assert row.digest_state == DIGEST_READY
    manila_mod.revoke_access_rule.assert_called_once()
    delete_vm.assert_awaited_once()


async def test_backfill_marks_failed_and_still_releases_resources_on_ssh_error():
    row = _pending_row(1)
    store = {"ids": [1], "rows": {1: row}, "commits": 0}
    vm = MagicMock(
        server_id="vm-1", host="1.2.3.4", key_path="/k", username="ubuntu", internal_ip="10.0.0.9", fip_id="fip-1"
    )

    with (
        patch("app.services.palimpsest_backfill.get_session_factory", return_value=lambda: _FactorySession(store)),
        patch(
            "app.services.resource_policy_store.get_service_project_connection",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.resource_policy_store.resolve_policy_snapshot",
            new=AsyncMock(
                return_value={
                    "builder.flavor": {"id": "flavor-1", "name": "builder"},
                    "builder.network": {"id": "network-1", "name": "network"},
                }
            ),
        ),
        patch(
            "app.services.resource_policy_store.get_policy_snapshot",
            new=AsyncMock(return_value={"builder.floating_network": None}),
        ),
        patch("app.services.palimpsest_backfill.create_ephemeral_vm", AsyncMock(return_value=vm)),
        patch("app.services.palimpsest_backfill.delete_ephemeral_vm", AsyncMock()) as delete_vm,
        patch("app.services.palimpsest_backfill.manila") as manila_mod,
        patch(
            "app.services.palimpsest_backfill.ssh_executor.run_command",
            AsyncMock(return_value=(1, "", "mount: permission denied")),
        ),
        patch("app.services.palimpsest_backfill._refresh_chain_ids", AsyncMock(return_value=0)),
    ):
        manila_mod.ensure_nfs_access_rule.return_value = {"access_id": "acc-1"}
        manila_mod.get_export_locations.return_value = ["10.0.0.1:/layers/uv"]
        result = await backfill_digests(limit=10)

    assert result["failed"] == 1
    assert row.digest_state == DIGEST_FAILED
    assert "permission denied" in result["details"][0]["error"]
    # 한 건 실패해도 자원은 회수된다
    manila_mod.revoke_access_rule.assert_called_once()
    delete_vm.assert_awaited_once()


async def test_backfill_deletes_vm_even_when_hashing_raises_unexpectedly():
    row = _pending_row(1)
    store = {"ids": [1], "rows": {1: row}, "commits": 0}
    vm = MagicMock(
        server_id="vm-1", host="1.2.3.4", key_path="/k", username="ubuntu", internal_ip="10.0.0.9", fip_id="fip-1"
    )

    with (
        patch("app.services.palimpsest_backfill.get_session_factory", return_value=lambda: _FactorySession(store)),
        patch(
            "app.services.resource_policy_store.get_service_project_connection",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.resource_policy_store.resolve_policy_snapshot",
            new=AsyncMock(
                return_value={
                    "builder.flavor": {"id": "flavor-1", "name": "builder"},
                    "builder.network": {"id": "network-1", "name": "network"},
                }
            ),
        ),
        patch(
            "app.services.resource_policy_store.get_policy_snapshot",
            new=AsyncMock(return_value={"builder.floating_network": None}),
        ),
        patch("app.services.palimpsest_backfill.create_ephemeral_vm", AsyncMock(return_value=vm)),
        patch("app.services.palimpsest_backfill.delete_ephemeral_vm", AsyncMock()) as delete_vm,
        patch("app.services.palimpsest_backfill._hash_one", AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.services.palimpsest_backfill._refresh_chain_ids", AsyncMock(return_value=0)),
    ):
        with pytest.raises(RuntimeError):
            await backfill_digests(limit=10)

    delete_vm.assert_awaited_once()
