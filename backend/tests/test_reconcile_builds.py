"""Prebuilt visibility after durable build discovery replaced startup orphan cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_libraries_uses_service_conn_with_include_public(admin_client):
    """The retained catalog discovers service-owned prebuilt shares."""
    from app.services.manila import FileStorageInfo

    fake_share = MagicMock(spec=FileStorageInfo)
    fake_share.library_name = "python311"
    fake_share.id = "share-prebuilt-123"

    with (
        patch("app.api.common.libraries.get_service_project_connection", return_value=MagicMock()),
        patch("app.api.common.libraries.manila.list_file_storages", return_value=[fake_share]) as mock_list,
    ):
        resp = await admin_client.get("/api/v1/libraries")

    assert resp.status_code == 200
    assert mock_list.call_args.kwargs["include_public"] is True
    py311 = next((lib for lib in resp.json() if lib["id"] == "python311"), None)
    if py311:
        assert py311["available_prebuilt"] is True
