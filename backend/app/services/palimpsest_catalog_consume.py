"""One-shot caller-credential consumption using the existing durable work journal.

Credentials remain only in the admitted API task, never SQL/Redis. A process
loss is deliberately not requeued under a service identity. Durable intent and
tracking survive; reads never dispatch/replay a provider create.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from app.models.db import LayerConsume
from app.services import palimpsest_catalog as catalog

_logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()
_ASSIGNMENT_REFRESH_SECONDS = 15


async def _keep_assignment(dispatcher, member):
    while True:
        if not await dispatcher.publish([member]):
            raise RuntimeError("Catalog consume assignment could not be renewed")
        await asyncio.sleep(_ASSIGNMENT_REFRESH_SECONDS)


def _task_finished(task):
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        _logger.error(
            "Catalog consume task failed while preserving durable tracking (%s)", type(task.exception()).__name__
        )


async def current_writer(info):
    from app.api.deps import require_project_write
    from app.services import keystone
    from app.services.project_service import get_project_access

    project = info["project_id"]
    if info.get("connection_project_id", project) != project:
        raise HTTPException(403, "Consume requires the original credential in the current project")
    native = await asyncio.to_thread(keystone.validate_token, info["token"], project_id=project)
    if native.get("user_id") != info["user_id"] or native.get("project_id") != project:
        raise HTTPException(403, "Native caller scope differs from the current project")
    access = await get_project_access(project, info["user_id"])
    if not access["roles"]:
        raise HTTPException(403, "Current project membership is required")
    require_project_write({**info, "roles": access["roles"], "is_system_admin": False})


async def require_action(info, action):
    from app.services.service_proxy import get_policy_capabilities

    decisions = await get_policy_capabilities("palimpsest", info)
    if action not in decisions["actions"]:
        raise HTTPException(403, "Palimpsest action permission is required")


async def admit(request, info, profile_id, spec):
    from app.api.deps import get_os_conn
    from app.services import keystone, layer_build, nova
    from app.services.cache import _get_redis
    from app.services.flavor_eligibility import admit_flavor, release_admission
    from app.services.resource_policy_store import get_policy_snapshot
    from app.services.work_dispatcher import WorkDispatcher, close_connection, open_connection

    await current_writer(info)
    await require_action(info, "packages:read")
    # Own the generator explicitly: FastAPI must not close the caller connection
    # when the short acceptance response ends while the supervised task runs.
    scope = get_os_conn(request, info)
    conn = await anext(scope)
    share_conn = None
    dispatcher = None
    admission = None
    transferred = False
    consume_id = None
    try:
        async with catalog.factory()() as session:
            snapshot = await catalog.published_snapshot(session, profile_id)
            if snapshot["revision"] != spec.revision:
                raise HTTPException(409, "Environment revision changed; refresh before launching")
            if not snapshot["cloud_supported"]:
                raise HTTPException(409, snapshot["cloud_reason"])
        network = await asyncio.to_thread(conn.network.get_network, spec.network_id)
        if (
            network is None
            or str(network.id) != spec.network_id
            or not (getattr(network, "project_id", None) == info["project_id"] or getattr(network, "is_shared", False))
        ):
            raise HTTPException(403, "Network is not owned by or shared with the current project")
        flavors = await asyncio.to_thread(nova.list_flavors, conn)
        flavor = next((row for row in flavors if row.id == spec.flavor_id), None)
        if flavor is None:
            raise HTTPException(422, "Flavor is unavailable in the current project")
        await layer_build.validate_consume_image_identity(conn, snapshot["artifacts"])
        public_key = spec.ssh_public_key
        if spec.key_name and not public_key:
            key = await asyncio.to_thread(conn.compute.get_keypair, spec.key_name)
            public_key = getattr(key, "public_key", None)
            if not public_key:
                raise HTTPException(422, "Selected caller keypair has no accessible public key")
            from app.utils.ssh_keys import validate_ssh_public_key

            validate_ssh_public_key(public_key)
        service_project = (await get_policy_snapshot(("openstack.service_project",)))["openstack.service_project"]
        if not service_project or not service_project.get("id"):
            raise HTTPException(503, "Layer service project authority is unavailable")
        share_conn = await open_connection(keystone.get_admin_connection_for_project, service_project["id"])
        admission = await admit_flavor(conn, info["project_id"], flavor)
        resources = {
            "network": {"id": spec.network_id, "name": str(network.name or spec.network_id)},
            "flavor": {"id": spec.flavor_id, "name": str(flavor.name)},
            "openstack.service_project": service_project,
            "consumer_project": {"id": info["project_id"]},
            "catalog_revision": spec.revision,
            "catalog_profile_id": profile_id,
            "catalog_artifact_sources": [
                {"id": entry["id"], "share_id": entry["share_id"], "blob_digest": entry["blob_digest"]}
                for entry in snapshot["artifacts"]
            ],
        }
        async with catalog.factory()() as session:
            locked = await catalog.published_snapshot(session, profile_id, lock=True)
            if locked["revision"] != spec.revision:
                raise HTTPException(409, "Environment revision changed during admission")
            row = LayerConsume(
                profile_name=locked["profile"].name,
                project_id=info["project_id"],
                artifact_ids=[x["id"] for x in locked["artifacts"]],
                share_id="",
                transport="nfs",
                server_name=spec.server_name,
                status="creating",
                resource_snapshot=resources,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            consume_id = row.id
            result = catalog.consume_dto(row)
        # A unique admission owns a single dispatcher namespace; no pool can pick
        # this work up without the in-memory original caller credential.
        dispatcher = WorkDispatcher(await _get_redis(), f"afterglow:catalog-consume:{consume_id}")
        await dispatcher.__aenter__()
        member = f"consume:{consume_id}"
        if not await dispatcher.publish([member]):
            raise HTTPException(503, "Consume dispatcher could not admit work")
        claim = await dispatcher.claim(90)
        if claim is None or claim[0] != member:
            raise HTTPException(503, "Consume dispatcher did not claim this admission")
        task = asyncio.create_task(
            _execute(
                dispatcher,
                claim,
                scope,
                conn,
                share_conn,
                admission,
                info.copy(),
                profile_id,
                spec,
                locked["artifacts"],
                resources,
                public_key,
            ),
            name=f"catalog-consume:{consume_id}",
        )
        _tasks.add(task)
        task.add_done_callback(_task_finished)
        transferred = True
        return result
    except HTTPException:
        raise
    except Exception as exc:
        from app.services.flavor_eligibility import FlavorEligibilityDenied, FlavorEligibilityUnavailable
        from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

        if isinstance(exc, (FlavorEligibilityDenied, GpuQuotaDenied)):
            raise HTTPException(409, "Current project quota or flavor capacity does not permit this VM") from exc
        if isinstance(exc, (FlavorEligibilityUnavailable, GpuQuotaUnavailable)):
            raise HTTPException(503, "Current project quota or capacity authority is unavailable") from exc
        raise HTTPException(503, "Environment consume admission is unavailable") from exc
    finally:
        if not transferred:
            try:
                if consume_id is not None:
                    await _failed(consume_id, "error")
            finally:
                try:
                    if dispatcher is not None:
                        await dispatcher.__aexit__(None, None, None)
                finally:
                    try:
                        if admission is not None:
                            await release_admission(admission)
                    finally:
                        try:
                            if share_conn is not None:
                                await close_connection(share_conn)
                        finally:
                            await scope.aclose()


async def _failed(consume_id, status):
    async with catalog.factory()() as session:
        row = await session.get(LayerConsume, consume_id, with_for_update=True)
        if row is not None and row.status == "creating":
            row.status = status
            row.completed_at = datetime.now(UTC)
            # Provider exception strings can contain credentials/internal paths.
            row.error_message = "Environment provisioning did not complete; inspect durable allocation before retrying"
            await session.commit()


async def _execute(
    dispatcher, claim, scope, conn, share_conn, admission, info, profile_id, spec, artifacts, resources, public_key
):
    from app.services import build_work, layer_build
    from app.services.flavor_eligibility import release_admission
    from app.services.work_dispatcher import close_connection, work_lease

    consume_id = int(claim[0].split(":", 1)[1])
    assignment = asyncio.create_task(_keep_assignment(dispatcher, claim[0]))
    try:
        async with work_lease(dispatcher, *claim) as lease, build_work.bind(dispatcher.redis, claim[0], lease):
            await current_writer(info)
            await require_action(info, "packages:read")
            async with catalog.factory()() as session:
                snapshot = await catalog.published_snapshot(session, profile_id, lock=True)
                if snapshot["revision"] != spec.revision or not snapshot["cloud_supported"]:
                    raise HTTPException(409, "Environment changed before allocation")
            await layer_build._await_consume_stage(
                layer_build.run_layer_consume(
                    consume_db_id=consume_id,
                    profile_name=snapshot["profile"].name,
                    server_name=spec.server_name,
                    flavor_id=spec.flavor_id,
                    network_id=spec.network_id,
                    ssh_public_key=public_key,
                    ssh_username=spec.ssh_username,
                    resource_snapshot=resources,
                    compute_conn=conn,
                    share_conn=share_conn,
                    artifact_ids=[x["id"] for x in artifacts],
                    resolved_artifacts=artifacts,
                    transport="nfs",
                ),
                assignment,
            )
    except (Exception, asyncio.CancelledError) as exc:
        # An accepted/uncertain journal intent must never be treated as safe to retry.
        prefix = f"afterglow:builds:journal:{claim[0]}:submit:consumer:{consume_id}:"
        try:
            submitted = any([await dispatcher.redis.get(prefix + step) for step in ("port", "upper", "server")])
        except Exception:
            submitted = True  # Missing journal authority is not evidence of rejection.
        _logger.warning("Catalog consume %s stopped (%s)", consume_id, type(exc).__name__)
        await _failed(consume_id, "indeterminate" if submitted else "error")
    finally:
        assignment.cancel()
        await asyncio.gather(assignment, return_exceptions=True)
        try:
            await release_admission(admission)
        finally:
            try:
                await close_connection(share_conn)
            finally:
                try:
                    await scope.aclose()
                finally:
                    await dispatcher.__aexit__(None, None, None)
