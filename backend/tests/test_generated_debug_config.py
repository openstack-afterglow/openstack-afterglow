"""Consumer regressions for generated DEFAULT.debug, without runtime settings imports."""

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config2helm  # noqa: E402
import generate_k8s  # noqa: E402


def _load_generator(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load_generator("afterglow_setup_generator", "setup.py")
KOLLA_FILES = "deploy/kolla/ansible/roles/afterglow/files/"
SANITIZER = _load_generator("debug_operator_sanitizer", KOLLA_FILES + "sanitize_operator_config.py")
FRONTEND = _load_generator("debug_frontend_projection", KOLLA_FILES + "render_frontend_config.py")


@pytest.mark.parametrize("defaults", [None, {}, {"debug": False}, {"debug": True}])
def test_k8s_configmap_preserves_debug_and_explicit_logging(defaults):
    cfg = {"logging": {"log_level": "WARNING"}}
    if defaults is not None:
        cfg["DEFAULT"] = defaults

    configmap = yaml.safe_load(generate_k8s.render_configmap(cfg))
    parsed = tomllib.loads(configmap["data"]["afterglow.conf"])

    assert parsed["DEFAULT"]["debug"] is bool(defaults and defaults.get("debug"))
    assert parsed["logging"]["log_level"] == "WARNING"


@pytest.mark.parametrize("defaults", [None, {}, {"debug": False}, {"debug": True}])
@pytest.mark.parametrize("include_secrets", [False, True])
def test_helm_values_conversion_preserves_debug_and_logging(defaults, include_secrets):
    cfg = {"logging": {"log_level": "WARNING"}}
    if defaults is not None:
        cfg["DEFAULT"] = defaults

    values = yaml.safe_load(config2helm.render_yaml(config2helm.convert(cfg, include_secrets)))

    assert values["debug"] is bool(defaults and defaults.get("debug"))
    assert values["logging"]["logLevel"] == "WARNING"


@pytest.mark.parametrize("debug", [None, False, True])
@pytest.mark.parametrize(
    "logging_config",
    [None, {"log_level": "WARNING", "log_directory": "/app/logs/custom", "max_bytes": 10485760}],
)
def test_helm_chart_renders_converted_and_legacy_values(tmp_path, debug, logging_config):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the actual ConfigMap template")

    cfg = {} if logging_config is None else {"logging": logging_config}
    if debug is not None:
        cfg["DEFAULT"] = {"debug": debug}
    values = config2helm.convert(cfg, False)
    if debug is None:
        values.pop("debug")  # Older values files do not declare DEFAULT.debug.
    values_path = tmp_path / "values.yaml"
    values_path.write_text(config2helm.render_yaml(values), encoding="utf-8")
    rendered = subprocess.run(
        [
            helm,
            "template",
            "afterglow",
            str(ROOT / "helm/afterglow"),
            "--show-only",
            "templates/configmap.yaml",
            "-f",
            str(values_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    configmap = yaml.safe_load(rendered.stdout)
    parsed = tomllib.loads(configmap["data"]["afterglow.conf"])

    assert parsed["DEFAULT"]["debug"] is (debug is True)
    assert parsed["logging"] == (
        logging_config
        if logging_config is not None
        else {"log_directory": "logs", "log_level": "INFO", "max_bytes": 52428800}
    )


@pytest.mark.parametrize("debug", [None, False, True])
@pytest.mark.parametrize("for_k8s", [False, True])
def test_setup_generates_debug_for_compose_and_k8s(debug, for_k8s):
    with (ROOT / "afterglow.conf.example").open("rb") as handle:
        cfg = tomllib.load(handle)
    cfg.pop("DEFAULT")
    if debug is not None:
        cfg["DEFAULT"] = {"debug": debug}
    # The wizard groups Manila fields separately and stores GPU devices as a list.
    cfg["manila_ceph"] = {
        "manila_endpoint": "",
        "manila_share_network_id": "",
        "manila_share_type": "cephfs",
        "manila_nfs_share_type": "nfstype",
        "ceph_monitors": "",
    }
    cfg["gpu_devices"] = []
    cfg["session"]["warning_before_seconds"] = 300
    cfg["nova"].update(default_network_id="", default_availability_zone="nova")
    cfg["openstack"].update(insecure=False, cacert="")

    if for_k8s:
        configmap = yaml.safe_load(SETUP.render_k8s_configmap(cfg))
        generated = configmap["data"]["afterglow.conf"]
    else:
        generated = SETUP.render_config_toml(cfg)
    parsed = tomllib.loads(generated)

    assert parsed["DEFAULT"]["debug"] is (debug is True)
    if for_k8s:
        assert "password" not in parsed["openstack"]
        assert "secret_key" not in parsed["app"]


@pytest.mark.parametrize("loader", [generate_k8s.load_config, config2helm.load_config])
def test_generators_merge_debug_overrides(tmp_path, loader):
    base = tmp_path / "afterglow.conf"
    base.write_text("[DEFAULT]\ndebug = true\n", encoding="utf-8")
    (tmp_path / "afterglow.operator.conf").write_text("[DEFAULT]\ndebug = false\n", encoding="utf-8")

    assert loader(base)["DEFAULT"]["debug"] is False


@pytest.mark.parametrize("literal", ["True", "False"])
@pytest.mark.parametrize("loader", [generate_k8s.load_config, config2helm.load_config])
def test_generators_reject_capitalized_toml_without_rewriting(tmp_path, literal, loader):
    source = tmp_path / "afterglow.conf"
    original = f"[DEFAULT]\ndebug = {literal}\n"
    source.write_text(original, encoding="utf-8")

    with pytest.raises(tomllib.TOMLDecodeError):
        loader(source)

    assert source.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("debug", [False, True])
def test_operator_sanitizer_preserves_debug_but_frontend_omits_it(tmp_path, debug):
    source = tmp_path / "afterglow.conf"
    sanitized = tmp_path / "afterglow.operator.conf"
    original = f"[DEFAULT]\ndebug = {'true' if debug else 'false'}\n"
    source.write_text(original, encoding="utf-8")

    SANITIZER.main(str(source), str(sanitized))
    assert sanitized.read_text(encoding="utf-8") == original
    parsed = FRONTEND.load_merged([sanitized])
    assert parsed["DEFAULT"]["debug"] is debug
    public = tomllib.loads(FRONTEND.render_toml(FRONTEND.project_public_config(parsed)))
    assert "DEFAULT" not in public


@pytest.mark.parametrize("literal", ["True", "False"])
def test_operator_sanitizer_rejects_invalid_boolean_without_writing(tmp_path, literal):
    source = tmp_path / "afterglow.conf"
    destination = tmp_path / "afterglow.operator.conf"
    original = f"[DEFAULT]\ndebug = {literal}\n"
    source.write_text(original, encoding="utf-8")

    with pytest.raises(tomllib.TOMLDecodeError):
        SANITIZER.main(str(source), str(destination))

    assert source.read_text(encoding="utf-8") == original
    assert not destination.exists()
