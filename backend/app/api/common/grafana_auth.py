"""Grafana 임베드 지원 엔드포인트."""

from fastapi import APIRouter, Depends

from app.api.deps import get_token_info
from app.config import get_settings

router = APIRouter()


@router.get("/dashboards")
async def get_grafana_dashboards(
    token_info: dict = Depends(get_token_info),
):
    """Grafana 대시보드 UID 매핑 + 기본 URL 반환.

    미설정 시 grafana_url은 빈 문자열, dashboards는 기본 UID 반환.
    항상 200 — 프론트엔드가 grafana_url 유무로 빈 상태 판단.
    """
    settings = get_settings()
    return {
        "grafana_url": settings.grafana_base_url,
        "dashboards": {
            "node": settings.grafana_dashboard_node_uid,
            "rabbitmq": settings.grafana_dashboard_rabbitmq_uid,
            "mysqld": settings.grafana_dashboard_mysqld_uid,
            "proxysql": settings.grafana_dashboard_proxysql_uid,
            "memcached": settings.grafana_dashboard_memcached_uid,
            "etcd": settings.grafana_dashboard_etcd_uid,
            "haproxy": settings.grafana_dashboard_haproxy_uid,
            "libvirt": settings.grafana_dashboard_libvirt_uid,
            "openstack": settings.grafana_dashboard_openstack_uid,
            "ceph": settings.grafana_dashboard_ceph_uid,
            "instance-cpu": settings.grafana_dashboard_instance_cpu_uid,
            "instance-gpu": settings.grafana_dashboard_instance_gpu_uid,
        },
    }
