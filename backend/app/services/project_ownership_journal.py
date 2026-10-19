"""Graph lease precedes SQL; native uncertainty requires explicit settlement.

A fresh ownership read is evidence, never proof that a timed-out native call
has stopped. Every native step is journaled before dispatch. Crashed/unknown
steps block replay and new transfers until an administrator confirms settlement.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.api.common.errors import public_service_error
from app.database import get_session_factory
from app.models.project_ownership import ProjectOwnershipTransfer


@asynccontextmanager
async def session():
    factory = get_session_factory()
    if factory is None:
        raise public_service_error(503, "project_ownership_storage_unavailable")
    try:
        async with factory() as db:
            yield db
    except HTTPException:
        raise
    except Exception as exc:
        raise public_service_error(503, "project_ownership_storage_unavailable") from exc


def dto(row):
    if row is None:
        return None
    values = {
        key: getattr(row, key)
        for key in ("id", "project_id", "domain_id", "from_user_id", "to_user_id", "status", "stage")
    }
    if (
        any(not isinstance(value, str) or not value for value in values.values())
        or row.status not in {"applying", "unknown", "settled", "completed"}
        or row.stage
        not in {"prepared", "revoke", "grant", "initial_grant", "verified", "native_outcome_unknown", "reconciled"}
    ):
        raise public_service_error(503, "project_ownership_journal_unavailable")
    return values


async def _row(db, project_id, *, lock=False):
    query = select(ProjectOwnershipTransfer).where(ProjectOwnershipTransfer.project_id == project_id)
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def get(project_id):
    async with session() as db:
        return dto(await _row(db, project_id))


async def assert_resolved(project_id):
    operation = await get(project_id)
    if operation is not None and operation["status"] != "completed":
        raise HTTPException(409, "project_ownership_native_operation_unresolved")


async def _commit(db, lease):
    await lease.assert_owned()
    await db.commit()
    await lease.assert_owned()


async def begin(project_id, domain_id, old, target, *, lease):
    async with session() as db:
        row = await _row(db, project_id, lock=True)
        previous = dto(row)
        if previous and previous["status"] in {"applying", "unknown"}:
            raise HTTPException(409, "project_ownership_native_operation_unresolved")
        if previous and previous["status"] == "settled":
            if (row.domain_id, row.from_user_id, row.to_user_id) != (domain_id, old, target):
                raise HTTPException(409, "project_ownership_recovery_target_mismatch")
        else:
            if row is None:
                row = ProjectOwnershipTransfer(project_id=project_id)
                db.add(row)
            row.id = str(uuid4())
            row.domain_id, row.from_user_id, row.to_user_id = domain_id, old, target
        row.status, row.stage, row.updated_at = "applying", "prepared", datetime.now(UTC)
        await _commit(db, lease)
        return dto(row)


async def phase(operation, status, stage, *, lease):
    async with session() as db:
        row = await _row(db, operation["project_id"], lock=True)
        if row is None or row.id != operation["id"]:
            raise public_service_error(503, "project_ownership_journal_changed")
        row.status, row.stage, row.updated_at = status, stage, datetime.now(UTC)
        await _commit(db, lease)
        return dto(row)


async def reconcile(operation, observed, *, lease):
    # Caller has freshly verified system authority and explicit operator evidence
    # that ALL original native requests are no longer running. No native writes.
    completed = observed["status"] == "unique" or (
        observed["status"] == "missing" and operation["from_user_id"] == operation["to_user_id"]
    )
    status = "completed" if completed else "settled"
    return await phase(operation, status, "reconciled", lease=lease)


async def assert_user_resolved(user_id):
    async with session() as db:
        query = (
            select(ProjectOwnershipTransfer.project_id)
            .where(
                ProjectOwnershipTransfer.status != "completed",
                (ProjectOwnershipTransfer.from_user_id == user_id) | (ProjectOwnershipTransfer.to_user_id == user_id),
            )
            .limit(1)
        )
        if (await db.execute(query)).first() is not None:
            raise HTTPException(409, "project_ownership_native_operation_unresolved")


async def assert_domain_resolved(domain_id):
    async with session() as db:
        query = (
            select(ProjectOwnershipTransfer.project_id)
            .where(
                ProjectOwnershipTransfer.status != "completed",
                ProjectOwnershipTransfer.domain_id == domain_id,
            )
            .limit(1)
        )
        if (await db.execute(query)).first() is not None:
            raise HTTPException(409, "project_ownership_native_operation_unresolved")
