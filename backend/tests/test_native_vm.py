"""Native supervisor boundaries; no application startup or OpenStack access."""

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "native_vm.py"
_SPEC = importlib.util.spec_from_file_location("native_vm", _PATH)
assert _SPEC and _SPEC.loader
native = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(native)


def test_credentials_persist_and_missing_credentials_do_not_replace_data(tmp_path):
    original = native.load_credentials(tmp_path)
    assert native.load_credentials(tmp_path) == original
    assert (tmp_path / "credentials.json").stat().st_mode & 0o777 == 0o600
    data = tmp_path / "mariadb"
    data.mkdir()
    record = data / "user-data"
    record.write_bytes(b"retained")
    (tmp_path / "credentials.json").unlink()
    with pytest.raises(native.StartupError, match="without credentials"):
        native.load_credentials(tmp_path)
    assert record.read_bytes() == b"retained"
    assert not (tmp_path / "credentials.json").exists()


@pytest.mark.parametrize("partial", ["mariadb", "mariadb.installing"])
def test_partial_system_tables_are_not_adopted(tmp_path, partial):
    data = tmp_path / partial
    (data / "mysql").mkdir(parents=True)
    record = data / "mysql" / "partial"
    record.write_bytes(b"unfinished")
    supervisor = native.Supervisor(tmp_path)
    with pytest.raises(native.StartupError, match="interrupted|incomplete"):
        native.initialize_datadir(tmp_path, supervisor)
    assert record.read_bytes() == b"unfinished"
    assert not supervisor.children


def test_failed_installer_keeps_partial_state_and_refuses_retry(tmp_path, monkeypatch):
    installer = tmp_path / "mariadb-install-db"
    installer.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys\n"
        "directory = pathlib.Path(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--datadir=')))\n"
        "(directory / 'mysql').mkdir()\n"
        "sys.exit(7)\n"
    )
    installer.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    supervisor = native.Supervisor(tmp_path)
    try:
        with pytest.raises(native.StartupError, match=r"exited \(7\)"):
            native.initialize_datadir(tmp_path, supervisor)
        with pytest.raises(native.StartupError, match="interrupted"):
            native.initialize_datadir(tmp_path, supervisor)
        assert not (tmp_path / "mariadb").exists()
        assert not (tmp_path / "mariadb.installing" / ".installed").exists()
    finally:
        supervisor.shutdown()


def test_operator_config_and_auth_survive_managed_datastore_override(tmp_path, monkeypatch):
    from app import config

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    original = (
        '[app]\nsite_name = "Operator dashboard"\nsecret_key = "' + "a" * 64 + '"\n'
        '[openstack]\nauth_url = "https://identity.invalid/v3"\nusername = "operator"\n'
        '[k3s]\nkubeconfig_encryption_key = "' + "b" * 64 + '"\n'
        "[cache]\nsentinel_enabled = true\n"
    ).encode()
    canonical = state / "afterglow.conf"
    canonical.write_bytes(original)
    (app_dir / "afterglow.conf").symlink_to(canonical)
    override = app_dir / "afterglow.site.conf"
    override.write_text('[app]\nsite_description = "Preserved override"\n')
    monkeypatch.setattr(config, "_config_candidates", lambda: [app_dir / "afterglow.conf"])
    for key in ("SECRET_KEY", "K3S_KUBECONFIG_ENCRYPTION_KEY"):
        monkeypatch.delenv(key, raising=False)
    try:
        credentials = native.load_credentials(state)
        loaded = native.prepare_config(app_dir, state, credentials)
        environment = native.child_environment(
            credentials,
            state / "mysql.sock",
            loaded,
            "https://dashboard.invalid",
            "https://api.invalid",
            state,
        )
        assert canonical.read_bytes() == original
        assert loaded["app"]["site_description"] == "Preserved override"
        assert environment["SECRET_KEY"] == "a" * 64
        assert environment["K3S_KUBECONFIG_ENCRYPTION_KEY"] == "b" * 64
        assert loaded["openstack"]["username"] == "operator"
        assert environment["SENTINEL_ENABLED"] == "false"
        assert environment["PUBLIC_API_BASE"] == "https://api.invalid"
        assert environment["ORIGIN"] == "https://dashboard.invalid"
    finally:
        config.load_raw_toml.cache_clear()


@pytest.mark.parametrize(
    "value",
    [
        "https://user:password@example.invalid",
        "https://example.invalid/path",
        "https://example.invalid?token=secret",
        "https://example.invalid#fragment",
        "file:///tmp/dashboard",
        "http://example.invalid:0",
        "http://example.invalid:99999",
    ],
)
def test_forwarded_browser_origin_rejects_unsafe_values_without_echoing(value):
    with pytest.raises(argparse.ArgumentTypeError) as failure:
        native.origin(value)
    assert value not in str(failure.value)


def test_child_exit_even_zero_is_a_service_failure_and_other_children_are_reaped(tmp_path):
    supervisor = native.Supervisor(tmp_path, shutdown_timeout=0.2)
    sibling = supervisor.start("sibling", [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path)
    supervisor.start("failed", [sys.executable, "-c", "raise SystemExit(0)"], tmp_path)
    try:
        with pytest.raises(native.StartupError, match=r"failed exited \(0\)"):
            supervisor.wait_ready(lambda: False, timeout=5)
    finally:
        supervisor.shutdown()
    assert sibling.returncode == -signal.SIGTERM
    assert not supervisor.children


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
def test_real_signal_stops_graceful_and_stubborn_children(tmp_path, stop_signal):
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "import pathlib, signal, sys, time\n"
        "name = sys.argv[1]\n"
        "def stopped(*args):\n"
        "    pathlib.Path(name + '.stopped').write_text('graceful')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stopped if name == 'graceful' else signal.SIG_IGN)\n"
        "pathlib.Path(name + '.ready').write_text('ready')\n"
        "while True: time.sleep(1)\n"
    )
    harness = (
        "import importlib.util, json, pathlib, signal, sys\n"
        f"spec = importlib.util.spec_from_file_location('native_vm', {_PATH.as_posix()!r})\n"
        "native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)\n"
        "supervisor = native.Supervisor(pathlib.Path.cwd(), shutdown_timeout=0.2)\n"
        "signal.signal(signal.SIGTERM, supervisor.signal); signal.signal(signal.SIGINT, supervisor.signal)\n"
        "children = [supervisor.start(name, [sys.executable, 'child.py', name], pathlib.Path.cwd()) for name in ('graceful', 'stubborn')]\n"
        "try:\n"
        "    supervisor.wait_ready(lambda: all(pathlib.Path(name + '.ready').exists() for name in ('graceful', 'stubborn')), timeout=5)\n"
        "    pathlib.Path('supervisor.ready').write_text('ready')\n"
        "    supervisor.run()\n"
        "except native.Stopped: pass\n"
        "finally: supervisor.shutdown()\n"
        "print(json.dumps([child.returncode for child in children]))\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", harness], cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "supervisor.ready").exists():
            if parent.poll() is not None or time.monotonic() > deadline:
                raise AssertionError("supervisor failed to become ready")
            time.sleep(0.01)
        os.kill(parent.pid, stop_signal)
        output, errors = parent.communicate(timeout=5)
        assert parent.returncode == 0, errors
        assert json.loads(output) == [0, -signal.SIGKILL]
        assert (tmp_path / "graceful.stopped").read_text() == "graceful"
        assert not (tmp_path / "stubborn.stopped").exists()
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.communicate(timeout=5)


@pytest.mark.parametrize("bootstrap_fails", [False, True])
def test_native_boot_runs_canonical_bootstrap_before_writers_and_fails_closed(
    tmp_path, monkeypatch, capsys, bootstrap_fails
):
    from app import config, database
    from scripts import bootstrap_schema

    state = tmp_path / "state"
    app_dir = tmp_path / "app"
    state.mkdir()
    app_dir.mkdir()
    credentials = native.load_credentials(state)
    data = state / "mariadb"
    (data / "mysql").mkdir(parents=True)
    (data / ".installed").write_text("installed\n")
    retained = data / "operator-data"
    retained.write_bytes(b"preserve existing rows")
    original_config = (
        '[app]\nsite_name = "Native operator"\nsecret_key = "' + "a" * 64 + '"\n'
        '[k3s]\nkubeconfig_encryption_key = "' + "b" * 64 + '"\n'
    ).encode()
    canonical = state / "afterglow.conf"
    canonical.write_bytes(original_config)
    (app_dir / "afterglow.conf").symlink_to(canonical)
    events = []
    expected_url = native.child_environment(
        credentials, state / "run" / "mysql.sock", {}, "http://localhost:3080", "http://localhost:8000", state / "logs"
    )["DATABASE_URL"]

    class BootSupervisor:
        def __init__(self, log_dir):
            assert log_dir == state / "logs"

        def signal(self, *_args):
            pass

        def start(self, name, argv, cwd, env=None):
            events.append(name)
            if name in {"backend", "worker", "frontend"}:
                assert events.index("schema") < events.index(name)
                assert env["DATABASE_URL"] == expected_url
                assert env["SECRET_KEY"] == "a" * 64

        def check(self):
            pass

        def wait_ready(self, probe):
            pass

        def run(self):
            raise native.Stopped()

        def shutdown(self):
            events.append("shutdown")

    async def bootstrap(url):
        assert url == expected_url
        assert events == ["mariadb", "redis"]
        events.append("schema")
        if bootstrap_fails:
            raise bootstrap_schema.MigrationLedgerError("private migration failure details")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(native.os, "environ", dict(os.environ))
    monkeypatch.setattr(native.os, "getuid", lambda: 1000)
    monkeypatch.setattr(native, "Path", lambda value: {"/app": app_dir, "/var/lib/afterglow": state}[value])
    monkeypatch.setattr(native, "Supervisor", BootSupervisor)
    monkeypatch.setattr(native, "initialize_sql", AsyncMock())
    monkeypatch.setattr(config, "_config_candidates", lambda: [app_dir / "afterglow.conf"])
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("K3S_KUBECONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "mysql+aiomysql://stale:stale@localhost/stale")
    legacy = AsyncMock(side_effect=AssertionError("legacy create_tables must not run"))
    monkeypatch.setattr(database, "create_tables", legacy)
    canonical_bootstrap = AsyncMock(side_effect=bootstrap)
    monkeypatch.setattr(bootstrap_schema, "bootstrap_database", canonical_bootstrap)
    config.get_settings.cache_clear()
    previous_umask = os.umask(0o077)
    try:
        assert config.get_settings().database_url != expected_url
        assert native.main([]) == (1 if bootstrap_fails else 0)
        canonical_bootstrap.assert_awaited_once_with(expected_url)
        legacy.assert_not_awaited()
        assert events == (
            ["mariadb", "redis", "schema", "shutdown"]
            if bootstrap_fails
            else ["mariadb", "redis", "schema", "backend", "worker", "frontend", "shutdown"]
        )
        assert canonical.read_bytes() == original_config
        assert retained.read_bytes() == b"preserve existing rows"
        assert native.load_credentials(state) == credentials
        output = capsys.readouterr()
        assert "private migration failure details" not in output.err
        if bootstrap_fails:
            assert "startup failed" in output.err
            assert "API and frontend ready" not in output.out
    finally:
        os.umask(previous_umask)
        config.get_settings.cache_clear()
        config.load_raw_toml.cache_clear()


@pytest.mark.parametrize("damage", [None, "manifest", "missing_sql108", "changed_sql108"])
def test_native_image_packages_complete_canonical_migrations(tmp_path, damage):
    repository = _PATH.parents[2]
    dockerfile = (repository / "Dockerfile").read_text()
    backend_stage = dockerfile.split("FROM backend-runtime AS backend\n", 1)[1].split("\nFROM ", 1)[0]
    native_stage = dockerfile.split("FROM native-runtime AS native-vm\n", 1)[1].split("\nFROM ", 1)[0]
    # Both edges matter: native-vm inherits these bytes from the backend image,
    # not the checkout or a host-mounted migrations directory.
    for name in ("scripts", "migrations"):
        assert f"COPY --chown=appuser:appuser backend/{name}/ ./{name}/" in backend_stage
        assert f"COPY --from=backend --chown=appuser:appuser /app/{name} /app/{name}" in native_stage
        shutil.copytree(repository / "backend" / name, tmp_path / name)
    assert 'ENTRYPOINT ["/app/.venv/bin/python", "/app/scripts/native_vm.py"]' in native_stage
    migrations = tmp_path / "migrations"
    if damage == "manifest":
        (migrations / "manifest.txt").unlink()
    elif damage == "missing_sql108":
        (migrations / "108_instance_usage_governance.sql").unlink()
    elif damage == "changed_sql108":
        with (migrations / "108_instance_usage_governance.sql").open("a") as handle:
            handle.write("\n-- checksum drift\n")
    environment = dict(os.environ, PYTHONPATH=str(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json\n"
            "from scripts.baseline_migrations import MIGRATIONS, load_manifest\n"
            "from scripts.bootstrap_schema import load_sql106, load_sql107, load_sql108\n"
            "print(json.dumps({'directory': str(MIGRATIONS), 'ids': [m.logical_id for m in load_manifest()], "
            "'sql106': len(load_sql106()), 'sql107': len(load_sql107()), 'sql108': load_sql108()}))\n",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if damage:
        assert result.returncode != 0
        assert "MigrationLedgerError" in result.stderr
        assert not result.stdout
    else:
        assert result.returncode == 0, result.stderr
        packaged = json.loads(result.stdout)
        assert Path(packaged["directory"]) == migrations
        assert {"106-mcp-oauth-ongoing", "107-experience-events", "108-instance-usage-governance"} <= set(
            packaged["ids"]
        )
        assert packaged["sql106"] > 0
        assert packaged["sql107"] == 6
        assert len(packaged["sql108"]) == 2
        assert {statement.split("(", 1)[0].strip() for statement in packaged["sql108"]} == {
            "CREATE TABLE IF NOT EXISTS instance_usage_policies",
            "CREATE TABLE IF NOT EXISTS instance_usage_extension_requests",
        }
