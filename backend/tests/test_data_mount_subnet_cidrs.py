"""Project subnet CIDR resolution regressions for ordinary data mounts."""

from unittest.mock import MagicMock, patch

from app.api.compute.instances import _resolve_project_subnet_cidrs


def make_subnet_detail(cidr: str):
    s = MagicMock()
    s.cidr = cidr
    return s


def make_network_detail(cidrs: list[str]):
    nd = MagicMock()
    nd.subnet_details = [make_subnet_detail(c) for c in cidrs]
    return nd


# ---------------------------------------------------------------------------
# _resolve_project_subnet_cidrs
# ---------------------------------------------------------------------------


def test_resolve_project_subnet_cidrs_returns_cidrs():
    """get_network_detail로부터 CIDR 목록을 올바르게 추출한다."""
    conn = MagicMock()
    with patch(
        "app.api.compute.instances.neutron.get_network_detail",
        return_value=make_network_detail(["10.10.0.0/24", "fd00::/64"]),
    ):
        result = _resolve_project_subnet_cidrs(conn, "net-abc")
    assert result == ["10.10.0.0/24", "fd00::/64"]


def test_resolve_project_subnet_cidrs_skips_empty():
    """cidr 필드가 비어 있는 subnet은 제외한다."""
    conn = MagicMock()
    nd = MagicMock()
    s1, s2 = MagicMock(), MagicMock()
    s1.cidr = "10.10.0.0/24"
    s2.cidr = ""
    nd.subnet_details = [s1, s2]
    with patch("app.api.compute.instances.neutron.get_network_detail", return_value=nd):
        result = _resolve_project_subnet_cidrs(conn, "net-abc")
    assert result == ["10.10.0.0/24"]
