from __future__ import annotations

import pytest

from app.services.mcp_control_plane import dashboard


@pytest.mark.asyncio
async def test_project_quotas_uses_only_the_exact_project_and_fixed_safe_fields(monkeypatch):
    calls: list[tuple[str, object]] = []

    def compute(conn, project_id, *, strict):
        calls.append(("compute", project_id))
        assert strict is True
        return {
            "instances": {"limit": 10, "in_use": 2},
            "cores": {"limit": 20, "in_use": 4},
            "ram": {"limit": 1024, "in_use": 256},
            "unexposed": {"limit": 1, "in_use": 0},
        }

    def storage(conn, project_id, *, strict):
        calls.append(("storage", project_id))
        assert strict is True
        return {
            "volumes": {"limit": 5, "in_use": 1},
            "gigabytes": {"limit": 100, "in_use": 25},
            "backups": {"limit": 99, "in_use": 1},
        }

    def network(conn, project_id, *, strict):
        calls.append(("network", project_id))
        assert strict is True
        return {"floatingip": {"limit": 3, "used": 1}, "security_group": {"limit": 99, "used": 1}}

    monkeypatch.setattr(dashboard.nova, "get_project_quota", compute)
    monkeypatch.setattr(dashboard.cinder, "get_volume_quota", storage)
    monkeypatch.setattr(dashboard.neutron_service, "get_network_quota", network)

    result = await dashboard.project_quotas(object(), project_id="project-a", manila_enabled=False)

    # 세 source 는 asyncio.to_thread 로 동시에 실행되므로 호출 순서는 보장되지 않는다.
    # 각 source 가 정확한 project 로 한 번씩만 호출됐는지만 확인한다.
    assert sorted(calls) == [("compute", "project-a"), ("network", "project-a"), ("storage", "project-a")]
    assert result == {
        "compute": {
            "instances": {"limit": 10, "in_use": 2},
            "cores": {"limit": 20, "in_use": 4},
            "ram": {"limit": 1024, "in_use": 256},
        },
        "storage": {
            "volumes": {"limit": 5, "in_use": 1},
            "gigabytes": {"limit": 100, "in_use": 25},
        },
        "network": {"floatingip": {"limit": 3, "in_use": 1}},
        "file_storage": None,
    }


@pytest.mark.asyncio
async def test_project_quotas_fail_closed_when_a_required_source_is_malformed(monkeypatch):
    monkeypatch.setattr(dashboard.nova, "get_project_quota", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        dashboard.cinder,
        "get_volume_quota",
        lambda *_args, **_kwargs: {"volumes": {"limit": 1, "in_use": 0}, "gigabytes": {"limit": 1, "in_use": 0}},
    )
    monkeypatch.setattr(
        dashboard.neutron_service,
        "get_network_quota",
        lambda *_args, **_kwargs: {"floatingip": {"limit": 1, "used": 0}},
    )

    with pytest.raises(dashboard.McpDashboardError, match="missing"):
        await dashboard.project_quotas(object(), project_id="project-a", manila_enabled=False)
