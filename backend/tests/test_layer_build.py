"""layer_build orchestration regression tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.layer_build import _wait_for_shutoff


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
