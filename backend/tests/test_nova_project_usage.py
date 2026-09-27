"""Nova simple-tenant-usage adapter shape."""

from datetime import datetime
from unittest.mock import MagicMock

from openstack.compute.v2.usage import ServerUsage, Usage

from app.services import nova


def test_get_project_usage_preserves_server_flavor_and_timestamps():
    conn = MagicMock()
    conn.compute.get_usage.return_value = Usage(
        total_hours=240.0,
        total_vcpus_usage=480.0,
        total_memory_mb_usage=983040.0,
        total_local_gb_usage=4800.0,
        server_usages=[
            ServerUsage(
                name="web-01",
                instance_id="s1",
                flavor="c2.medium",
                vcpus=2,
                memory_mb=4096,
                local_gb=20,
                hours=120.0,
                state="active",
                started_at="2026-08-01T10:00:00.000000",
                ended_at=None,
                uptime=3600,
            )
        ],
    )

    usage = nova.get_project_usage(conn, "project-1", "2026-08-01", "2026-08-31")

    assert usage["total_vcpus_usage"] == 480.0
    server = usage["server_usages"][0]
    assert server["flavor"] == "c2.medium"
    assert server["started_at"] == "2026-08-01T10:00:00+00:00"
    assert server["ended_at"] is None
    assert server["uptime"] == 3600
    conn.compute.get_usage.assert_called_once_with(
        "project-1",
        start=datetime(2026, 8, 1),
        end=datetime(2026, 8, 31),
    )


def test_get_project_usage_returns_zero_fallback_when_nova_fails():
    conn = MagicMock()
    conn.compute.get_usage.side_effect = RuntimeError("nova unavailable")

    assert nova.get_project_usage(conn, "project-1", "2026-08-01", "2026-08-31") == {
        "total_vcpus_usage": 0.0,
        "total_memory_mb_usage": 0.0,
        "total_local_gb_usage": 0.0,
        "total_hours": 0.0,
        "server_usages": [],
    }
