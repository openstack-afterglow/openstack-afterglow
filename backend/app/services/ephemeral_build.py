"""ephemeral VM cloud-init 라이브러리 빌드 오케스트레이터.

빌드 요청 → Manila share → Neutron port(IP 예약) → Access rule →
cloud-init user_data 렌더 → Nova server(port attach) →
SHUTOFF 폴링 → console_output sentinel grep → 성공/실패/indeterminate 처리

Execution is one durable ``library:<build id>`` target. The SQL row (admitted
recipe/version snapshot and build token) is the authority; the build_work journal
records every non-idempotent CREATE before it is sent. Any owner — first or a later
one after handoff — runs the same create-or-recover steps, so an accepted resource is
observed with GET and an unknown submission is looked up by its deterministic
identity, never issued again.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
from openstack.exceptions import ResourceNotFound
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.services import build_work, keystone, manila, neutron, nova
from app.services.cloud_init_builder import render_user_data
from app.services.work_dispatcher import DispatcherUnavailable, open_connection

_logger = logging.getLogger(__name__)

_SHUTOFF_POLL_INTERVAL = 15  # 폴링 간격 (초)
_SHUTOFF_MAX_WAIT = 3600  # VM 생성 시각 기준 최대 60분 (NFS 병렬 복사 ~7분 + 여유)
_SHARE_READY_WAIT = 300  # 인계받은 share가 available이 될 때까지의 최대 대기
_SUCCESS_SENTINEL = "::AFTERGLOW::SUCCESS::"
_FAILURE_SENTINEL = "::AFTERGLOW::FAILURE::"
_EXCERPT_CHARS = 2000
_DENY_STATES = frozenset({"queued_to_deny", "denying"})
_REVOKE_POLLS = 15
_REVOKE_POLL_INTERVAL = 2

# Ownership or authority is unavailable: hand off without failing the build.
_FENCE_ERRORS = (DispatcherUnavailable, SQLAlchemyError, RedisError)
# Rows another actor ended while this owner may still hold the execution lease.
_ABANDONED = frozenset({"cancelled", "error", "timeout"})
_UPDATABLE = frozenset(
    {
        "status",
        "cloud_init_status",
        "progress_step",
        "progress_pct",
        "server_id",
        "port_id",
        "file_storage_id",
        "error_message",
        "console_log_excerpt",
    }
)
_TERMINAL_FIELDS = {
    "success": {
        "status": "complete",
        "cloud_init_status": "success",
        "progress_step": "빌드 완료",
        "progress_pct": 100,
    },
    "failure": {"status": "error", "cloud_init_status": "failure", "progress_step": "빌드 실패"},
    "indeterminate": {"status": "error", "cloud_init_status": "indeterminate", "progress_step": "sentinel 부재"},
}
_INDETERMINATE_MESSAGE = "console_output에서 sentinel을 찾을 수 없습니다. VM panic 또는 console buffer 초과 가능성."


# ---------------------------------------------------------------------------
# SQL authority
# ---------------------------------------------------------------------------


async def _update_db(build_id: int, *, completed: bool = False, **fields) -> None:
    """Write only while this owner is current and the row is still runnable.

    The conditional UPDATE never overwrites a row that was cancelled or ended
    concurrently; that, a missing database, or a lost lease raises
    DispatcherUnavailable so the caller stops instead of continuing blind.
    """
    unknown = fields.keys() - _UPDATABLE
    if unknown:
        raise ValueError(f"unsupported library build fields: {sorted(unknown)}")
    from sqlalchemy import update

    from app.database import get_session_factory
    from app.models.db import LibraryBuild

    values = {key: value for key, value in fields.items() if value is not None}
    if completed:
        values["completed_at"] = datetime.now(UTC)
    await build_work.checkpoint()
    factory = get_session_factory()
    if factory is None:
        raise DispatcherUnavailable("build database is unavailable")
    async with factory() as session:
        result = await session.execute(
            update(LibraryBuild)
            .where(LibraryBuild.id == build_id, LibraryBuild.status.notin_(build_work.TERMINAL))
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    if result.rowcount != 1:
        raise DispatcherUnavailable("build is no longer runnable")


async def _load_build(build_id: int):
    from app.database import get_session_factory
    from app.models.db import LibraryBuild

    await build_work.checkpoint()
    factory = get_session_factory()
    if factory is None:
        raise DispatcherUnavailable("build database is unavailable")
    async with factory() as session:
        row = await session.get(LibraryBuild, build_id)
    if row is None or row.status in build_work.TERMINAL:
        raise DispatcherUnavailable("build is no longer runnable")
    return row


async def _row_status(build_id: int) -> str | None:
    from app.database import get_session_factory
    from app.models.db import LibraryBuild

    factory = get_session_factory()
    if factory is None:
        raise DispatcherUnavailable("build database is unavailable")
    async with factory() as session:
        row = await session.get(LibraryBuild, build_id)
    return None if row is None else row.status


# ---------------------------------------------------------------------------
# Admitted plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Plan:
    build_id: int
    library_id: str
    library_version: str
    recipe: SimpleNamespace
    build_token: str
    service_project_id: str
    image_id: str
    flavor_id: str
    network_id: str
    share_proto: str
    share_type: str
    share_network_id: str
    share_size_gb: int
    admitted_share_id: str
    recorded_port_id: str | None
    recorded_server_id: str | None

    @property
    def tag(self) -> str:
        return self.build_token[:8]

    @property
    def share_name(self) -> str:
        return f"union-prebuilt-{self.library_id}-{self.tag}"

    @property
    def port_name(self) -> str:
        return f"afterglow-build-{self.tag}"

    @property
    def vm_name(self) -> str:
        return f"afterglow-build-{self.library_id}-{self.tag}"

    @property
    def cephx_user(self) -> str:
        return f"union-builder-{self.library_id}-{self.tag}"

    @property
    def marker(self) -> str:
        """Provider-visible identity used to observe an unknown submission."""
        return f"afterglow-library-build-{self.build_id}"


def _plan(row) -> _Plan:
    snapshot = row.resource_snapshot or {}
    recipe = snapshot.get("recipe")
    service_project = snapshot.get("openstack.service_project") or {}
    base_image = snapshot.get("base_image") or {}
    builder_flavor = snapshot.get("builder.flavor") or {}
    builder_network = snapshot.get("builder.network") or {}
    manila_snapshot = snapshot.get("manila") or {}
    if not isinstance(recipe, dict) or not all(
        (
            snapshot.get("library_version"),
            service_project.get("id"),
            base_image.get("id"),
            builder_flavor.get("id"),
            builder_network.get("id"),
            manila_snapshot.get("share_proto"),
            manila_snapshot.get("share_type"),
            manila_snapshot.get("share_size_gb"),
        )
    ):
        raise ValueError("library build resource snapshot is incomplete")
    if not row.build_token:
        raise ValueError("library build was admitted without a build token")
    proto = str(manila_snapshot["share_proto"]).upper()
    if proto not in {"NFS", "CEPHFS"}:
        raise ValueError(f"unsupported builder share protocol: {proto!r}")
    return _Plan(
        build_id=row.id,
        library_id=row.library_id,
        library_version=str(snapshot["library_version"]),
        recipe=SimpleNamespace(**recipe),
        build_token=row.build_token,
        service_project_id=service_project["id"],
        image_id=base_image["id"],
        flavor_id=builder_flavor["id"],
        network_id=builder_network["id"],
        share_proto=proto,
        share_type=manila_snapshot["share_type"],
        share_network_id=manila_snapshot.get("share_network_id") or "",
        share_size_gb=int(manila_snapshot["share_size_gb"]),
        admitted_share_id=row.file_storage_id or "",
        recorded_port_id=row.port_id,
        recorded_server_id=row.server_id,
    )


@dataclass
class _State:
    share_id: str | None = None
    port_id: str | None = None
    server_id: str | None = None
    rw_access_id: str | None = None


# ---------------------------------------------------------------------------
# Create-or-recover primitives
# ---------------------------------------------------------------------------


def _resource_id(value) -> str:
    if isinstance(value, dict):
        return value["id"]
    return value.id


def _accepted_id(submission: dict | None) -> str | None:
    if not submission or submission.get("state") != "accepted":
        return None
    result = submission.get("result")
    if isinstance(result, dict):
        return result.get("id")
    return result if isinstance(result, str) else None


async def _recover_submission(step: str, observe, recorded: str | None = None) -> str | None:
    """Return an earlier CREATE's identity, or None when it was never submitted.

    An accepted result is returned for the caller to GET. A submission whose
    outcome is unknown is only adopted when exactly one resource carrying this
    build's identity exists; otherwise it fails closed and is never reissued.
    """
    submission = await build_work.submission_get(step)
    if submission is None:
        return recorded
    identity = _accepted_id(submission)
    if identity:
        return identity
    matches = await build_work.run_sync(observe)
    if len(matches) == 1:
        _logger.warning("[ephemeral_build] adopted %s from an unknown submission: %s", step, matches[0])
        return matches[0]
    raise build_work.SubmissionUnknown(
        f"{step} submission outcome is unknown ({len(matches)} matching resources); it will not be reissued"
    )


async def _create_or_recover(step: str, observe, fn, *args, recorded: str | None = None, **kwargs):
    """Return ``(identity, created)``; ``created`` is None when an earlier CREATE was recovered."""
    identity = await _recover_submission(step, observe, recorded)
    if identity is not None:
        return identity, None
    created = await build_work.submit(step, fn, *args, **kwargs)
    return _resource_id(created), created


async def _best_effort(label: str, fn, *args, **kwargs):
    """Fenced provider work whose failure must not change the build outcome."""
    try:
        return await build_work.run_sync(fn, *args, **kwargs)
    except _FENCE_ERRORS:
        raise
    except Exception:
        _logger.warning("[ephemeral_build] %s 실패", label, exc_info=True)
        return None


def _create_access_rule(conn, share_id: str, access_to: str, level: str, access_type: str = "cephx") -> dict:
    metadata = {"auth_flavor_list": ["sys"]} if access_type == "ip" else None
    rule = manila.create_access_rule(
        conn,
        share_id,
        access_to,
        level,
        access_type,
        metadata=metadata,
        wait_for_key=False,
    )
    # Persist identity only; CephX secrets are fetched under the current fence.
    return {"id": rule.get("access_id") or rule["id"]}


def _find_shares(conn, plan: _Plan) -> list[str]:
    return [
        share.id
        for share in manila.list_file_storages(conn)
        if share.name == plan.share_name and share.metadata.get("union_build") == plan.marker
    ]


def _find_ports(conn, plan: _Plan) -> list[str]:
    return [
        port.id
        for port in conn.network.ports(name=plan.port_name, network_id=plan.network_id)
        if port.name == plan.port_name and port.description == plan.marker
    ]


def _find_servers(conn, plan: _Plan) -> list[str]:
    return [
        server.id
        for server in conn.compute.servers(name=f"^{re.escape(plan.vm_name)}$")
        if server.name == plan.vm_name and (server.metadata or {}).get("afterglow_library_build") == plan.marker
    ]


def _find_access_rules(conn, share_id: str, access_to: str, level: str) -> list[str]:
    return [
        rule["id"]
        for rule in manila.list_access_rules(conn, share_id, strict=True)
        if rule.get("access_to") == access_to
        and rule.get("access_level") == level
        and rule.get("state") not in {"denying", "deleting", "error"}
    ]


# ---------------------------------------------------------------------------
# Provisioning steps
# ---------------------------------------------------------------------------


async def _await_share_available(conn, share_id: str) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _SHARE_READY_WAIT
    while True:
        share = await build_work.run_sync(manila.get_file_storage, conn, share_id)
        if share.status == "available":
            return
        if share.status == "error" or loop.time() >= deadline:
            raise RuntimeError(f"builder share {share_id} is not available (status={share.status})")
        await asyncio.sleep(5)


async def _ensure_share(conn, plan: _Plan, state: _State) -> str:
    if plan.admitted_share_id and await build_work.submission_get("share") is None:
        # 저수준 경로: 사전 생성된 share를 빌드 대상으로 사용 (재개 시에도 동일하게 검증)
        await _update_db(plan.build_id, status="creating_share", progress_step="기존 share 검증", progress_pct=5)
        try:
            await build_work.run_sync(manila.get_file_storage, conn, plan.admitted_share_id)
        except _FENCE_ERRORS:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"사전 생성 share {plan.admitted_share_id}를 service 프로젝트에서 찾을 수 없습니다. "
                "share가 service 프로젝트 소속이거나 공개(is_public=True) 상태여야 합니다. "
                f"원인: {exc}"
            ) from exc
        state.share_id = plan.admitted_share_id
        # 빌드 시작 메타데이터 세팅 — 성공 시 prebuilt로 승격됨
        await build_work.run_sync(
            manila.update_share_metadata,
            conn,
            state.share_id,
            {
                "union_type": "ephemeral-build",
                "union_status": "building",
                "union_library": plan.library_id,
                "union_version": plan.library_version,
            },
        )
        return state.share_id

    await _update_db(plan.build_id, status="creating_share", progress_step="Manila share 생성", progress_pct=5)
    share_id, _ = await _create_or_recover(
        "share",
        lambda: _find_shares(conn, plan),
        manila.submit_file_storage,
        conn,
        name=plan.share_name,
        size_gb=plan.share_size_gb,
        share_network_id=plan.share_network_id,
        share_type=plan.share_type,
        share_proto=plan.share_proto,
        metadata={
            "union_type": "ephemeral-build",
            "union_status": "building",
            "union_library": plan.library_id,
            "union_version": plan.library_version,
            "union_build": plan.marker,
        },
    )
    state.share_id = share_id
    await _await_share_available(conn, share_id)
    await _update_db(plan.build_id, file_storage_id=share_id)
    return share_id


async def _ensure_port(conn, plan: _Plan, state: _State) -> str:
    port_id, port = await _create_or_recover(
        "port",
        lambda: _find_ports(conn, plan),
        conn.network.create_port,
        network_id=plan.network_id,
        name=plan.port_name,
        description=plan.marker,
        recorded=plan.recorded_port_id,
    )
    state.port_id = port_id
    if port is None:
        port = await build_work.run_sync(conn.network.get_port, port_id)
        if port is None:
            raise RuntimeError(f"builder port {port_id} no longer exists")
    await _update_db(plan.build_id, port_id=port_id)
    fixed_ips = port.fixed_ips or []
    fixed_ip = fixed_ips[0].get("ip_address", "") if fixed_ips else ""
    if not fixed_ip:
        raise RuntimeError(f"builder port {port_id} has no fixed IP")
    _logger.info("[ephemeral_build] port 확보: %s (%s)", port_id, fixed_ip)
    return fixed_ip


async def _ensure_access(conn, plan: _Plan, state: _State, share_id: str, fixed_ip: str) -> dict:
    await _update_db(plan.build_id, status="creating_access", progress_step="Access rule 생성", progress_pct=10)
    access_to = fixed_ip if plan.share_proto == "NFS" else plan.cephx_user
    access_type = "ip" if plan.share_proto == "NFS" else "cephx"

    def observe():
        return _find_access_rules(conn, share_id, access_to, "rw")

    access_id = await _recover_submission("rw_access", observe)
    if access_id is None:
        matches = await build_work.run_sync(observe)
        if len(matches) > 1:
            raise RuntimeError(f"multiple builder RW rules match {access_to}")
        if matches:
            access_id = matches[0]
        else:
            accepted = await build_work.submit(
                "rw_access",
                _create_access_rule,
                conn,
                share_id,
                access_to,
                "rw",
                access_type,
            )
            access_id = accepted["id"]
    state.rw_access_id = access_id
    rule = await build_work.run_sync(manila.get_access_rule, conn, share_id, access_id)
    if rule is None:
        raise RuntimeError(f"builder access rule {access_id} no longer exists")
    cephx_secret = None
    if plan.share_proto == "CEPHFS":
        from app.config import get_settings

        timeout = get_settings().manila_cephx_key_timeout_seconds
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            rule = await build_work.run_sync(manila.get_access_rule, conn, share_id, access_id)
            cephx_secret = (rule or {}).get("access_key")
            if cephx_secret:
                break
            if rule is None or asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(f"CephX access key for rule {access_id} is unavailable")
            await asyncio.sleep(5)
    await build_work.journal_update(rw_access_id=state.rw_access_id)
    _logger.info("[ephemeral_build] access rule 확보: %s (proto=%s)", state.rw_access_id, plan.share_proto)

    export_locations = await build_work.run_sync(manila.get_export_locations, conn, share_id)
    if not export_locations:
        raise RuntimeError(f"Share {share_id}의 export location이 없습니다")
    export_path = export_locations[0]
    if plan.share_proto == "NFS":
        return {"share_proto": "NFS", "export_path": export_path}
    if ":" in export_path:
        ceph_mons, ceph_path = export_path.rsplit(":", 1)
    else:
        ceph_mons, ceph_path = export_path, "/"
    return {
        "share_proto": "CEPHFS",
        "ceph_mons": ceph_mons,
        "ceph_path": ceph_path,
        "cephx_user": plan.cephx_user,
        "cephx_secret": cephx_secret,
    }


async def _ensure_server(conn, plan: _Plan, state: _State, port_id: str, mount_spec: dict) -> str:
    await _update_db(plan.build_id, status="creating_vm", progress_step="VM 생성", progress_pct=15)
    server_id = await _recover_submission("server", lambda: _find_servers(conn, plan), plan.recorded_server_id)
    if server_id is None:
        user_data = render_user_data(plan.recipe, mount_spec, plan.build_token)
        server = await build_work.submit(
            "server",
            conn.compute.create_server,
            name=plan.vm_name,
            image_id=plan.image_id,
            flavor_id=plan.flavor_id,
            networks=[{"port": port_id}],
            user_data=base64.b64encode(user_data.encode()).decode(),
            metadata={
                "union_type": "ephemeral-build",
                "union_library": plan.library_id,
                "afterglow_managed": "true",
                "afterglow_library_build": plan.marker,
            },
        )
        server_id = server.id
        _logger.info("[ephemeral_build] VM 생성: %s (%s)", plan.vm_name, server_id)
    else:
        _logger.info("[ephemeral_build] 기존 VM 관찰: %s (build=%d)", server_id, plan.build_id)
    state.server_id = server_id
    await _update_db(
        plan.build_id,
        server_id=server_id,
        cloud_init_status="booting",
        progress_step="VM 부팅 중",
        progress_pct=20,
    )
    return server_id


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def _created_at(server) -> datetime | None:
    value = getattr(server, "created_at", None)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _console(conn, server_id: str, length: int | None) -> str:
    try:
        return await build_work.run_sync(nova.get_console_output, conn, server_id, length) or ""
    except _FENCE_ERRORS:
        raise
    except Exception:
        # SHUTOFF VM은 console이 없을 수 있음 (hypervisor 구현 차이)
        _logger.warning("[ephemeral_build] console_output 조회 실패: %s", server_id)
        return ""


async def _wait_for_shutoff(conn, plan: _Plan, server_id: str) -> tuple[str, str | None]:
    """Poll until SHUTOFF/ERROR; return the status and any sentinel seen while ACTIVE.

    The deadline counts from the server's own creation time, and an early sentinel
    is journaled, so a later owner continues the same wait instead of restarting it.
    """
    early = (await build_work.journal_get()).get("early_sentinel")
    success_tok = f"{_SUCCESS_SENTINEL}{plan.build_token}"
    failure_tok = f"{_FAILURE_SENTINEL}{plan.build_token}"
    started: datetime | None = None
    while True:
        server = await build_work.run_sync(conn.compute.get_server, server_id)
        status = (server.status or "").upper()
        started = started or _created_at(server) or datetime.now(UTC)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if status in ("SHUTOFF", "ERROR"):
            _logger.info("[ephemeral_build] VM %s 상태: %s (elapsed=%ds)", server_id, status, elapsed)
            return status, early
        if elapsed >= _SHUTOFF_MAX_WAIT:
            raise TimeoutError(f"VM {server_id}이 {_SHUTOFF_MAX_WAIT}s 내에 SHUTOFF 되지 않았습니다")
        if status == "ACTIVE" and elapsed > 60 and early is None:
            partial = await _console(conn, server_id, 200)
            if success_tok in partial:
                early = "success"
            elif failure_tok in partial:
                early = "failure"
            if early is not None:
                await build_work.journal_update(early_sentinel=early)
                _logger.info("[ephemeral_build] sentinel 조기 감지(%s) — SHUTOFF 대기 계속", early)
        await _update_db(plan.build_id, cloud_init_status="booting" if elapsed < 120 else "installing")
        await asyncio.sleep(_SHUTOFF_POLL_INTERVAL)


async def _observe_result(conn, plan: _Plan, server_id: str) -> dict:
    await _update_db(plan.build_id, status="building", progress_step="cloud-init 실행 중", progress_pct=25)
    vm_status, early = await _wait_for_shutoff(conn, plan, server_id)

    await _update_db(plan.build_id, cloud_init_status="finalizing", progress_step="결과 검증", progress_pct=90)
    console = await _console(conn, server_id, None)
    if console:
        await _update_db(plan.build_id, console_log_excerpt=console[-_EXCERPT_CHARS:])

    if f"{_SUCCESS_SENTINEL}{plan.build_token}" in console or early == "success":
        return {"result": "success"}
    if f"{_FAILURE_SENTINEL}{plan.build_token}" in console or early == "failure":
        return {"result": "failure", "message": "cloud-init FAILURE sentinel 감지 — console_log_excerpt 참조"}
    if vm_status == "ERROR":
        return {"result": "failure", "message": f"빌드 VM {server_id}이 ERROR 상태가 되었습니다"}
    _logger.error("[ephemeral_build] sentinel 부재 (indeterminate): library=%s", plan.library_id)
    return {"result": "indeterminate", "message": _INDETERMINATE_MESSAGE}


async def _drive(conn, plan: _Plan, state: _State) -> dict:
    journal = await build_work.journal_get()
    if journal.get("outcome"):
        # 이전 owner가 결과를 확정한 뒤 정리 도중 인계됨 — 관찰을 반복하지 않는다.
        return journal["outcome"]
    await _adopt_known(plan, state)
    server_id = await _recover_submission("server", lambda: _find_servers(conn, plan), plan.recorded_server_id)
    if server_id is not None:
        # A running VM already has its mount/user-data. Observe its output without
        # revisiting provisioning or creating access rules during handoff.
        state.server_id = server_id
        if state.share_id is None:
            raise build_work.SubmissionUnknown("existing build VM has no durable output share identity")
        await _update_db(
            plan.build_id,
            server_id=server_id,
            file_storage_id=state.share_id,
            port_id=state.port_id,
        )
        return await _observe_result(conn, plan, server_id)
    share_id = await _ensure_share(conn, plan, state)
    fixed_ip = await _ensure_port(conn, plan, state)
    mount_spec = await _ensure_access(conn, plan, state, share_id, fixed_ip)
    server_id = await _ensure_server(conn, plan, state, state.port_id, mount_spec)
    return await _observe_result(conn, plan, server_id)


# ---------------------------------------------------------------------------
# Completion and cleanup
# ---------------------------------------------------------------------------


async def _adopt_known(plan: _Plan, state: _State) -> None:
    """Merge identities a previous owner (or a late accepted response) made durable."""
    if state.share_id is None:
        state.share_id = _accepted_id(await build_work.submission_get("share")) or plan.admitted_share_id or None
    if state.port_id is None:
        state.port_id = _accepted_id(await build_work.submission_get("port")) or plan.recorded_port_id
    if state.server_id is None:
        state.server_id = _accepted_id(await build_work.submission_get("server")) or plan.recorded_server_id
    if state.rw_access_id is None:
        state.rw_access_id = _accepted_id(await build_work.submission_get("rw_access")) or (
            await build_work.journal_get()
        ).get("rw_access_id")


async def _ensure_ro_rule(conn, plan: _Plan, share_id: str, ro_user: str) -> bool:
    try:
        access_id, _ = await _create_or_recover(
            "ro_access",
            lambda: _find_access_rules(conn, share_id, ro_user, "ro"),
            _create_access_rule,
            conn,
            share_id,
            ro_user,
            "ro",
        )
        rule = await build_work.run_sync(manila.get_access_rule, conn, share_id, access_id)
        if rule is None:
            raise RuntimeError(f"readonly access rule {access_id} no longer exists")
    except build_work.SubmissionUnknown:
        # Keep the journaled successful build pending until this rule can be
        # observed. Unknown access is not a ready/public share.
        raise
    except _FENCE_ERRORS:
        raise
    except Exception:
        _logger.warning("[ephemeral_build] RO CephX rule 생성 실패", exc_info=True)
        return False
    _logger.info("[ephemeral_build] RO CephX rule 확보: %s", ro_user)
    return True


async def _promote_share(conn, plan: _Plan, state: _State) -> None:
    """빌드 성공 처리: RW rule 회수 → RO rule 생성 → 메타데이터 갱신 → share 공개."""
    share_id = state.share_id
    if state.rw_access_id:
        await _best_effort("RW access rule 회수", manila.revoke_access_rule, conn, share_id, state.rw_access_id)
    metadata: dict[str, str] = {
        "union_type": "prebuilt",  # 완료 share를 prebuilt로 승격 → 409 dedup 정상 작동
        "union_status": "ready",
        "union_built_at": datetime.now(UTC).isoformat(),
        "union_library": plan.library_id,
        "union_version": plan.library_version,
    }
    ro_user = f"union-ro-{plan.library_id}"
    if plan.share_proto == "CEPHFS" and await _ensure_ro_rule(conn, plan, share_id, ro_user):
        metadata["union_cephx_user"] = ro_user
    await _best_effort("메타데이터 갱신", manila.update_share_metadata, conn, share_id, metadata)
    await _best_effort("set_share_public", manila.set_share_public, conn, share_id, True)


async def _finalize(conn, plan: _Plan, state: _State, outcome: dict) -> None:
    """Persist the decided outcome first, then clean up, then seal the SQL row.

    Every provider step is fenced and repeatable, so an owner that takes over
    midway resumes from the journaled outcome instead of re-observing a VM that
    may already be deleted.
    """
    await build_work.journal_update(outcome=outcome)
    await _adopt_known(plan, state)
    result = outcome["result"]
    if result == "success" and state.share_id:
        await _promote_share(conn, plan, state)
    elif state.share_id:
        status = "indeterminate" if result == "indeterminate" else "error"
        await _best_effort(
            "share 상태 갱신", manila.update_share_metadata, conn, state.share_id, {"union_status": status}
        )
    if state.server_id:
        await _best_effort("server 삭제", conn.compute.delete_server, state.server_id)
    if state.port_id:
        await _best_effort("port 삭제", neutron.delete_port, conn, state.port_id)
    await _update_db(plan.build_id, **_TERMINAL_FIELDS[result], error_message=outcome.get("message"), completed=True)
    _logger.info("[ephemeral_build] 빌드 종료(%s): library=%s, share=%s", result, plan.library_id, state.share_id)


async def _release_after_fence(conn, plan: _Plan, state: _State) -> None:
    """Remove transient resources only when another actor ended a row this owner still leases.

    Lease loss, an unavailable database, or a still-runnable row leaves the VM,
    port and console output untouched for the next owner. CREATE responses that
    were accepted after the fence are included via the submission journal.
    """
    try:
        status = await _row_status(plan.build_id)
    except Exception:
        _logger.warning("[ephemeral_build] fence 후 SQL 상태 확인 불가 — 리소스를 인계 대상으로 유지")
        return
    if status is not None and status not in _ABANDONED:
        return
    try:
        await _adopt_known(plan, state)
    except Exception:
        _logger.warning("[ephemeral_build] fence 후 journal 조회 실패 — 리소스를 유지", exc_info=True)
        return
    steps = []
    if state.server_id:
        steps.append(("server", conn.compute.delete_server, (state.server_id,)))
    if state.port_id:
        steps.append(("port", neutron.delete_port, (conn, state.port_id)))
    if state.share_id and state.rw_access_id:
        steps.append(("RW access rule", manila.revoke_access_rule, (conn, state.share_id, state.rw_access_id)))
    for label, fn, args in steps:
        try:
            await build_work.cleanup_owned(fn, *args)
            _logger.info("[ephemeral_build] 종료된 빌드 %d의 %s 정리", plan.build_id, label)
        except DispatcherUnavailable:
            _logger.warning("[ephemeral_build] 실행 lease 상실 — %s 정리를 다음 owner에 맡김", label)
            return
        except Exception:
            _logger.warning("[ephemeral_build] 종료된 빌드의 %s 정리 실패", label, exc_info=True)


async def _cancel_observe(step: str, observe) -> str | None:
    """Cleanup-only view of an unknown CREATE: one build-tagged match, or proven absence."""
    submission = await build_work.submission_get(step)
    if submission is None or _accepted_id(submission):
        return None
    matches = await build_work.run_sync(observe)
    if len(matches) > 1:
        raise build_work.SubmissionUnknown(f"cancelled build {step} matches {len(matches)} resources")
    return matches[0] if matches else None


async def _port_ip(conn, port_id: str | None) -> str | None:
    if not port_id:
        return None
    try:
        port = await build_work.run_sync(conn.network.get_port, port_id)
    except ResourceNotFound:
        return None
    fixed_ips = (port.fixed_ips or []) if port is not None else []
    return fixed_ips[0].get("ip_address") if fixed_ips else None


async def _revoke_cancelled_rule(conn, share_id: str, access_id: str) -> None:
    """Deny once; Manila removes the rule asynchronously and only its 404 proves revocation."""
    rule = await build_work.run_sync(manila.get_access_rule, conn, share_id, access_id)
    if rule is None:
        return
    if rule.get("state") not in _DENY_STATES:
        await build_work.cleanup_owned(manila.revoke_access_rule, conn, share_id, access_id)
    for _ in range(_REVOKE_POLLS):
        if await build_work.run_sync(manila.get_access_rule, conn, share_id, access_id) is None:
            return
        await asyncio.sleep(_REVOKE_POLL_INTERVAL)
    raise RuntimeError(f"builder RW access rule {access_id} revocation is still pending")


async def _release_cancelled(conn, plan: _Plan | None, state: _State) -> None:
    if plan is not None:
        if state.share_id is None:
            state.share_id = await _cancel_observe("share", lambda: _find_shares(conn, plan))
        if state.port_id is None:
            state.port_id = await _cancel_observe("port", lambda: _find_ports(conn, plan))
        if state.server_id is None:
            state.server_id = await _cancel_observe("server", lambda: _find_servers(conn, plan))
        if state.share_id and state.rw_access_id is None:
            share_id = state.share_id
            access_to = plan.cephx_user if plan.share_proto == "CEPHFS" else await _port_ip(conn, state.port_id)
            if access_to:
                state.rw_access_id = await _cancel_observe(
                    "rw_access", lambda: _find_access_rules(conn, share_id, access_to, "rw")
                )
    # NFS grants are found through the port IP, so revoke before deleting the port.
    if state.share_id and state.rw_access_id:
        await _revoke_cancelled_rule(conn, state.share_id, state.rw_access_id)
    if state.server_id:
        await build_work.cleanup_owned(conn.compute.delete_server, state.server_id)
    if state.port_id:
        await build_work.cleanup_owned(neutron.delete_port, conn, state.port_id)


async def _finish_cancellation(build_db_id: int) -> None:
    """Close an admin cancellation after removing its transient builder resources.

    The cleanup owner never submits a CREATE. It removes exact SQL/journal
    identities and adopts an unknown submission only when exactly one resource
    with this build's identity exists (none proves it never landed). The output
    share is kept, as on every cancellation; only its builder RW grant is revoked.
    """
    from app.database import get_session_factory
    from app.models.db import LibraryBuild

    await build_work.checkpoint()
    factory = get_session_factory()
    if factory is None:
        raise DispatcherUnavailable("build database is unavailable")
    async with factory() as session:
        row = await session.get(LibraryBuild, build_db_id)
    if row is None:
        raise DispatcherUnavailable("library cancellation cleanup authority changed")
    try:
        plan = _plan(row)
    except ValueError:
        plan = None  # Never admitted with a token: no journaled CREATE can exist.
    state = _State(share_id=row.file_storage_id or None, port_id=row.port_id, server_id=row.server_id)
    if plan is not None:
        await _adopt_known(plan, state)
        project_id = plan.service_project_id
    else:
        project_id = ((row.resource_snapshot or {}).get("openstack.service_project") or {}).get("id")
    if project_id and (plan is not None or state.server_id or state.port_id):
        conn = await open_connection(keystone.get_admin_connection_for_project, project_id)
        try:
            await _release_cancelled(conn, plan, state)
        finally:
            try:
                await build_work.cleanup_sync(conn.close)
            except Exception:
                _logger.warning("[ephemeral_build] service connection close failed", exc_info=True)
    async with factory() as session, session.begin():
        locked = await session.get(LibraryBuild, build_db_id, with_for_update=True)
        await build_work.current_binding().lease.check()
        if (
            locked is None
            or locked.status != "cancelled"
            or (locked.resource_snapshot or {}).get("cancel_cleanup") != "pending"
        ):
            raise DispatcherUnavailable("library cancellation cleanup authority changed")
        finished = deepcopy(locked.resource_snapshot)
        finished["cancel_cleanup"] = "done"
        locked.resource_snapshot = finished
        locked.completed_at = datetime.now(UTC)
    _logger.info("[ephemeral_build] 취소된 빌드 %d 정리 완료", build_db_id)


def _error_text(exc: BaseException) -> str:
    # httpx.HTTPStatusError의 경우 Manila 응답 본문 메시지 (+ 가용 type 목록) 를 표시
    if isinstance(exc, httpx.HTTPStatusError):
        return manila.format_error_message(exc)[:1000]
    return str(exc)[:1000]


async def _execute(conn, plan: _Plan) -> None:
    state = _State()
    try:
        outcome = await _drive(conn, plan, state)
    except build_work.SubmissionUnknown:
        # An old owner may still receive the accepted response. Keep the row and
        # resources runnable for observation; never turn ambiguity into cleanup.
        raise
    except _FENCE_ERRORS:
        await _release_after_fence(conn, plan, state)
        raise
    except Exception as exc:
        _logger.error("[ephemeral_build] 빌드 실패: library=%s", plan.library_id, exc_info=True)
        outcome = {"result": "failure", "message": _error_text(exc)}
    try:
        await _finalize(conn, plan, state, outcome)
    except _FENCE_ERRORS:
        await _release_after_fence(conn, plan, state)
        raise


async def run_ephemeral_build(build_db_id: int) -> None:
    """Execute or resume one admitted library build under the bound ``library:<id>`` target.

    Requires a ``build_work.bind`` context. The same entry serves first execution
    and handoff: SQL snapshot, admitted build token, recorded IDs and the CREATE
    journal decide whether each resource is created, observed or recovered.
    Ends with a terminal SQL row for a known outcome. SubmissionUnknown leaves
    the row/resources runnable for later observation, never for CREATE replay.
    DispatcherUnavailable (or a SQL/Redis error) and cancellation also preserve
    any running VM and output for the next owner. A cancellation-cleanup binding
    only removes the cancelled build's transient resources and seals the row.
    """
    if build_work.current_binding().member != f"library:{build_db_id}":
        raise DispatcherUnavailable("library build target does not match the bound execution lease")
    if build_work.current_binding().cancel_cleanup:
        await _finish_cancellation(build_db_id)
        return
    row = await _load_build(build_db_id)
    try:
        plan = _plan(row)
    except ValueError as exc:
        _logger.error("[ephemeral_build] 빌드 %d 실행 불가: %s", build_db_id, exc)
        await _update_db(build_db_id, **_TERMINAL_FIELDS["failure"], error_message=str(exc), completed=True)
        return
    conn = await open_connection(keystone.get_admin_connection_for_project, plan.service_project_id)
    try:
        await _execute(conn, plan)
    finally:
        try:
            await build_work.cleanup_sync(conn.close)
        except Exception:
            _logger.warning("[ephemeral_build] service connection close failed", exc_info=True)
