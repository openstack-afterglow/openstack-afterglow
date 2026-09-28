"""Image verification decisions are independent of Glance properties and visibility."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.compute import ImageDetail
from app.services import image_verification as svc

_ID = str(uuid4())
_HASH = "a" * 128


def _image(**changes):
    fields = dict(
        id=_ID,
        name="ubuntu:latest",
        status="active",
        owner="owner-project",
        created_at="2026-09-24T12:30:00.123456+00:00",
        visibility="public",
        os_hash_algo="sha512",
        os_hash_value=_HASH,
        properties={"verified": "true", "verification_status": "verified"},
    )
    fields.update(changes)
    return ImageDetail(**fields)


@pytest.mark.asyncio
async def test_unavailable_store_is_not_approval():
    with patch.object(svc, "get_session_factory", return_value=None):
        images = await svc.enrich([_image()])
        assert images[0].verification_status == "unavailable"
        assert images[0].verified_at is None
        with pytest.raises(svc.VerificationUnavailable):
            await svc.set_verification(_image(), verified=True, actor_id="admin")


@pytest.mark.asyncio
async def test_approval_requires_identifiable_active_image():
    with pytest.raises(svc.ImageNotVerifiable):
        await svc.set_verification(_image(status="queued"), verified=True, actor_id="admin")
    with pytest.raises(svc.ImageNotVerifiable):
        await svc.set_verification(_image(os_hash_value=None), verified=True, actor_id="admin")
    with pytest.raises(svc.ImageNotVerifiable):
        await svc.set_verification(_image(id="not-an-image-id"), verified=True, actor_id="admin")


@pytest.mark.asyncio
async def test_nonadmin_cannot_approve(non_admin_client, mock_conn):
    mock_conn.image.get_image.return_value = SimpleNamespace(id=_ID)
    response = await non_admin_client.put(f"/api/v1/admin/images/{_ID}/verification", json={"verified": True})
    assert response.status_code == 403
    mock_conn.image.get_image.assert_not_called()


@pytest.mark.asyncio
async def test_approval_failure_is_explicit_to_admin(admin_client, mock_conn):
    with (
        patch("app.api.identity.admin_images.glance.get_image", return_value=_image()),
        patch.object(svc, "get_session_factory", return_value=None),
    ):
        response = await admin_client.put(f"/api/v1/admin/images/{_ID}/verification", json={"verified": True})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_admin_upload_persistence_failure_returns_created_image(admin_client, mock_conn):
    image = SimpleNamespace(id=_ID, name="ubuntu:latest", status="queued", disk_format="raw")
    mock_conn.image.create_image.return_value = image
    with (
        patch("app.api.compute.images.glance.get_image", return_value=_image()),
        patch(
            "app.api.compute.images.image_verification.set_verification",
            new=AsyncMock(side_effect=svc.VerificationUnavailable()),
        ) as save,
        patch("app.api.compute.images.rec", new=AsyncMock()),
    ):
        response = await admin_client.post(
            "/api/v1/images",
            files={
                "name": (None, "ubuntu"),
                "file": ("ubuntu.raw", BytesIO(b"test"), "application/octet-stream"),
            },
        )
    assert response.status_code == 201
    assert response.json()["id"] == _ID
    assert response.json()["verification_status"] == "unavailable"
    assert response.json()["verification_message"]
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_nonadmin_upload_cannot_gain_verification(client, mock_conn):
    image = SimpleNamespace(id=_ID, name="ubuntu:latest", status="active", disk_format="raw")
    mock_conn.image.create_image.return_value = image
    with patch("app.api.compute.images.rec", new=AsyncMock()):
        response = await client.post(
            "/api/v1/images",
            files={
                "name": (None, "ubuntu"),
                "file": ("ubuntu.raw", BytesIO(b"test"), "application/octet-stream"),
            },
        )
    assert response.status_code == 201
    assert response.json()["verification_status"] == "unavailable"


@pytest.mark.db
@pytest.mark.asyncio
async def test_real_datastore_approval_revocation_and_identity_drift(admin_client, mock_conn):
    """Runs under the disposable functional MariaDB, without dropping other tables."""
    import os

    from sqlalchemy.ext.asyncio import create_async_engine

    from app import database
    from app.models.db import ImageVerification

    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: ImageVerification.__table__.create(sync, checkfirst=True))
    await engine.dispose()
    database.init_db(url)
    image = _image(id=str(uuid4()))
    uploaded = _image(id=str(uuid4()))
    try:
        # Existing public images and user-set Glance properties are not approval.
        assert (await svc.enrich([image]))[0].verification_status == "unverified"
        with patch("app.api.identity.admin_images.glance.get_image", return_value=image):
            response = await admin_client.put(f"/api/v1/admin/images/{image.id}/verification", json={"verified": True})
            assert response.status_code == 200
            assert response.json()["verification_status"] == "verified"
            assert response.json()["verified_at"] is not None
            detail = await admin_client.get(f"/api/v1/admin/images/{image.id}")
            assert detail.json()["verification_status"] == "verified"
        sdk_list_image = SimpleNamespace(
            **image.model_dump(), hash_algo=image.os_hash_algo, hash_value=image.os_hash_value, is_protected=False
        )
        mock_conn.image.images.return_value = iter([sdk_list_image])
        listed = await admin_client.get("/api/v1/admin/images")
        assert listed.json()["items"][0]["verification_status"] == "verified"
        with patch("app.api.compute.images.glance.get_image", return_value=image):
            user_detail = await admin_client.get(f"/api/v1/images/{image.id}")
        assert user_detail.json()["verification_status"] == "verified"
        # Simulate the SDK's pre-upload queued return; the fetched active image
        # supplies the actual Glance digest used for persisted approval.
        mock_upload = SimpleNamespace(id=uploaded.id, name=uploaded.name, status="queued", disk_format="raw")
        with (
            patch("app.api.compute.images.glance.create_image", return_value=mock_upload),
            patch("app.api.compute.images.glance.get_image", return_value=uploaded),
            patch("app.api.compute.images.rec", new=AsyncMock()),
        ):
            created = await admin_client.post(
                "/api/v1/images",
                files={
                    "name": (None, "ubuntu"),
                    "file": ("ubuntu.raw", BytesIO(b"uploaded data"), "application/octet-stream"),
                },
            )
        assert created.status_code == 201
        assert created.json()["verification_status"] == "verified"
        assert (await svc.enrich([uploaded]))[0].verification_status == "verified"
        assert (await svc.enrich([image.model_copy(update={"owner": "other-project"})]))[
            0
        ].verification_status == "unverified"
        assert (await svc.enrich([image.model_copy(update={"created_at": "2026-09-25T12:30:00Z"})]))[
            0
        ].verification_status == "unverified"
        assert (await svc.enrich([image.model_copy(update={"os_hash_value": "b" * 128})]))[
            0
        ].verification_status == "unverified"
        assert (await svc.enrich([image.model_copy(update={"status": "deactivated"})]))[
            0
        ].verification_status == "unverified"
        with patch("app.api.identity.admin_images.glance.get_image", return_value=image):
            revoked = await admin_client.put(f"/api/v1/admin/images/{image.id}/verification", json={"verified": False})
        assert revoked.status_code == 200
        assert revoked.json()["verification_status"] == "unverified"
        assert (await svc.enrich([image]))[0].verification_status == "unverified"
        with patch("app.api.identity.admin_images.glance.delete_image"):
            deleted_admin = await admin_client.delete(f"/api/v1/admin/images/{uploaded.id}")
        assert deleted_admin.status_code == 204
        assert (await svc.enrich([uploaded]))[0].verification_status == "unverified"
        await svc.set_verification(image, verified=True, actor_id="admin")
        with patch("app.api.compute.images.glance.delete_image"):
            deleted_user = await admin_client.delete(f"/api/v1/images/{image.id}")
        assert deleted_user.status_code == 204
        assert (await svc.enrich([image]))[0].verification_status == "unverified"
    finally:
        factory = database.get_session_factory()
        async with factory() as session, session.begin():
            for image_id in (image.id, uploaded.id):
                row = await session.get(ImageVerification, image_id)
                if row:
                    await session.delete(row)
        await database.close_db()
