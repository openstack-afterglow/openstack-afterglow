import importlib.util
import tomllib
from pathlib import Path

import pytest

_RENDERER_PATH = (
    Path(__file__).resolve().parents[2] / "deploy/kolla/ansible/roles/afterglow/files/render_frontend_config.py"
)
_SPEC = importlib.util.spec_from_file_location("kolla_frontend_config_renderer", _RENDERER_PATH)
assert _SPEC and _SPEC.loader
_RENDERER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RENDERER)


def test_renderer_merges_layers_and_emits_only_public_fields(tmp_path: Path) -> None:
    base = tmp_path / "afterglow.conf"
    operator = tmp_path / "afterglow.operator.conf"
    frontend_operator = tmp_path / "afterglow.frontend.operator.conf"
    final = tmp_path / "afterglow.zz-kolla.conf"
    destination = tmp_path / "afterglow.frontend.conf"

    base.write_text(
        '[app]\nbackend_port = 8020\nsite_name = "Afterglow"\n'
        'site_description = "Cloud"\nlogo_path = "/afterglow-logo.svg"\n'
        'public_api_base = "http://internal:8020"\nsecret_key = "base-secret"\n'
        "\n[services]\nk3s = false\nchat = false\nmcp = false\n"
    )
    operator.write_text(
        '[app]\nsite_name = "Operator Cloud"\nlogo_dark_path = "/operator-dark.png"\n'
        'secret_key = "operator-secret"\n'
        '\n[openstack]\ns3_endpoint = "https://s3.example.com"\npassword = "keystone-secret"\n'
        '\n[monitoring]\ngrafana_base_url = "https://grafana.example.com"\n'
        'prometheus_password = "prometheus-secret"\n'
        '\n[chat]\nbase_url = "https://chat.example.com"\napi_key = "chat-secret"\n'
        '\n[gitlab_oidc]\nenabled = true\ngitlab_url = "https://git.example.com"\n'
        'client_secret = "gitlab-secret"\n'
        '\n[mcp]\npublic_url = "https://cloud.example.com/api/v1/mcp"\n'
        'lumen_service_token = "mcp-secret"\n'
        '\n[database]\nurl = "mysql://database-secret"\n'
    )
    frontend_operator.write_text(
        '[app]\nsite_name = "Frontend Cloud"\nlogo_light_path = "/frontend-light.png"\n'
        'public_api_base = "https://operator.example.com/api"\nsecret_key = "frontend-secret"\n'
        "\n[services]\nmanila = true\nk3s = false\n"
    )
    final.write_text(
        '[app]\npublic_api_base = "https://cloud.example.com"\n'
        'frontend_base_url = "https://cloud.example.com"\nsecret_key = "final-secret"\n'
        "\n[services]\nk3s = true\nchat = true\nmcp = true\n"
    )

    assert (
        _RENDERER.main(
            str(base),
            str(operator),
            str(frontend_operator),
            str(final),
            str(destination),
        )
        is True
    )

    rendered = tomllib.loads(destination.read_text())
    assert rendered == {
        "app": {
            "backend_port": 8020,
            "site_name": "Frontend Cloud",
            "site_description": "Cloud",
            "logo_path": "/afterglow-logo.svg",
            "logo_dark_path": "/operator-dark.png",
            "logo_light_path": "/frontend-light.png",
            "frontend_base_url": "https://cloud.example.com",
            "public_api_base": "https://cloud.example.com",
        },
        "services": {"k3s": True, "chat": True, "mcp": True, "manila": True},
        "openstack": {"s3_endpoint": "https://s3.example.com"},
        "monitoring": {"grafana_base_url": "https://grafana.example.com"},
        "chat": {"base_url": "https://chat.example.com"},
        "gitlab_oidc": {"enabled": True, "gitlab_url": "https://git.example.com"},
        "mcp": {"public_url": "https://cloud.example.com/api/v1/mcp"},
    }
    assert "secret" not in destination.read_text()
    assert destination.stat().st_mode & 0o777 == 0o644
    assert (
        _RENDERER.main(
            str(base),
            str(operator),
            str(frontend_operator),
            str(final),
            str(destination),
        )
        is False
    )


def test_renderer_rejects_invalid_public_field_type(tmp_path: Path) -> None:
    base = tmp_path / "afterglow.conf"
    operator = tmp_path / "afterglow.operator.conf"
    final = tmp_path / "afterglow.zz-kolla.conf"
    destination = tmp_path / "afterglow.frontend.conf"
    base.write_text('[app]\nsite_name = "Afterglow"\n')
    operator.write_text("# No operator overrides.\n")
    final.write_text('[services]\nchat = "yes"\n')

    with pytest.raises(TypeError, match=r"\[services\]\.chat must be bool"):
        _RENDERER.main(str(base), str(operator), str(final), str(destination))

    assert not destination.exists()
