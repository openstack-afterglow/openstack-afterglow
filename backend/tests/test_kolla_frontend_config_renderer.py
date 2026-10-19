import copy
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
    destination = tmp_path / "afterglow.frontend.conf"

    base.write_text(
        '[app]\nbackend_port = 8020\nsite_name = "Afterglow"\n'
        'site_description = "Cloud"\nlogo_path = "/afterglow-logo.svg"\n'
        'public_api_base = "http://internal:8020"\nsecret_key = "base-secret"\n'
        'frontend_base_url = "https://native.example.com"\n'
        "\n[services]\nk3s = true\nchat = false\nmcp = false\n"
    )
    operator.write_text(
        '[app]\nsite_name = "Operator Cloud"\nlogo_dark_path = "/operator-dark.png"\n'
        'public_api_base = "https://backend-operator.example.com"\nsecret_key = "operator-secret"\n'
        '\n[openstack]\ns3_endpoint = "https://s3.example.com"\npassword = "keystone-secret"\n'
        '\n[monitoring]\ngrafana_base_url = "https://grafana.example.com"\n'
        'prometheus_password = "prometheus-secret"\n'
        '\n[chat]\nbase_url = "https://chat.example.com"\napi_key = "chat-secret"\n'
        '\n[mcp]\npublic_url = "https://cloud.example.com/api/v1/mcp"\n'
        'lumen_service_token = "mcp-secret"\n'
        '\n[database]\nurl = "mysql://database-secret"\n'
        "\n[services]\nchat = true\nmcp = true\n"
    )
    frontend_operator.write_text(
        '[app]\nsite_name = "Frontend Cloud"\nlogo_light_path = "/frontend-light.png"\n'
        'public_api_base = "https://operator.example.com/api"\nsecret_key = "frontend-secret"\n'
        "\n[services]\nmanila = true\nk3s = false\n"
    )
    sources = {source: source.read_bytes() for source in (base, operator, frontend_operator)}

    assert (
        _RENDERER.main(
            str(base),
            str(operator),
            str(frontend_operator),
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
            "frontend_base_url": "https://native.example.com",
            "public_api_base": "https://operator.example.com/api",
        },
        "services": {"k3s": False, "chat": True, "mcp": True, "manila": True},
        "openstack": {"s3_endpoint": "https://s3.example.com"},
        "monitoring": {"grafana_base_url": "https://grafana.example.com"},
        "chat": {"base_url": "https://chat.example.com"},
        "mcp": {"public_url": "https://cloud.example.com/api/v1/mcp"},
    }
    assert "secret" not in destination.read_text()
    assert destination.stat().st_mode & 0o777 == 0o644
    original_output = destination.read_bytes()
    original_stat = destination.stat()
    assert (
        _RENDERER.main(
            str(base),
            str(operator),
            str(frontend_operator),
            str(destination),
        )
        is False
    )
    assert destination.read_bytes() == original_output
    assert destination.stat().st_ino == original_stat.st_ino
    assert destination.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert {source: source.read_bytes() for source in sources} == sources


def test_renderer_rejects_invalid_public_field_type(tmp_path: Path) -> None:
    base = tmp_path / "afterglow.conf"
    operator = tmp_path / "afterglow.operator.conf"
    destination = tmp_path / "afterglow.frontend.conf"
    base.write_text('[app]\nsite_name = "Afterglow"\n')
    operator.write_text('[services]\nchat = "yes"\n')

    with pytest.raises(TypeError, match=r"\[services\]\.chat must be bool"):
        _RENDERER.main(str(base), str(operator), str(destination))

    assert not destination.exists()


def test_public_projection_has_an_independent_closed_allowlist() -> None:
    # Keep this consumer contract independent of the renderer schema: adding a
    # backend setting must not automatically make it browser-visible.
    public = {
        "app": {
            "backend_port": 0,
            "site_name": "",
            "site_description": "Cloud",
            "logo_path": "/logo.svg",
            "logo_dark_path": "/dark.svg",
            "logo_light_path": "/light.svg",
            "favicon_path": "/favicon.svg",
            "refresh_interval_ms": 0,
            "frontend_base_url": "https://cloud.example.test",
            "public_api_base": "https://api.example.test",
        },
        "services": {
            "magnum": False,
            "manila": True,
            "zun": False,
            "k3s": False,
            "trove": True,
            "swift": False,
            "barbican": False,
            "waygate": True,
            "chat": False,
            "mcp": True,
        },
        "openstack": {"s3_endpoint": "https://s3.example.test"},
        "monitoring": {"grafana_base_url": "https://grafana.example.test"},
        "chat": {"base_url": "https://chat.example.test"},
        "mcp": {"public_url": "https://cloud.example.test/mcp"},
    }
    private = copy.deepcopy(public)
    for section in private.values():
        section.update(
            secret_key="private-secret",
            password="private-password",
            api_key="private-api-key",
            new_backend_option="not-public",
            credentials={"token": "private-token"},
        )
    private["services"]["lumen_internal_url"] = "https://private-lumen.example.test"
    private["services"]["future_service"] = True
    private.update(
        DEFAULT={"debug": True},
        database={"url": "mysql://private-database"},
        builder={"ssh_private_key": "private-key"},
        future_section={"site_name": "not-public"},
    )
    original = copy.deepcopy(private)

    projected = _RENDERER.project_public_config(private)

    assert projected == public
    assert tomllib.loads(_RENDERER.render_toml(projected)) == public
    assert private == original


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"app": {"backend_port": True}}, r"\[app\]\.backend_port must be int"),
        ({"app": {"refresh_interval_ms": False}}, r"\[app\]\.refresh_interval_ms must be int"),
        ({"app": {"site_name": []}}, r"\[app\]\.site_name must be str"),
        ({"services": {"chat": 0}}, r"\[services\]\.chat must be bool"),
        ({"app": "not-a-table"}, r"\[app\] must be a TOML table"),
    ],
)
def test_public_projection_rejects_type_coercion(config: dict, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        _RENDERER.project_public_config(config)


@pytest.mark.parametrize("invalid_layer", [0, 1, 2])
@pytest.mark.parametrize("existing_destination", [False, True])
def test_invalid_toml_does_not_replace_frontend_output(
    tmp_path: Path, invalid_layer: int, existing_destination: bool
) -> None:
    inputs = [tmp_path / name for name in ("native.conf", "operator.conf", "frontend-operator.conf")]
    for index, source in enumerate(inputs):
        source.write_text(f'[app]\nsite_name = "Layer {index}"\n', encoding="utf-8")
    inputs[invalid_layer].write_text("[services]\nchat = True\n", encoding="utf-8")
    sources = {source: source.read_bytes() for source in inputs}
    destination = tmp_path / "frontend.conf"
    if existing_destination:
        destination.write_bytes(b"# Last known good output\n[services]\nchat = false\n")
        destination.chmod(0o644)
        original = destination.read_bytes()
        original_stat = destination.stat()
    original_entries = set(tmp_path.iterdir())

    with pytest.raises(tomllib.TOMLDecodeError):
        _RENDERER.main(*(str(source) for source in inputs), str(destination))

    if existing_destination:
        assert destination.read_bytes() == original
        assert destination.stat().st_ino == original_stat.st_ino
        assert destination.stat().st_mtime_ns == original_stat.st_mtime_ns
        assert destination.stat().st_mode == original_stat.st_mode
    else:
        assert not destination.exists()
    assert {source: source.read_bytes() for source in inputs} == sources
    assert set(tmp_path.iterdir()) == original_entries


def test_frontend_override_removal_restores_backend_effective_value(tmp_path: Path) -> None:
    effective = tmp_path / "effective.conf"
    operator = tmp_path / "frontend-operator.conf"
    destination = tmp_path / "frontend.conf"
    effective.write_text('[app]\nsite_name = "Native Cloud"\n', encoding="utf-8")
    operator.write_text('[app]\nsite_name = "Frontend Cloud"\n', encoding="utf-8")
    assert _RENDERER.main(str(effective), str(operator), str(destination)) is True
    assert tomllib.loads(destination.read_text())["app"]["site_name"] == "Frontend Cloud"

    effective.write_text('[app]\nsite_name = "Regenerated Native Cloud"\n', encoding="utf-8")
    operator.write_text("# Override removed.\n", encoding="utf-8")

    assert _RENDERER.main(str(effective), str(operator), str(destination)) is True
    assert tomllib.loads(destination.read_text()) == {"app": {"site_name": "Regenerated Native Cloud"}}


def test_load_merged_uses_explicit_layer_order_without_rewriting_sources(tmp_path: Path) -> None:
    native = tmp_path / "native.conf"
    operator = tmp_path / "operator.conf"
    unrelated = tmp_path / "unrelated.conf"
    native.write_text(
        '# Native generation\n[app]\nsite_name = "Native Cloud"\nbackend_port = 8020\n'
        '[custom.nested]\nretained = "native"\nvalue = "native"\n',
        encoding="utf-8",
    )
    operator.write_text(
        '# Operator values win\n[app]\nsite_name = "Operator Cloud"\n[custom.nested]\nvalue = "operator"\n',
        encoding="utf-8",
    )
    unrelated.write_text('[app]\nsite_name = "Stale generated layer"\n', encoding="utf-8")
    sources = {source: source.read_bytes() for source in (native, operator, unrelated)}
    stats = {source: source.stat() for source in sources}

    assert _RENDERER.load_merged([native, operator]) == {
        "app": {"site_name": "Operator Cloud", "backend_port": 8020},
        "custom": {"nested": {"retained": "native", "value": "operator"}},
    }
    assert _RENDERER.load_merged([operator, native]) == tomllib.loads(native.read_text(encoding="utf-8"))
    assert {source: source.read_bytes() for source in sources} == sources
    for source in sources:
        assert source.stat().st_ino == stats[source].st_ino
        assert source.stat().st_mtime_ns == stats[source].st_mtime_ns
