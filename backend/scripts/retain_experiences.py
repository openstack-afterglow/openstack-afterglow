"""Explicit diagnostic maintenance; dry-run by default, never a scheduled job.

Run from backend: python scripts/retain_experiences.py --database-url <isolated-url>
An operator must separately review backups and holds before supplying --apply.
Hold/release: add --hold/--release SEGMENT_UUID --user-id USER --project-id PROJECT.
These operations are also dry-run unless --apply is supplied and never infer scope.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.database import close_db, init_db  # noqa: E402
from app.models.experience import ExperienceHold, ExperienceOperationLink, ExperienceRecord, uuid_string  # noqa: E402
from app.services import experience as store  # noqa: E402


async def maintain_hold(
    *,
    segment_id: str,
    user_id: str,
    project_id: str,
    release: bool = False,
    apply: bool = False,
) -> dict:
    """Manage one explicitly named owner's existing diagnostic segment.

    This is a maintenance-DB operation, not an HTTP authorization endpoint.
    Correlation IDs never select other owners or establish business ownership.
    """
    uuid_string(segment_id)
    actor = store._actor({"user_id": user_id, "project_id": project_id})
    if not all(actor.values()):
        raise ValueError("An explicit user and project are required")
    owner_key = store._digest(actor)
    async with store._factory()() as session:
        async with session.begin():
            if apply:
                # SQL/Galera maintenance serialization is shared with retain().
                # Lock before even reading hold/existence state.
                await store.lock_maintenance(session)
            hold = await session.get(ExperienceHold, (owner_key, segment_id))
            detail_count = await session.scalar(
                select(func.count())
                .select_from(ExperienceRecord)
                .where(
                    ExperienceRecord.owner_key == owner_key,
                    ExperienceRecord.segment_id == segment_id,
                    ExperienceRecord.user_id == user_id,
                    ExperienceRecord.project_id == project_id,
                )
            )
            link_count = await session.scalar(
                select(func.count())
                .select_from(ExperienceOperationLink)
                .where(
                    ExperienceOperationLink.owner_key == owner_key,
                    ExperienceOperationLink.segment_id == segment_id,
                    ExperienceOperationLink.user_id == user_id,
                    ExperienceOperationLink.project_id == project_id,
                )
            )
            if not release and hold is None and not detail_count and not link_count:
                raise ValueError("No diagnostic segment exists for the exact owner")
            candidates = int(hold is not None) if release else int(hold is None)
            result = {
                "apply": apply,
                "detail_matches": int(detail_count or 0),
                "link_matches": int(link_count or 0),
                "hold_candidates": 0 if release else candidates,
                "release_candidates": candidates if release else 0,
                "holds_created": 0,
                "holds_released": 0,
            }
            if apply and candidates:
                if release:
                    await session.delete(hold)
                    result["holds_released"] = 1
                else:
                    session.add(ExperienceHold(owner_key=owner_key, segment_id=segment_id))
                    result["holds_created"] = 1
        return result


async def run(args: argparse.Namespace) -> None:
    init_db(args.database_url)
    try:
        if args.hold is not None or args.release is not None:
            result = await maintain_hold(
                segment_id=args.hold if args.hold is not None else args.release,
                user_id=args.user_id,
                project_id=args.project_id,
                release=args.release is not None,
                apply=args.apply,
            )
        else:
            result = await store.retain(apply=args.apply, batch_size=args.batch_size)
        print(json.dumps(result, sort_keys=True))
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded semantic diagnostic retention (dry-run unless --apply)")
    parser.add_argument(
        "--database-url", required=True, help="Explicit maintenance database; never inferred from deployment"
    )
    parser.add_argument("--apply", action="store_true", help="Apply the requested retention or hold/release operation")
    parser.add_argument("--batch-size", type=int, default=500, choices=range(1, 2001), metavar="1..2000")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--hold", metavar="SEGMENT_UUID", help="Hold an existing exact-owner diagnostic segment")
    operation.add_argument("--release", metavar="SEGMENT_UUID", help="Release an exact-owner diagnostic hold")
    parser.add_argument("--user-id", help="Explicit existing diagnostic owner; required for hold/release")
    parser.add_argument("--project-id", help="Explicit originating project; required for hold/release")
    args = parser.parse_args()
    if args.hold is not None or args.release is not None:
        if not args.user_id or not args.project_id:
            parser.error("--hold/--release require both --user-id and --project-id")
    elif args.user_id is not None or args.project_id is not None:
        parser.error("--user-id/--project-id are only valid with --hold/--release")
    try:
        asyncio.run(run(args))
    except Exception:
        # Connection exceptions can include credentials; never echo them.
        parser.exit(1, "Experience retention failed; no success receipt was produced.\n")


if __name__ == "__main__":
    main()
