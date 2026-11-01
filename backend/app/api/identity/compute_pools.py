"""Fresh system-admin ceilings and exact-domain manager project caps."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.api.deps import get_admin_os_conn, require_admin, require_domain_manager
from app.api.identity.iam import IamRoute
from app.models.compute_pools import MAX_AMOUNT, PoolUpdate, ProjectLimitsUpdate
from app.models.flavor_automation import HostUpdate, PolicyUpdate
from app.services import compute_pools, domain_iam, flavor_automation_policy, pci_device_inventory

router = APIRouter(route_class=IamRoute)
NativeId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
RevisionQuery = Annotated[int, Query(ge=0, le=MAX_AMOUNT)]


async def _result(operation):
    try:
        return await operation
    except compute_pools.ComputePoolUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except compute_pools.ComputePoolDenied as exc:
        raise HTTPException(409, {"code": "compute_pool_denied", "blockers": exc.blockers}) from exc


@router.get("/admin/domains/{domain_id}/compute-pool")
async def admin_pool(domain_id: NativeId, token_info: dict = Depends(require_admin), conn=Depends(get_admin_os_conn)):
    return await _result(compute_pools.read_pool(conn, domain_id))


@router.put("/admin/domains/{domain_id}/compute-pool")
async def put_admin_pool(
    domain_id: NativeId, req: PoolUpdate, token_info: dict = Depends(require_admin), conn=Depends(get_admin_os_conn)
):
    return await _result(
        compute_pools.update_pool(conn, domain_id, req.revision, req.enabled, req.limits, token_info=token_info)
    )


@router.put("/admin/domains/{domain_id}/compute-pool/projects/{project_id}")
async def put_admin_project_limits(
    domain_id: NativeId,
    project_id: NativeId,
    req: ProjectLimitsUpdate,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_admin_os_conn),
):
    return await _result(
        compute_pools.update_project_limits(
            conn, domain_id, project_id, req.revision, req.limits, token_info=token_info, system=True
        )
    )


@router.delete("/admin/domains/{domain_id}/compute-pool/projects/{project_id}")
async def delete_admin_project_limits(
    domain_id: NativeId,
    project_id: NativeId,
    revision: RevisionQuery,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_admin_os_conn),
):
    return await _result(
        compute_pools.delete_project_limits(conn, domain_id, project_id, revision, token_info=token_info, system=True)
    )


@router.get("/iam/compute-pool")
async def manager_pool(token_info: dict = Depends(require_domain_manager)):
    context = await domain_iam.context(token_info)
    return await _result(compute_pools.read_pool(None, context["domain_id"]))


@router.put("/iam/compute-pool/projects/{project_id}")
async def put_manager_project_limits(
    project_id: NativeId, req: ProjectLimitsUpdate, token_info: dict = Depends(require_domain_manager)
):
    return await _result(
        compute_pools.update_project_limits(
            None, token_info["domain_id"], project_id, req.revision, req.limits, token_info=token_info
        )
    )


@router.delete("/iam/compute-pool/projects/{project_id}")
async def delete_manager_project_limits(
    project_id: NativeId, revision: RevisionQuery, token_info: dict = Depends(require_domain_manager)
):
    return await _result(
        compute_pools.delete_project_limits(None, token_info["domain_id"], project_id, revision, token_info=token_info)
    )


@router.get("/admin/flavor-automation/policy")
async def automation_policy(token_info: dict = Depends(require_admin)):
    return await flavor_automation_policy.load_policy()


@router.get("/admin/flavor-automation/pci-devices")
async def automation_pci_devices(token_info: dict = Depends(require_admin), conn=Depends(get_admin_os_conn)):
    return await pci_device_inventory.discover(conn)


@router.put("/admin/flavor-automation/policy")
async def put_automation_policy(
    req: PolicyUpdate, token_info: dict = Depends(require_admin), conn=Depends(get_admin_os_conn)
):
    return await flavor_automation_policy.update_profiles(
        conn,
        revision=req.revision,
        gpu_profiles=[profile.model_dump() for profile in req.gpu_profiles],
        token_info=token_info,
    )


@router.post("/admin/flavor-automation/discover")
async def discover_automation_hosts(token_info: dict = Depends(require_admin), conn=Depends(get_admin_os_conn)):
    return await flavor_automation_policy.discover(conn, token_info=token_info)


@router.put("/admin/flavor-automation/hosts/{host_id}")
async def put_automation_host(
    host_id: NativeId,
    req: HostUpdate,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_admin_os_conn),
):
    return await flavor_automation_policy.update_host(
        conn,
        host_id,
        revision=req.revision,
        removed=req.removed,
        token_info=token_info,
    )
