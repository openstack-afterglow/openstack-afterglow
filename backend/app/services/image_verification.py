"""Project-independent, DB-owned approval of an exact Glance image incarnation.

Glance properties and tags are user-editable and are never consulted for trust.
The raw Glance list cache contains digest/identity fields, never approval state.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.database import get_session_factory, is_db_available, mark_db_unhealthy
from app.models.compute import ImageInfo
from app.models.db import ImageVerification

_logger = logging.getLogger(__name__)


class VerificationUnavailable(Exception):
    """The authoritative store could not confirm or persist approval."""


class ImageNotVerifiable(Exception):
    """The Glance image is not active or its immutable identity is incomplete."""


def _identity(image: ImageInfo) -> tuple[str, str, datetime, str, str] | None:
    try:
        image_id = str(UUID(image.id))
        owner = image.owner
        created = datetime.fromisoformat(image.created_at.replace("Z", "+00:00")) if image.created_at else None
        algorithm = (image.os_hash_algo or "").lower()
        digest = (image.os_hash_value or "").lower()
        if (
            not owner
            or not created
            or algorithm not in {"sha256", "sha512"}
            or len(digest) != {"sha256": 64, "sha512": 128}[algorithm]
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            return None
        return (image_id, owner, created.replace(tzinfo=created.tzinfo or UTC).astimezone(UTC), algorithm, digest)
    except (ValueError, TypeError, AttributeError):
        return None


def _matches(image: ImageInfo, record: ImageVerification) -> bool:
    identity = _identity(image)
    if not identity or image.status != "active":
        return False
    recorded = record.image_created_at.replace(tzinfo=record.image_created_at.tzinfo or UTC).astimezone(UTC)
    return identity == (record.image_id, record.owner_id, recorded, record.hash_algorithm, record.hash_value)


def _factory():
    factory = get_session_factory()
    if factory is None or not is_db_available():
        raise VerificationUnavailable("Image verification storage is unavailable")
    return factory


async def enrich(images: list[ImageInfo]) -> list[ImageInfo]:
    """Batch one DB read per page, preserving each caller's raw Glance objects."""
    if not images:
        return images
    try:
        factory = _factory()
        async with factory() as session:
            records = (
                await session.scalars(
                    select(ImageVerification).where(ImageVerification.image_id.in_([image.id for image in images]))
                )
            ).all()
    except VerificationUnavailable:
        return [
            image.model_copy(update={"verification_status": "unavailable", "verified_at": None}) for image in images
        ]
    except Exception as exc:
        mark_db_unhealthy(exc)
        _logger.warning("Image verification read unavailable", exc_info=True)
        return [
            image.model_copy(update={"verification_status": "unavailable", "verified_at": None}) for image in images
        ]
    by_id = {record.image_id: record for record in records}
    enriched = []
    for image in images:
        record = by_id.get(image.id)
        if record is not None and _matches(image, record):
            verified_at = record.verified_at.replace(tzinfo=record.verified_at.tzinfo or UTC).astimezone(UTC)
            enriched.append(
                image.model_copy(update={"verification_status": "verified", "verified_at": verified_at.isoformat()})
            )
        else:
            enriched.append(image.model_copy(update={"verification_status": "unverified", "verified_at": None}))
    return enriched


async def set_verification(image: ImageInfo, *, verified: bool, actor_id: str) -> None:
    """Approve an active image with a Glance-owned strong hash, or revoke its row."""
    identity = _identity(image)
    if verified and (image.status != "active" or identity is None):
        raise ImageNotVerifiable("Only active images with owner, creation time and SHA digest can be approved")
    try:
        factory = _factory()
        async with factory() as session, session.begin():
            existing = await session.get(ImageVerification, image.id)
            if not verified:
                if existing:
                    await session.delete(existing)
            else:
                if not actor_id:
                    raise ImageNotVerifiable("Administrator identity is required")
                image_id, owner, created, algorithm, digest = identity
                if existing is None:
                    existing = ImageVerification(image_id=image_id)
                    session.add(existing)
                existing.owner_id = owner
                existing.image_created_at = created
                existing.hash_algorithm = algorithm
                existing.hash_value = digest
                existing.verified_by = actor_id
                existing.verified_at = datetime.now(UTC)
    except ImageNotVerifiable:
        raise
    except Exception as exc:
        mark_db_unhealthy(exc)
        _logger.warning("Image verification write unavailable", exc_info=True)
        raise VerificationUnavailable("Image verification storage is unavailable") from exc


async def remove_deleted_image(image_id: str) -> None:
    """Remove the stored approval only after a successful Glance deletion."""
    try:
        factory = _factory()
        async with factory() as session, session.begin():
            existing = await session.get(ImageVerification, image_id)
            if existing:
                await session.delete(existing)
    except Exception as exc:
        mark_db_unhealthy(exc)
        _logger.warning("Deleted image approval cleanup unavailable", exc_info=True)
        raise VerificationUnavailable("Image verification storage is unavailable") from exc
