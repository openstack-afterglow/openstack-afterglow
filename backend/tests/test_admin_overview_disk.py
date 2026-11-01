"""admin._fetch_overview_disk — 클러스터-와이드 블록 스토리지 보정 단위 테스트."""

from unittest.mock import MagicMock


def _make_conn(pool_resp: dict, volumes: list, image_bytes: int) -> MagicMock:
    conn = MagicMock()
    conn.block_storage.get_endpoint.return_value = "http://cinder:8776/v3/proj"

    session_resp = MagicMock()
    session_resp.json.return_value = pool_resp
    conn.session.get.return_value = session_resp

    vol_mocks = []
    for size in volumes:
        v = MagicMock()
        v.size = size
        vol_mocks.append(v)
    conn.block_storage.volumes.return_value = vol_mocks

    img_mock = MagicMock()
    img_mock.status = "active"
    img_mock.size = image_bytes
    conn.image.images.return_value = [img_mock]

    return conn


def test_total_disk_is_pool_sum():
    """total_disk 가 Cinder 풀의 total_capacity_gb 합 이어야 한다."""
    from app.api.identity.admin import _fetch_overview_disk

    conn = _make_conn(
        pool_resp={
            "pools": [
                {
                    "name": "pool1",
                    "capabilities": {
                        "total_capacity_gb": 500.0,
                        "free_capacity_gb": 100.0,
                        "allocated_capacity_gb": 400.0,
                    },
                },
                {
                    "name": "pool2",
                    "capabilities": {
                        "total_capacity_gb": 300.0,
                        "free_capacity_gb": 50.0,
                        "allocated_capacity_gb": 250.0,
                    },
                },
            ]
        },
        volumes=[10, 20],
        image_bytes=0,
    )
    result = _fetch_overview_disk(conn)
    assert result["total_disk"] == 800.0, f"풀 합이 800이어야 함, got {result['total_disk']}"


def test_used_disk_includes_volumes_and_images():
    """used_disk = 볼륨 합(GB) + 이미지 합(bytes → GB)."""
    from app.api.identity.admin import _fetch_overview_disk

    # 이미지 1 GB = 1073741824 bytes
    image_bytes = 1073741824
    conn = _make_conn(
        pool_resp={
            "pools": [
                {
                    "name": "p",
                    "capabilities": {
                        "total_capacity_gb": 1000.0,
                        "free_capacity_gb": 500.0,
                        "allocated_capacity_gb": 500.0,
                    },
                }
            ]
        },
        volumes=[10, 5],  # 15 GB
        image_bytes=image_bytes,
    )
    result = _fetch_overview_disk(conn)
    # 15 GB (볼륨) + 1 GB (이미지) = 16 GB
    assert result["used_disk"] == pytest.approx(16.0, abs=0.01), f"used_disk 16이어야 함, got {result['used_disk']}"


def test_infinite_pool_not_counted():
    """Unknown/infinite pool capacity must not become a trustworthy numeric total."""
    from app.api.identity.admin import _fetch_overview_disk

    conn = _make_conn(
        pool_resp={
            "pools": [
                {
                    "name": "inf-pool",
                    "capabilities": {
                        "total_capacity_gb": "infinite",
                        "free_capacity_gb": "infinite",
                        "allocated_capacity_gb": 0,
                    },
                },
                {
                    "name": "real-pool",
                    "capabilities": {
                        "total_capacity_gb": 200.0,
                        "free_capacity_gb": 50.0,
                        "allocated_capacity_gb": 150.0,
                    },
                },
            ]
        },
        volumes=[],
        image_bytes=0,
    )
    result = _fetch_overview_disk(conn)
    assert result["total_disk"] is None
    assert result["used_disk"] == 0


def test_no_pools_returns_zero_total():
    """풀이 없으면 total_disk=0."""
    from app.api.identity.admin import _fetch_overview_disk

    conn = _make_conn(pool_resp={"pools": []}, volumes=[], image_bytes=0)
    result = _fetch_overview_disk(conn)
    assert result["total_disk"] == 0.0
    assert result["used_disk"] == 0.0


import pytest
