"""
라이브러리 파일 스토리지 자동 빌드 서비스.

Manila share 생성 → Ephemeral Builder VM cloud-init으로 패키지 설치 → DB 결과 반영
"""

from __future__ import annotations

import asyncio
import logging

from app.services import libraries as lib_svc

_logger = logging.getLogger(__name__)

_TERMINAL = {"complete", "error", "timeout", "cancelled"}
_DISPATCH_PREFIX = "afterglow:builds"


async def cancel_build(build_db_id: int) -> dict:
    """진행 중인 빌드를 취소한다.

    SQL row는 즉시 ``cancelled``가 되어 실행 owner의 다음 mutation을 막는다.
    ``completed_at``은 비워 두고 ``resource_snapshot.cancel_cleanup=pending``을 남겨
    배정된 build owner가 SQL·CREATE journal의 정확한 server/port/RW rule을 관측·정리한
    뒤 닫는다. 요청 처리 중에는 provider 리소스를 변경하지 않는다.

    Returns:
        { "cancelled": True, "library_id": str }
    """
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LibraryBuild

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DB가 초기화되지 않았습니다")

    async with factory() as session:
        row = (
            await session.execute(select(LibraryBuild).where(LibraryBuild.id == build_db_id).with_for_update())
        ).scalar_one_or_none()
        if row is None:
            raise KeyError(f"빌드 {build_db_id}를 찾을 수 없습니다")
        if row.status in _TERMINAL:
            raise ValueError(f"이미 종료된 빌드입니다 (상태: {row.status})")

        library_id = row.library_id
        row.status = "cancelled"
        if row.build_token:
            row.cloud_init_status = "failure"
        row.progress_step = "사용자 취소"
        row.error_message = "관리자에 의해 취소됨"
        row.resource_snapshot = {**(row.resource_snapshot or {}), "cancel_cleanup": "pending"}
        await session.commit()
    return {"cancelled": True, "library_id": library_id}


# ---------------------------------------------------------------------------
# 빌드 큐
# ---------------------------------------------------------------------------


async def queue_build(library_id: str, existing_share_id: str | None = None) -> dict:
    """Commit a frozen build request; only an assigned worker can execute it."""
    import copy
    import uuid

    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LibraryBuild, LibraryRecipe
    from app.services import library_recipes
    from app.services.resource_policy_store import (
        get_policy_snapshot,
        get_service_project_connection,
        lock_service_project_admission,
        resolve_policy_snapshot,
    )
    from app.services.work_dispatcher import close_connection

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DB가 초기화되지 않았습니다")
    lib = lib_svc.get_by_id(library_id)
    recipe = await library_recipes.get_recipe(library_id)
    if recipe is None or not recipe.base_image_id:
        raise ValueError("library builds require an explicit recipe base image")
    proto = (recipe.share_proto or "NFS").upper()
    keys = ["builder.flavor", "builder.network"]
    keys.append("manila.nfs_share_type" if proto == "NFS" else "manila.cephfs_share_type")
    if proto == "NFS":
        keys.append("manila.share_network")
    service_project = (await get_policy_snapshot(("openstack.service_project",)))["openstack.service_project"]
    if service_project is None:
        raise ValueError("service project policy is not configured")
    # Resolve every service-owned resource against this exact project; the
    # admission transaction below rejects a concurrent project change.
    service_conn = await get_service_project_connection(service_project["id"])
    from app.services.work_dispatcher import run_sync

    try:
        policies = await resolve_policy_snapshot(conn=service_conn, keys=tuple(keys), service_conn=service_conn)
        image = await run_sync(service_conn.image.get_image, recipe.base_image_id)
        if image is None:
            raise ValueError(f"library recipe base image was not found: {recipe.base_image_id}")
    finally:
        await close_connection(service_conn)
    snapshot = {
        "openstack.service_project": service_project,
        "base_image": {"id": recipe.base_image_id, "name": getattr(image, "name", recipe.base_image_id)},
        **policies,
        "manila": {
            "share_proto": proto,
            "share_type": policies["manila.nfs_share_type" if proto == "NFS" else "manila.cephfs_share_type"]["name"],
            "share_network_id": policies["manila.share_network"]["id"] if proto == "NFS" else "",
            "share_size_gb": recipe.share_size_gb,
        },
        "library_version": lib.version,
        "recipe": {
            key: copy.deepcopy(getattr(recipe, key, None))
            for key in (
                "id",
                "library_id",
                "version",
                "commands",
                "apt_packages",
                "pip_packages",
                "base_image_id",
                "share_size_gb",
                "share_proto",
                "cloud_init_template_version",
            )
        },
    }
    async with factory() as session:
        await lock_service_project_admission(session, service_project["id"])
        # The oldest recipe is a stable SQL serialization row even as later
        # recipe versions are added. No process cache or Redis admission lock.
        anchor = (
            await session.execute(
                select(LibraryRecipe)
                .where(LibraryRecipe.library_id == recipe.library_id)
                .order_by(LibraryRecipe.id)
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if anchor is None:
            raise RuntimeError("library builds require a persisted recipe")
        current = (
            (
                await session.execute(
                    select(LibraryBuild)
                    .where(
                        LibraryBuild.library_id == library_id,
                        LibraryBuild.status.notin_(_TERMINAL),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )
        if current is not None:
            raise RuntimeError(f"이미 빌드 중인 라이브러리: {library_id}")
        row = LibraryBuild(
            library_id=library_id,
            recipe_id=recipe.id,
            file_storage_id=existing_share_id or "",
            build_token=uuid.uuid4().hex,
            resource_snapshot=snapshot,
            status="queued",
            cloud_init_status="queued",
            progress_step="빌드 대기",
            progress_pct=0,
        )
        session.add(row)
        await session.flush()
        queued = (await session.execute(select(LibraryBuild.id).where(LibraryBuild.status == "queued"))).scalars().all()
        position = len(queued)
        await session.commit()
    return {"status": "queued", "library_id": library_id, "queue_position": position}


async def get_build_queue_status() -> dict:
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LibraryBuild

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        rows = (
            (await session.execute(select(LibraryBuild).where(LibraryBuild.status.notin_(_TERMINAL)))).scalars().all()
        )
    queued = sorted(row.library_id for row in rows if row.status == "queued")
    return {
        "queued": queued,
        "active": sorted(row.library_id for row in rows if row.status != "queued"),
        "queue_size": len(queued),
    }


async def _discover_work(dispatcher) -> None:
    """Leader-only SQL discovery is a hint, never an orphan cleanup decision."""
    if not await dispatcher.is_leader():
        return
    from sqlalchemy import and_, or_, select

    from app.database import get_session_factory
    from app.models.db import LayerBuild, LayerImportJob, LibraryBuild
    from app.services.work_dispatcher import DispatcherUnavailable

    factory = get_session_factory()
    if factory is None:
        raise DispatcherUnavailable("build database is unavailable")
    async with factory() as session:
        # Cancelled rows with completed_at unset still owe cancellation cleanup: an
        # assigned owner observes journaled identities, removes them, then seals.
        libraries = (
            (
                await session.execute(
                    select(LibraryBuild.id).where(
                        or_(
                            LibraryBuild.status.notin_(_TERMINAL),
                            and_(LibraryBuild.status == "cancelled", LibraryBuild.completed_at.is_(None)),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        imports = (
            (await session.execute(select(LayerImportJob.id).where(LayerImportJob.status.notin_(_TERMINAL))))
            .scalars()
            .all()
        )
        # Import-owned child rows are executed by their import target, never
        # independently alongside that target's VM/output orchestration.
        layers = (
            (
                await session.execute(
                    select(LayerBuild.id).where(
                        or_(
                            LayerBuild.status.notin_(_TERMINAL),
                            # Cancelled before an in-flight CREATE settled (same contract as libraries).
                            and_(LayerBuild.status == "cancelled", LayerBuild.completed_at.is_(None)),
                        ),
                        LayerBuild.kind.notin_(("dockerfile", "dockerfile-root")),
                    )
                )
            )
            .scalars()
            .all()
        )
    await dispatcher.publish(
        [
            *(f"library:{identity}" for identity in libraries),
            *(f"import:{identity}" for identity in imports),
            *(f"layer:{identity}" for identity in layers),
        ]
    )


async def _execute_work(dispatcher, member: str, owner: str) -> None:
    from app.services import build_work
    from app.services.work_dispatcher import work_lease

    kind, identity = member.split(":", 1)
    async with work_lease(dispatcher, member, owner) as lease:
        cancel_cleanup = False
        if kind in ("layer", "library"):
            from app.database import get_session_factory
            from app.models.db import LayerBuild, LibraryBuild

            async with get_session_factory()() as session:
                row = await session.get(LayerBuild if kind == "layer" else LibraryBuild, int(identity))
                cancel_cleanup = (
                    row is not None
                    and row.status == "cancelled"
                    and (row.resource_snapshot or {}).get("cancel_cleanup") == "pending"
                )
        async with build_work.bind(dispatcher.redis, member, lease, cancel_cleanup=cancel_cleanup):
            if kind == "library":
                from app.services.ephemeral_build import run_ephemeral_build

                await run_ephemeral_build(int(identity))
            elif kind == "import":
                from app.services.dockerfile_import import run_dockerfile_import_job

                await run_dockerfile_import_job(int(identity))
            elif kind == "layer":
                from app.services.layer_builder import execute_layer_build

                await execute_layer_build(int(identity))
            else:
                raise ValueError(f"unknown build target: {member}")


async def _worker_session(dispatcher, poll_seconds: float) -> None:
    from app.services.work_dispatcher import DispatcherUnavailable

    # References only supervise/drain tasks; they never grant execution authority.
    tasks: dict[str, asyncio.Task] = {}
    retired: dict[asyncio.Task, str] = {}
    try:
        while True:
            if dispatcher.lost:
                raise DispatcherUnavailable("build dispatcher lost membership")
            for task, member in list(retired.items()):
                if task.done():
                    retired.pop(task)
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        _logger.warning("retired build target stopped: %s", member, exc_info=True)
            for member, task in list(tasks.items()):
                if task.done():
                    tasks.pop(member)
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        _logger.warning("build target stopped: %s", member, exc_info=True)
                elif not await dispatcher.is_assigned(member):
                    task.cancel()
            await _discover_work(dispatcher)
            while claimed := await dispatcher.claim(90):
                member, owner = claimed
                previous = tasks.get(member)
                if previous is not None:
                    # Keep the real SDK/connection drain referenced, without
                    # stalling leader discovery while the stale task drains.
                    previous.cancel()
                    retired[previous] = member
                tasks[member] = asyncio.create_task(_execute_work(dispatcher, member, owner))
            await asyncio.sleep(poll_seconds)
    finally:
        remaining = [*tasks.values(), *retired]
        for task in remaining:
            task.cancel()
        # Do not leave membership/release leases until all SDK calls drain.
        from app.services.build_work import drain

        await drain(asyncio.gather(*remaining, return_exceptions=True))


async def build_worker_loop(*, redis=None, worker_id: str | None = None, poll_seconds: float = 5) -> None:
    """Supervised target dispatcher for durable library and Dockerfile work."""
    from app.services.cache import _get_redis
    from app.services.work_dispatcher import WorkDispatcher

    while True:
        try:
            client = redis if redis is not None else await _get_redis()
            async with WorkDispatcher(client, _DISPATCH_PREFIX, worker_id=worker_id) as dispatcher:
                await _worker_session(dispatcher, poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("build dispatcher unavailable; rejoining", exc_info=True)
            await asyncio.sleep(poll_seconds)
