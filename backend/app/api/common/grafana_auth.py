"""Grafana 임베드 지원 엔드포인트."""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.config import get_settings

router = APIRouter()


@router.get("/dashboards")
async def get_grafana_dashboards(
    token_info: dict = Depends(require_admin),
):
    """Return the administrator's external Grafana catalog.

    Dashboard variables are presentation hints, not tenant authorization. Consumer
    VM charts use the Nova-authorized instance metrics API instead of this origin.
    An unset URL still returns the configured catalog to authorized administrators.
    """
    settings = get_settings()
    return {
        "grafana_url": settings.grafana_base_url,
        "dashboards": {
            "node": settings.grafana_dashboard_node_uid,
            "node-temperatures": settings.grafana_dashboard_node_temperatures_uid,
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
