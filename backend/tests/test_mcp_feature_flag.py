"""Public site-config projection for the inbound MCP rollout flag."""

from app.config import Settings, get_settings
from app.services.site_branding import configured_public_site_config


def _settings_with(**overrides) -> Settings:
    return get_settings().model_copy(update=overrides)


def test_services_mcp_defaults_to_disabled():
    assert Settings.model_fields["service_mcp_enabled"].default is False
    assert configured_public_site_config(_settings_with(service_mcp_enabled=False))["services"]["mcp"] is False


def test_services_mcp_projects_the_enabled_flag_without_enabling_transport():
    settings = _settings_with(service_mcp_enabled=True)

    assert configured_public_site_config(settings)["services"]["mcp"] is True
