import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.common import lumen_installers
from app.config import Settings
from app.services.site_branding import configured_public_site_config


def _client(base_url: str) -> TestClient:
    settings = Settings(service_lumen_external_url=base_url)
    app = FastAPI()
    app.include_router(lumen_installers.build_lumen_installer_router(settings.service_lumen_external_url))
    return TestClient(app)


@pytest.mark.parametrize("filename", ["lumen.sh", "lumen.ps1"])
def test_public_installer_is_rendered_at_startup(filename, monkeypatch):
    base = "https://lumen.example:8443/service"
    client = _client(base + "///")

    def unexpected_render(*args):
        pytest.fail("the installer must already be rendered before the first request")

    monkeypatch.setattr(lumen_installers, "_render_installer", unexpected_render)
    path = f"/install/{filename}"
    response = client.get(path, headers={"Host": "other.example"}, params={"url": "https://ignored.example"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    etag = f'"{sha256(response.content).hexdigest()}"'
    assert response.headers["etag"] == etag
    assert f"'{base}/v1'" in response.text
    assert f"'{base}'" in response.text
    for forbidden in (
        "__LUMEN_",
        "other.example",
        "ignored.example",
        "sys.argv",
        "LUMEN_CODEX_BASE_URL",
        "LUMEN_ANTHROPIC_BASE_URL",
    ):
        assert forbidden not in response.text
    unchanged = client.get(path, headers={"If-None-Match": f'"older", W/{etag}'})
    assert unchanged.status_code == 304
    assert unchanged.headers["etag"] == etag
    assert unchanged.headers["cache-control"] == "no-cache"
    assert unchanged.content == b""
    assert client.get(path, headers={"If-None-Match": '"older"'}).content == response.content
    assert client.head(path).headers["etag"] == etag
    assert client.get(path + ".template").status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "//lumen.example",
        "http://lumen.example",
        "https://user:password@lumen.example",
        "https://lumen.example/path?",
        "https://lumen.example/path#",
        "https://lumen.example/path?a=b",
        "https://lumen.example/path#fragment",
        "https://lumen.example/'quoted'",
        'https://lumen.example/"quoted"',
        "https://lumen.example/\u2019",
        "https://lumen.example/\n",
        "https://lumen.example/%0a",
        "https://lumen.example/\\path",
        "https://lumen.example:65536",
        "https://lumen.example:",
        "https://lumen.example:0",
        "https://bad_host",
        "https://-badhost.example",
        "https://[not-an-ip]",
    ],
)
def test_invalid_public_lumen_url_fails_validation(url):
    with pytest.raises(ValidationError, match="lumen_external_url must be an absolute HTTPS URL") as failure:
        Settings(service_lumen_external_url=url)
    assert url not in str(failure.value)


@pytest.mark.parametrize("url", ["http://localhost:8012/", "http://127.0.0.1:8012/", "http://[::1]:8012/"])
def test_http_loopback_only_in_development(url, monkeypatch):
    monkeypatch.setenv("AFTERGLOW_ENV", "development")
    assert Settings(service_lumen_external_url=url).service_lumen_external_url == url.rstrip("/")
    monkeypatch.setenv("AFTERGLOW_ENV", "production")
    with pytest.raises(ValidationError, match="HTTP is permitted on development loopback only"):
        Settings(service_lumen_external_url=url)


def test_posix_installer_syntax_and_preflight_without_terminal(tmp_path):
    script = _client("https://lumen.example").get("/install/lumen.sh").content
    env = {"HOME": str(tmp_path), "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.defpath}"}
    subprocess.run(["sh", "-n"], input=script, check=True, env=env, timeout=5)
    run = subprocess.run(["sh"], input=script, capture_output=True, env=env, start_new_session=True, timeout=5)
    assert run.returncode == 1
    assert b"terminal" in run.stderr.lower()
    assert not any(tmp_path.iterdir())


def test_unconfigured_scripts_fail_without_using_inputs(tmp_path):
    client = _client("")
    posix = client.get("/install/lumen.sh")
    windows = client.get("/install/lumen.ps1")
    for response in (posix, windows):
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert "this deployment has no public Lumen URL" in response.text
        assert "https://" not in response.text
    assert "exit 1" in posix.text
    assert windows.text.startswith("throw ")
    run = subprocess.run(["sh"], input=posix.content, capture_output=True, env={"HOME": str(tmp_path)}, timeout=5)
    assert run.returncode == 1
    assert b"no public Lumen URL" in run.stderr
    assert not any(tmp_path.iterdir())


def test_unconfigured_powershell_fails_without_closing_the_session(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell runtime unavailable")
    script = tmp_path / "lumen.ps1"
    script.write_bytes(_client("").get("/install/lumen.ps1").content)
    command = [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive"]
    run = subprocess.run([*command, "-File", str(script)], capture_output=True, timeout=10)
    assert run.returncode == 1
    assert b"no public Lumen URL" in run.stderr
    caught = subprocess.run(
        [
            *command,
            "-Command",
            "try { Get-Content -Raw -LiteralPath $env:INSTALLER | Invoke-Expression } "
            "catch { [Console]::WriteLine($_.Exception.Message) }; [Console]::WriteLine('session-alive')",
        ],
        env={**os.environ, "INSTALLER": str(script)},
        capture_output=True,
        timeout=10,
    )
    assert caught.returncode == 0
    assert b"no public Lumen URL" in caught.stdout
    assert b"session-alive" in caught.stdout


def test_public_site_config_reports_installer_availability_without_url():
    base_url = "https://lumen.example"
    assert configured_public_site_config(Settings(service_lumen_external_url=""))["lumen_installer_configured"] is False
    configured = configured_public_site_config(Settings(service_lumen_external_url=base_url))
    assert configured["lumen_installer_configured"] is True
    assert base_url not in str(configured)
