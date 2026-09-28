"""layer_build orchestration regression tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.layer_build import (
    _wait_for_shutoff,
    run_layer_build,
)


@pytest.mark.asyncio
async def test_builder_retains_first_failure_trace_during_noisy_shutdown():
    token = "a" * 32
    conn = SimpleNamespace(
        compute=SimpleNamespace(
            get_server=MagicMock(
                side_effect=[
                    SimpleNamespace(status="ACTIVE"),
                    SimpleNamespace(status="ACTIVE"),
                    SimpleNamespace(status="SHUTOFF"),
                ]
            )
        )
    )
    with (
        patch("app.services.layer_build._SHUTOFF_POLL_INTERVAL", 61),
        patch("app.services.layer_build.asyncio.sleep", new_callable=AsyncMock),
        patch("app.services.layer_build._update_build_db", new_callable=AsyncMock) as update,
        patch(
            "app.services.layer_build.nova.get_console_output",
            side_effect=[
                f"Traceback: source device not found\n::AFTERGLOW::FAILURE::{token}",
                f"{'shutdown noise' * 1000}\n::AFTERGLOW::FAILURE::{token}",
            ],
        ),
    ):
        assert await _wait_for_shutoff(conn, "builder", 7, token) == (False, True)

    excerpts = [
        call.kwargs["console_log_excerpt"] for call in update.await_args_list if "console_log_excerpt" in call.kwargs
    ]
    assert excerpts == [f"Traceback: source device not found\n::AFTERGLOW::FAILURE::{token}"]


@pytest.mark.asyncio
async def test_run_layer_build_rejects_invalid_recipe_before_openstack_allocation():
    """Invalid recipes record an error before any OpenStack connection is opened."""
    with (
        patch("app.services.layer_build._update_build_db", new_callable=AsyncMock) as mock_update,
        patch("app.services.keystone.get_admin_connection_for_project") as mock_get_conn,
        patch("app.services.layer_build.neutron.create_port") as mock_create_port,
    ):
        await run_layer_build(
            build_db_id=123,
            layer_name="bad-python",
            kind="python",
            python_version="3.11",
            pip_packages=["numpy==1.26.4"],
            parent_artifact_id=7,
        )

    mock_get_conn.assert_not_called()
    mock_create_port.assert_not_called()
    error_updates = [call.kwargs for call in mock_update.await_args_list if call.kwargs.get("status") == "error"]
    assert error_updates
    assert "kind='python'" in error_updates[-1]["error_message"]
    assert "pip_packages" in error_updates[-1]["error_message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "kind": "python",
                "python_version": "3.11",
                "pip_packages": [],
                "pip_index_url": "https://download.pytorch.org/whl/cpu",
                "parent_artifact_id": 7,
            },
            "pip source",
        ),
        (
            {
                "kind": "system",
                "python_version": None,
                "pip_packages": [],
                "apt_packages": [],
            },
            "apt_packages",
        ),
    ],
)
async def test_run_layer_build_rejects_invalid_contract_before_openstack_allocation(kwargs, expected):
    with (
        patch("app.services.layer_build._update_build_db", new_callable=AsyncMock) as mock_update,
        patch("app.services.keystone.get_admin_connection_for_project") as mock_get_conn,
        patch("app.services.layer_build.neutron.create_port") as mock_create_port,
    ):
        await run_layer_build(build_db_id=124, layer_name="invalid", **kwargs)

    mock_get_conn.assert_not_called()
    mock_create_port.assert_not_called()
    error_updates = [call.kwargs for call in mock_update.await_args_list if call.kwargs.get("status") == "error"]
    assert expected in error_updates[-1]["error_message"]


@pytest.mark.asyncio
async def test_run_layer_build_requires_complete_snapshot_before_openstack_allocation():
    with (
        patch("app.services.layer_build._update_build_db", new_callable=AsyncMock) as mock_update,
        patch("app.services.keystone.get_admin_connection_for_project") as mock_get_conn,
        patch("app.services.layer_build.neutron.create_port") as mock_create_port,
    ):
        await run_layer_build(
            build_db_id=125,
            layer_name="uv",
            kind="uv",
            python_version=None,
            pip_packages=[],
            resource_snapshot={"base_image": {"id": "image-1"}},
        )

    mock_get_conn.assert_not_called()
    mock_create_port.assert_not_called()
    error_updates = [call.kwargs for call in mock_update.await_args_list if call.kwargs.get("status") == "error"]
    assert "resource snapshot is incomplete" in error_updates[-1]["error_message"]
