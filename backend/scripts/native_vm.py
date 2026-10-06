#!/app/.venv/bin/python
"""Non-root native OCI-root entrypoint (no init system or container engine).

Image contract: /app/app, /app/scripts, API + worker /app/.venv,
/usr/local/bin/node, /app/frontend/{build,node_modules,package.json}, and
mariadbd, mariadb-install-db, redis-server on PATH with their runtime assets.
Run as appuser with persistent, owned /var/lib/afterglow and writable /app/logs.
/app/afterglow.conf may symlink to the private state's afterglow.conf; an
operator's existing configuration and overrides are never rewritten. Managed
datastore/origin settings use the application's supported environment layer.

SQL has no TCP listener; Redis is authenticated and loopback-only. Installation
is staged and marked only after success. Interrupted staging is preserved and
refused, not silently adopted or deleted. Keep the entire state directory,
including credentials.json, across restarts. Child output goes to private logs;
only service names and exit codes are printed here, never exception text/argv.
"""

import argparse
import asyncio
import fcntl
import json
import os
import pwd
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


class StartupError(RuntimeError):
    pass


class Stopped(RuntimeError):
    pass


class Supervisor:
    def __init__(self, log_dir: Path, shutdown_timeout: float = 4):
        self.log_dir = log_dir
        self.shutdown_timeout = shutdown_timeout
        self.children = []
        self.stopping = threading.Event()

    def signal(self, signum, _frame):
        self.stopping.set()

    def start(self, name, argv, cwd, env=None):
        self.check()
        with (self.log_dir / f"{name}.log").open("ab", buffering=0) as output:
            child = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                start_new_session=True,
            )
        self.children.append((name, child))
        return child

    def check(self):
        if self.stopping.is_set():
            raise Stopped()
        for name, child in self.children:
            code = child.poll()
            if code is not None:
                raise StartupError(f"{name} exited ({code})")

    def wait_ready(self, probe, timeout=60):
        deadline = time.monotonic() + timeout
        while True:
            self.check()
            if probe():
                self.check()
                return
            if time.monotonic() >= deadline:
                raise StartupError("service readiness timed out")
            self.stopping.wait(0.1)

    def run_once(self, name, argv, cwd, timeout=120):
        child = self.start(name, argv, cwd)
        deadline = time.monotonic() + timeout
        while child.poll() is None:
            if self.stopping.wait(0.1):
                raise Stopped()
            if time.monotonic() >= deadline:
                raise StartupError(f"{name} timed out")
        self.children.remove((name, child))
        child.wait()
        self._kill_group(child, signal.SIGKILL)
        if child.returncode:
            raise StartupError(f"{name} exited ({child.returncode})")
        self.check()

    def run(self):
        while True:
            self.check()
            self.stopping.wait(0.1)

    def shutdown(self):
        # Reserve datastore flush time within stage-1's five-second grace.
        consumers = [item for item in self.children if item[0] not in {"mariadb", "redis"}]
        stores = [item for item in self.children if item[0] in {"mariadb", "redis"}]
        deadline = time.monotonic() + self.shutdown_timeout
        for group in (consumers, stores):
            for _, child in reversed(group):
                self._kill_group(child, signal.SIGTERM)
            group_deadline = (
                min(deadline, time.monotonic() + self.shutdown_timeout / 2) if group is consumers else deadline
            )
            for _, child in reversed(group):
                try:
                    child.wait(timeout=max(0, group_deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
            # Also kill descendants whose session leader has already exited.
            for _, child in reversed(group):
                self._kill_group(child, signal.SIGKILL)
                child.wait()
        self.children.clear()

    @staticmethod
    def _kill_group(child, signum):
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass


def origin(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or any(c.isspace() for c in value)
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError()
    except ValueError:
        raise argparse.ArgumentTypeError("expected an HTTP(S) origin without credentials or a path") from None
    return f"{parsed.scheme}://{parsed.netloc}"


def private_write(path: Path, content: str):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def load_credentials(state: Path):
    path = state / "credentials.json"
    if path.exists():
        credentials = json.loads(path.read_text())
        for key in ("sql_root", "sql_app", "redis", "secret_key", "encryption_key"):
            value = credentials.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise StartupError("invalid persisted credentials")
        path.chmod(0o600)
        return credentials
    if any((state / name).exists() for name in ("mariadb", "mariadb.installing", "redis")):
        raise StartupError("datastore state exists without credentials; restore credentials before starting")
    credentials = {
        key: secrets.token_hex(32) for key in ("sql_root", "sql_app", "redis", "secret_key", "encryption_key")
    }
    private_write(path, json.dumps(credentials) + "\n")
    return credentials


def initialize_datadir(state: Path, supervisor: Supervisor):
    data = state / "mariadb"
    staging = state / "mariadb.installing"
    if staging.exists():
        raise StartupError("interrupted MariaDB installation; preserve and recover mariadb.installing before retrying")
    if data.exists():
        if not (data / ".installed").is_file() or not (data / "mysql").is_dir():
            raise StartupError("unmarked or incomplete MariaDB data directory; recovery required")
        return data
    staging.mkdir(mode=0o700)
    supervisor.run_once(
        "mariadb-install",
        [
            "mariadb-install-db",
            "--no-defaults",
            f"--datadir={staging}",
            "--auth-root-authentication-method=normal",
            "--skip-test-db",
            f"--user={pwd.getpwuid(os.getuid()).pw_name}",
        ],
        state,
    )
    if not (staging / "mysql").is_dir():
        raise StartupError("MariaDB installation did not create system tables")
    private_write(staging / ".installed", "installed\n")
    staging.rename(data)
    return data


def prepare_config(app_dir: Path, state: Path, credentials):
    path = app_dir / "afterglow.conf"
    target = path.resolve()
    if not target.exists():
        if target.parent != state.resolve() and target.parent != app_dir.resolve():
            raise StartupError("configuration symlink points outside supported directories")
        private_write(
            target,
            (
                "[app]\nsecret_key = "
                + json.dumps(credentials["secret_key"])
                + "\n[k3s]\nkubeconfig_encryption_key = "
                + json.dumps(credentials["encryption_key"])
                + "\n"
            ),
        )
    # Backend supported merge convention; frontend still sees the untouched base.
    from app.config import load_raw_toml

    load_raw_toml.cache_clear()
    return load_raw_toml()


def child_environment(credentials, sql_socket: Path, config, frontend_origin, api_origin, log_dir):
    environment = dict(os.environ)
    environment.update(
        {
            "DATABASE_URL": "mysql+aiomysql://afterglow:"
            + credentials["sql_app"]
            + "@localhost/afterglow?"
            + urlencode({"unix_socket": str(sql_socket)}),
            "REDIS_URL": "redis://:" + credentials["redis"] + "@127.0.0.1:6379/0",
            "SENTINEL_ENABLED": "false",
            "SENTINEL_HOSTS": "",
            "FRONTEND_BASE_URL": frontend_origin,
            "PUBLIC_API_BASE": api_origin,
            "CORS_ORIGINS": frontend_origin,
            "ORIGIN": frontend_origin,
            "HOST": "0.0.0.0",
            "PORT": "3080",
            "BACKEND_PORT": "8000",
            "FRONTEND_PORT": "3080",
            "LOG_DIRECTORY": str(log_dir),
        }
    )
    for key, section, field, fallback in (
        ("SECRET_KEY", "app", "secret_key", credentials["secret_key"]),
        ("K3S_KUBECONFIG_ENCRYPTION_KEY", "k3s", "kubeconfig_encryption_key", credentials["encryption_key"]),
    ):
        if key not in environment:
            environment[key] = config.get(section, {}).get(field) or fallback
    return environment


async def initialize_sql(sql_socket: Path, credentials, data: Path):
    import aiomysql

    marker = data / ".account-ready"
    try:
        connection = await aiomysql.connect(
            unix_socket=str(sql_socket), user="root", password=credentials["sql_root"], connect_timeout=2
        )
    except aiomysql.OperationalError as exc:
        if marker.exists() or exc.args[0] != 1045:
            raise
        connection = await aiomysql.connect(unix_socket=str(sql_socket), user="root", connect_timeout=2)
    try:
        if not marker.exists():
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT User, Host FROM mysql.user")
                accounts = await cursor.fetchall()
                for user, host in accounts:
                    if not user or (user == "root" and host != "localhost"):
                        await cursor.execute(
                            "DROP USER IF EXISTS " + connection.escape(user) + "@" + connection.escape(host)
                        )
                await cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (credentials["sql_root"],))
                await cursor.execute(
                    "CREATE DATABASE IF NOT EXISTS afterglow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                await cursor.execute(
                    "CREATE USER IF NOT EXISTS 'afterglow'@'localhost' IDENTIFIED BY %s", (credentials["sql_app"],)
                )
                await cursor.execute("ALTER USER 'afterglow'@'localhost' IDENTIFIED BY %s", (credentials["sql_app"],))
                await cursor.execute("GRANT ALL PRIVILEGES ON afterglow.* TO 'afterglow'@'localhost'")
    finally:
        await connection.ensure_closed()
    application = await aiomysql.connect(
        unix_socket=str(sql_socket),
        user="afterglow",
        password=credentials["sql_app"],
        db="afterglow",
        connect_timeout=2,
    )
    try:
        async with application.cursor() as cursor:
            await cursor.execute("SELECT 1")
            if await cursor.fetchone() != (1,):
                raise StartupError("application database verification failed")
    finally:
        await application.ensure_closed()
    private_write(marker, "ready\n")


def socket_ready(path):
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(0.2)
            client.connect(str(path))
            return bool(client.recv(1))
    except OSError:
        return False


def redis_ready(password):
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.2) as client:
            client.sendall(f"*2\r\n$4\r\nAUTH\r\n$64\r\n{password}\r\n*1\r\n$4\r\nPING\r\n".encode())
            reply = client.makefile("rb")
            return reply.readline() == b"+OK\r\n" and reply.readline() == b"+PONG\r\n"
    except OSError:
        return False


def http_ready(url):
    try:
        with urlopen(url, timeout=1) as response:
            return response.status == 200 and json.loads(response.read(8192)).get("status") == "ok"
    except (OSError, ValueError):
        return False


async def guarded_startup(supervisor, operation, timeout=120):
    task = asyncio.create_task(operation)
    deadline = time.monotonic() + timeout
    try:
        while not task.done():
            supervisor.check()
            if time.monotonic() >= deadline:
                raise StartupError("database startup timed out")
            await asyncio.wait({task}, timeout=0.1)
        supervisor.check()
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def create_schema():
    from app.config import get_settings
    from app.database import close_db, create_tables, init_db

    get_settings.cache_clear()
    settings = get_settings()
    init_db(settings.database_url)
    try:
        await create_tables()
    finally:
        await close_db()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-origin", type=origin, default="http://localhost:3080")
    parser.add_argument("--api-origin", type=origin, default="http://localhost:8000")
    args = parser.parse_args(argv)
    if os.getuid() == 0:
        print("native supervisor: run as the image's non-root appuser", file=sys.stderr)
        return 1
    os.umask(0o077)
    state = Path("/var/lib/afterglow")
    app_dir = Path("/app")
    supervisor = None
    lock = None
    old_handlers = {}
    try:
        state.mkdir(mode=0o700, exist_ok=True)
        state.chmod(0o700)
        lock = (state / "supervisor.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logs = state / "logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        supervisor = Supervisor(logs)
        for sig in (signal.SIGTERM, signal.SIGINT):
            old_handlers[sig] = signal.signal(sig, supervisor.signal)
        os.chdir(app_dir)
        sys.path.insert(0, str(app_dir))
        credentials = load_credentials(state)
        config = prepare_config(app_dir, state, credentials)
        data = initialize_datadir(state, supervisor)
        runtime = state / "run"
        runtime.mkdir(mode=0o700, exist_ok=True)
        sql_socket = runtime / "mysql.sock"
        sql_socket.unlink(missing_ok=True)
        supervisor.start(
            "mariadb",
            [
                "mariadbd",
                "--no-defaults",
                f"--datadir={data}",
                f"--socket={sql_socket}",
                f"--pid-file={runtime / 'mysql.pid'}",
                f"--tmpdir={runtime}",
                "--skip-networking",
                "--skip-name-resolve",
                "--innodb-use-native-aio=0",
                "--general-log=0",
                "--slow-query-log=0",
            ],
            state,
        )
        supervisor.wait_ready(lambda: socket_ready(sql_socket))
        asyncio.run(guarded_startup(supervisor, initialize_sql(sql_socket, credentials, data)))
        supervisor.check()
        redis_dir = state / "redis"
        redis_dir.mkdir(mode=0o700, exist_ok=True)
        redis_config = runtime / "redis.conf"
        private_write(
            redis_config,
            (
                "bind 127.0.0.1\nprotected-mode yes\nport 6379\ndaemonize no\n"
                f"dir {json.dumps(str(redis_dir))}\nappendonly yes\nappendfsync everysec\n"
                f'requirepass {credentials["redis"]}\nlogfile ""\n'
            ),
        )
        supervisor.start("redis", ["redis-server", str(redis_config)], state)
        supervisor.wait_ready(lambda: redis_ready(credentials["redis"]))
        environment = child_environment(credentials, sql_socket, config, args.frontend_origin, args.api_origin, logs)
        os.environ.update(environment)
        asyncio.run(guarded_startup(supervisor, create_schema()))
        supervisor.check()
        supervisor.start(
            "backend",
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
            app_dir,
            environment,
        )
        supervisor.start("worker", [sys.executable, "-m", "app.notion_worker"], app_dir, environment)
        supervisor.start("frontend", ["/usr/local/bin/node", "build"], app_dir / "frontend", environment)
        supervisor.wait_ready(
            lambda: http_ready("http://127.0.0.1:8000/api/v1/health") and http_ready("http://127.0.0.1:3080/health")
        )
        print("native supervisor: API and frontend ready; database and cache initialized", flush=True)
        supervisor.run()
    except Stopped:
        return 0
    except StartupError as exc:
        print(f"native supervisor: {exc}", file=sys.stderr, flush=True)
        return 1
    except Exception:
        print("native supervisor: startup failed; inspect private service logs/state", file=sys.stderr, flush=True)
        return 1
    finally:
        if supervisor is not None:
            supervisor.shutdown()
        for sig, previous in old_handlers.items():
            signal.signal(sig, previous)
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
