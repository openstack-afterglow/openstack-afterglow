#!/usr/bin/env python3
"""CLI Importer for GPU Quotas.

Migrates GPU quota records from a source database to Afterglow's target database.

Requirements:
  - Preserves exact row IDs, project_ids, limits, created_at, and updated_at timestamps.
  - Validates and canonicalizes all GPU alias names.
  - Fails closed on invalid source data, source alias collisions, or divergent target rows.
  - Supports --dry-run audit report mode.
  - Never automatically drops or truncates source data.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    INT,
    VARCHAR,
    Column,
    DateTime,
    MetaData,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.services.gpu_quota import normalize_gpu_alias

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_gpu_quotas")


def _parse_datetime(val: Any) -> datetime:
    """Parse datetime or ISO format string to UTC datetime object."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val.astimezone(UTC)
    if isinstance(val, str):
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    raise ValueError(f"Cannot parse datetime value: {val!r}")


def _open_sync_engine(database_url: str, label: str):
    """Open a synchronous engine for a configured async or sync MySQL URL."""
    try:
        url = make_url(database_url)
        if url.drivername in {"mysql+aiomysql", "mysql+asyncmy"}:
            url = url.set(drivername="mysql+pymysql")
        engine = create_engine(url, echo=False)
        with engine.connect():
            pass
        return engine
    except (SQLAlchemyError, ValueError):
        logger.error("%s database connection failed.", label)
        return None


def _build_gpu_quotas_table(metadata: MetaData) -> Table:
    """Define gpu_quotas table reflection/schema."""
    return Table(
        "gpu_quotas",
        metadata,
        Column("id", INT, primary_key=True, autoincrement=True),
        Column("project_id", VARCHAR(64), nullable=False),
        Column("gpu_type", VARCHAR(64), nullable=False),
        Column("limit", INT, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("project_id", "gpu_type", name="uq_gpu_quotas_project_gpu_type"),
    )


def _run_import(source_db_url: str, target_db_url: str, *, dry_run: bool = False) -> int:
    """Execute the GPU quota import workflow."""
    logger.info("Starting GPU quota import audit.")
    logger.info("Source and target database URLs were supplied.")
    logger.info("Mode: %s", "DRY-RUN (audit only)" if dry_run else "LIVE (apply mutations)")

    source_engine = _open_sync_engine(source_db_url, "Source")
    target_engine = _open_sync_engine(target_db_url, "Target")
    if source_engine is None or target_engine is None:
        return 1

    source_meta = MetaData()
    target_meta = MetaData()

    source_inspector = inspect(source_engine)
    if not source_inspector.has_table("gpu_quotas"):
        logger.error("Source database does not contain table 'gpu_quotas'. Cannot proceed.")
        return 1

    source_table = _build_gpu_quotas_table(source_meta)

    # The forward migration must create the target table before any import.
    target_inspector = inspect(target_engine)
    if not target_inspector.has_table("gpu_quotas"):
        logger.error("Target database does not contain table 'gpu_quotas'. Apply migration 076 before importing.")
        return 1
    target_table = _build_gpu_quotas_table(target_meta)

    # 1. Read source rows
    with source_engine.connect() as source_conn:
        source_rows_raw = list(source_conn.execute(select(source_table)).mappings().all())

    logger.info("Found %d raw records in source database.", len(source_rows_raw))

    # 2. Validate and canonicalize source rows
    validated_rows: list[dict[str, Any]] = []
    source_seen: dict[tuple[str, str], dict[str, Any]] = {}

    for row in source_rows_raw:
        row_id = row["id"]
        raw_project_id = row["project_id"]
        project_id = str(raw_project_id or "")
        gpu_type_raw = str(row["gpu_type"] or "").strip()
        limit = row["limit"]

        if not isinstance(row_id, int) or row_id <= 0:
            logger.error("Validation Error: Row has invalid id %r", row_id)
            return 1
        if not project_id or project_id != project_id.strip() or len(project_id) > 64:
            logger.error("Validation Error: Row ID %s has invalid project_id %r", row_id, raw_project_id)
            return 1

        if not isinstance(limit, int) or limit < -1:
            logger.error("Validation Error: Row ID %s has invalid limit %r", row_id, limit)
            return 1

        norm_gpu_type = normalize_gpu_alias(gpu_type_raw)
        if not norm_gpu_type or len(norm_gpu_type) > 64:
            logger.error("Validation Error: Row ID %s has invalid or un-normalizable gpu_type %r", row_id, gpu_type_raw)
            return 1

        try:
            created_at = _parse_datetime(row["created_at"])
            updated_at = _parse_datetime(row["updated_at"])
        except ValueError as exc:
            logger.error("Validation Error: Row ID %s has invalid timestamp: %s", row_id, exc)
            return 1

        key = (project_id, norm_gpu_type)
        if key in source_seen:
            prev = source_seen[key]
            logger.error(
                "Source Collision Error: Multiple source rows map to key (%s, %s): ID %s and ID %s",
                project_id,
                norm_gpu_type,
                prev["id"],
                row_id,
            )
            return 1

        v_row = {
            "id": row_id,
            "project_id": project_id,
            "gpu_type": norm_gpu_type,
            "limit": limit,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        source_seen[key] = v_row
        validated_rows.append(v_row)

    logger.info("Successfully validated %d source rows.", len(validated_rows))

    # 3. Inspect existing target rows
    with target_engine.connect() as target_conn:
        target_rows_raw = list(target_conn.execute(select(target_table)).mappings().all())

    target_map: dict[tuple[str, str], dict[str, Any]] = {}
    target_ids: dict[int, tuple[str, str]] = {}
    for r in target_rows_raw:
        row_id = r["id"]
        raw_project_id = r["project_id"]
        project_id = str(raw_project_id or "")
        gpu_type_raw = str(r["gpu_type"] or "").strip()
        norm_gpu_type = normalize_gpu_alias(gpu_type_raw)
        if (
            not isinstance(row_id, int)
            or row_id <= 0
            or not project_id
            or project_id != project_id.strip()
            or len(project_id) > 64
            or not norm_gpu_type
            or norm_gpu_type != gpu_type_raw
            or not isinstance(r["limit"], int)
            or r["limit"] < -1
        ):
            logger.error("Target Validation Error: Existing row ID %r is not a canonical valid quota row.", row_id)
            return 1
        key = (project_id, norm_gpu_type)
        if key in target_map:
            logger.error("Target Collision Error: Multiple target rows map to key %s.", key)
            return 1
        try:
            created_at = _parse_datetime(r["created_at"])
            updated_at = _parse_datetime(r["updated_at"])
        except ValueError as exc:
            logger.error("Target Validation Error: Row ID %s has invalid timestamp: %s", row_id, exc)
            return 1
        target_ids[row_id] = key
        target_map[key] = {
            "id": row_id,
            "project_id": project_id,
            "gpu_type": norm_gpu_type,
            "limit": r["limit"],
            "created_at": created_at,
            "updated_at": updated_at,
        }

    # 4. Check for target divergence and separate rows to insert
    rows_to_insert: list[dict[str, Any]] = []
    identical_existing = 0

    for s_row in validated_rows:
        t_key = (s_row["project_id"], s_row["gpu_type"])
        existing_id_key = target_ids.get(s_row["id"])
        if existing_id_key is not None and existing_id_key != t_key:
            logger.error(
                "Target ID Collision Error: Source row ID %s for key %s conflicts with target key %s.",
                s_row["id"],
                t_key,
                existing_id_key,
            )
            return 1
        if t_key in target_map:
            t_row = target_map[t_key]
            # Verify exact equality
            if (
                t_row["limit"] != s_row["limit"]
                or t_row["id"] != s_row["id"]
                or t_row["created_at"] != s_row["created_at"]
                or t_row["updated_at"] != s_row["updated_at"]
            ):
                logger.error(
                    "Target Divergence Error: Target row for key %s differs from source. "
                    "Source: (id=%s, limit=%s, created_at=%s, updated_at=%s), "
                    "Target: (id=%s, limit=%s, created_at=%s, updated_at=%s)",
                    t_key,
                    s_row["id"],
                    s_row["limit"],
                    s_row["created_at"],
                    s_row["updated_at"],
                    t_row["id"],
                    t_row["limit"],
                    t_row["created_at"],
                    t_row["updated_at"],
                )
                return 1
            identical_existing += 1
        else:
            rows_to_insert.append(s_row)

    # Report audit statistics
    logger.info("--- GPU Quota Import Audit Summary ---")
    logger.info("Total source rows:        %d", len(source_rows_raw))
    logger.info("Validated source rows:    %d", len(validated_rows))
    logger.info("Identical target rows:    %d", identical_existing)
    logger.info("New rows to insert:       %d", len(rows_to_insert))

    if dry_run:
        logger.info("DRY-RUN completed successfully. No changes written to target database.")
        return 0

    if not rows_to_insert:
        logger.info("Target database is already fully synchronized. No new rows to insert.")
        return 0

    # 5. Perform insertions
    logger.info("Inserting %d new rows into target database...", len(rows_to_insert))
    with target_engine.begin() as target_conn:
        for item in rows_to_insert:
            target_conn.execute(target_table.insert().values(**item))

    # 6. Verify exact result
    with target_engine.connect() as target_conn:
        verif_rows = list(target_conn.execute(select(target_table)).mappings().all())

    verif_map = {(r["project_id"], r["gpu_type"]): r for r in verif_rows}
    for item in rows_to_insert:
        v_key = (item["project_id"], item["gpu_type"])
        if v_key not in verif_map:
            logger.error("Verification Error: Key %s missing in target database after insert!", v_key)
            return 1
        v_target = verif_map[v_key]
        if (
            v_target["id"] != item["id"]
            or v_target["limit"] != item["limit"]
            or _parse_datetime(v_target["created_at"]) != item["created_at"]
            or _parse_datetime(v_target["updated_at"]) != item["updated_at"]
        ):
            logger.error(
                "Verification Error: Key %s differs after insert. Source=%s, target=%s",
                v_key,
                item,
                dict(v_target),
            )
            return 1

    logger.info("Verification succeeded! Exactly %d rows inserted and verified.", len(rows_to_insert))
    return 0


def run_import(source_db_url: str, target_db_url: str, *, dry_run: bool = False) -> int:
    """Run the audit importer without exposing database URLs on connection errors."""
    try:
        return _run_import(source_db_url, target_db_url, dry_run=dry_run)
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("GPU quota import database operation failed: %s", type(exc).__name__)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Import GPU quotas from source DB to Afterglow target DB.")
    parser.add_argument("--source-db-url", required=True, help="Source database URL")
    parser.add_argument("--target-db-url", required=True, help="Target database URL")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Audit mode without performing mutations")
    args = parser.parse_args()

    sys.exit(run_import(args.source_db_url, args.target_db_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
