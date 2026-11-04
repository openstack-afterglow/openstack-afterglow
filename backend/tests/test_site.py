"""Public feature discovery must not expose diagnostic operator policy or secrets."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_public_site_config_exposes_only_experience_opt_in(monkeypatch, enabled):
    secret = "private-operator-policy-canary"
    settings = get_settings().model_copy(
        update={
            "experience_enabled": enabled,
            "experience_anonymous_read_enabled": True,
            "experience_detail_retention_days": 31,
            "experience_aggregate_retention_days": 99,
            "secret_key": secret,
            "service_mcp_enabled": True,
        }
    )
    monkeypatch.setattr("app.api.common.site.get_settings", lambda: settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/site-config")
    assert response.status_code == 200
    data = response.json()
    assert data["experience_enabled"] is enabled
    assert data["services"]["mcp"] is True
    assert "experience_anonymous_read_enabled" not in data
    assert "experience_detail_retention_days" not in data
    assert "experience_aggregate_retention_days" not in data
    assert secret not in response.text
