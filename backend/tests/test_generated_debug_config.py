"""Consumer regressions for generated DEFAULT.debug, without runtime settings imports."""

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
