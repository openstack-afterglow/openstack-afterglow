"""Command-aware retries over real loopback RESP and Sentinel connections."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ReadOnlyError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.services.cache import redis_backend

_READONLY = "-READONLY You can't write against a read only replica.\r\n"


def _resp(value):
    if isinstance(value, list):
        return f"*{len(value)}\r\n" + "".join(_resp(item) for item in value)
    value = str(value)
    return f"${len(value.encode())}\r\n{value}\r\n"


class _Server:
    """Minimal RESP server; scripts simulate commit-before-reply failures."""

    def __init__(self, script):
        self.script = script
        self.commands: list[list[str]] = []
        self.connections = 0
        self.handshakes: list[list[str]] = []
        self.writers = set()
        self.tasks = set()

    async def handle(self, reader, writer):
        self.connections += 1
        self.writers.add(writer)
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            while True:
                header = await reader.readline()
                if not header:
                    return
                args = []
                for _ in range(int(header[1:])):
                    size = int((await reader.readline())[1:])
                    args.append((await reader.readexactly(size + 2))[:-2].decode())
                if args and args[0].upper() in {"PING", "CLIENT", "AUTH", "SELECT"}:
                    self.handshakes.append(args)
                    writer.write(b"+PONG\r\n" if args[0].upper() == "PING" else b"+OK\r\n")
                    await writer.drain()
                    continue
                self.commands.append(args)
                reply = self.script(args, len(self.commands))
                if reply is None:
                    return
                if reply == "hang":
                    # The client's read timeout closes its socket. Do not leave
                    # an artificial long-lived sleeper behind after the test.
                    await reader.read()
                    return
                writer.write(reply.encode())
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            return
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            self.writers.discard(writer)
            self.tasks.discard(task)


@pytest.fixture
async def resp_servers():
    servers = []
    clients = []

    async def start(script):
        server = _Server(script)
        listener = await asyncio.start_server(server.handle, "127.0.0.1", 0)
        server.port = listener.sockets[0].getsockname()[1]
        servers.append((server, listener))
        return server

    yield start, clients
    for client in clients:
        await client.close()
        # Sentinel's master_for does not own its connection pool in redis-py5.
        await client.connection_pool.disconnect()
    for server, listener in servers:
        listener.close()
        await listener.wait_closed()
        for writer in tuple(server.writers):
            writer.close()
    for server, _ in servers:
        if server.tasks:
            await asyncio.gather(*tuple(server.tasks), return_exceptions=True)


def _master_reply(port):
    return _resp([["name", "kolla", "ip", "127.0.0.1", "port", port, "flags", "master", "num-other-sentinels", "0"]])


async def _sentinel_backend(start, clients, monkeypatch, master, *, redis_url="redis://127.0.0.1:1/0"):
    def discovery(args, n):
        assert args == ["SENTINEL", "MASTERS"]
        return _master_reply(master.port)

    sentinel = await start(discovery)
    settings = SimpleNamespace(
        sentinel_enabled=True,
        redis_url=redis_url,
        sentinel_hosts=f"127.0.0.1:{sentinel.port}",
        sentinel_master_name="kolla",
    )
    monkeypatch.setattr(redis_backend, "get_settings", lambda: settings)
    backend = redis_backend.RedisBackend()
    client = backend.raw_client()
    clients.append(client)
    clients.extend(client.connection_pool.sentinel_manager.sentinels)
    return backend, sentinel


@pytest.fixture(params=[False, True], ids=["direct", "sentinel"])
async def valkey(resp_servers, monkeypatch, request):
    start, clients = resp_servers

    async def build(script, *, socket_timeout=None, query=""):
        server = await start(script)
        if request.param:
            backend, _ = await _sentinel_backend(start, clients, monkeypatch, server)
        else:
            settings = SimpleNamespace(sentinel_enabled=False, redis_url=f"redis://127.0.0.1:{server.port}/0{query}")
            monkeypatch.setattr(redis_backend, "get_settings", lambda: settings)
            backend = redis_backend.RedisBackend()
            clients.append(backend.raw_client())
        if socket_timeout is not None:
            # Set before the pool has created any connections; retry policy is
            # never changed during a command (including concurrent commands).
            backend.raw_client().connection_pool.connection_kwargs["socket_timeout"] = socket_timeout
        return server, backend

    return build


@pytest.mark.parametrize(
    ("command", "reply", "expected"),
    [
        (("GET", "k"), _resp("v"), "v"),
        ((b"GET", "k"), _resp("v"), "v"),
        (("MGET", "k", "other"), _resp(["v", "w"]), ["v", "w"]),
        (("EXISTS", "k"), ":1\r\n", 1),
        (("TTL", "k"), ":15\r\n", 15),
        (("PTTL", "k"), ":15000\r\n", 15000),
    ],
)
async def test_safe_read_reconnects_after_dropped_reply(valkey, command, reply, expected):
    server, backend = await valkey(lambda args, n: None if n == 1 else reply)
    client = backend.raw_client()
    assert await client.execute_command(*command) == expected
    assert len(server.commands) == 2
    assert server.connections == 2
    assert client.connection_pool.connection_kwargs["socket_connect_timeout"] == 3
    assert client.connection_pool.connection_kwargs["socket_timeout"] == 5


async def test_safe_read_timeout_reconnects(valkey):
    server, backend = await valkey(lambda args, n: "hang" if n == 1 else _resp("v"), socket_timeout=0.03)
    assert await backend.raw_client().get("k") == "v"
    assert [c[0] for c in server.commands] == ["GET", "GET"]
    assert server.connections == 2


async def test_safe_read_readonly_reconnects(valkey):
    server, backend = await valkey(lambda args, n: _READONLY if n == 1 else _resp("v"))
    assert await backend.raw_client().get("k") == "v"
    assert server.connections == 2


@pytest.mark.parametrize("failure", [None, "hang", _READONLY], ids=["disconnect", "timeout", "readonly"])
async def test_persistent_read_failure_has_only_two_retries(valkey, failure):
    server, backend = await valkey(lambda args, n: failure, socket_timeout=0.03)
    with pytest.raises((RedisConnectionError, RedisTimeoutError, ReadOnlyError)):
        await backend.raw_client().get("k")
    assert len(server.commands) == 3
    assert server.connections == 3


@pytest.mark.parametrize(
    "command",
    [
        ("SET", "k", "v"),
        ("INCRBY", "k", 1),
        ("EVAL", "return redis.call('INCR', KEYS[1])", 1, "k"),
        ("EVALSHA", "script-sha", 1, "k"),
        ("GETDEL", "k"),
        ("GETEX", "k", "EX", 30),
    ],
)
@pytest.mark.parametrize("failure", [None, "hang"], ids=["disconnect", "timeout"])
async def test_committed_mutation_with_lost_reply_is_never_replayed(valkey, command, failure):
    commits = 0

    def commit_then_fail(args, n):
        nonlocal commits
        commits += 1
        return failure

    server, backend = await valkey(commit_then_fail, socket_timeout=0.03, query="?retry_on_timeout=true")
    with pytest.raises((RedisConnectionError, RedisTimeoutError)):
        await backend.raw_client().execute_command(*command)
    assert commits == 1
    assert len(server.commands) == 1
    assert server.connections == 1


async def test_readonly_write_fails_without_replay(valkey):
    server, backend = await valkey(lambda args, n: _READONLY)
    # Direct Redis raises READONLY; Sentinel disconnects and translates it to
    # ConnectionError. Neither exception authorizes write replay.
    with pytest.raises((ReadOnlyError, RedisConnectionError)):
        await backend.raw_client().set("k", "v")
    assert [c[0] for c in server.commands] == ["SET"]
    assert server.connections == 1


@pytest.mark.parametrize("transaction", [False, True], ids=["pipeline", "transaction"])
@pytest.mark.parametrize("failure", [None, "hang"], ids=["disconnect", "timeout"])
async def test_committed_pipeline_is_never_replayed(valkey, transaction, failure):
    commits = 0

    def execute(args, n):
        nonlocal commits
        if args[0] == "MULTI":
            return "+OK\r\n"
        if transaction and args[0] == "INCRBY":
            return "+QUEUED\r\n"
        assert args[0] == ("EXEC" if transaction else "INCRBY")
        commits += 1
        return failure

    server, backend = await valkey(execute, socket_timeout=0.03, query="?retry_on_timeout=true")
    async with backend.raw_client().pipeline(transaction=transaction) as pipe:
        pipe.incr("k")
        with pytest.raises((RedisConnectionError, RedisTimeoutError)):
            await pipe.execute()
    assert commits == 1
    assert [c[0] for c in server.commands] == (["MULTI", "INCRBY", "EXEC"] if transaction else ["INCRBY"])
    assert server.connections == 1


async def test_sentinel_read_failure_rediscovers_changed_master(resp_servers, monkeypatch):
    start, clients = resp_servers
    new_master = await start(lambda args, n: _resp("new-master"))
    master = SimpleNamespace(port=None)

    def old_reply(args, n):
        if n == 1:
            return _resp("old-master")
        master.port = new_master.port
        return None

    old_master = await start(old_reply)
    master.port = old_master.port
    backend, sentinel = await _sentinel_backend(start, clients, monkeypatch, master)
    client = backend.raw_client()
    assert await client.get("k") == "old-master"
    assert await client.get("k") == "new-master"
    assert [c[0] for c in old_master.commands] == ["GET", "GET"]
    assert [c[0] for c in new_master.commands] == ["GET"]
    assert len(sentinel.commands) == 2


async def test_sentinel_readonly_write_fails_then_next_read_discovers_master(resp_servers, monkeypatch):
    start, clients = resp_servers
    new_master = await start(lambda args, n: _resp("new-master"))
    master = SimpleNamespace(port=None)

    def old_reply(args, n):
        if args[0] == "GET":
            return _resp("old-master")
        master.port = new_master.port
        return _READONLY

    old_master = await start(old_reply)
    master.port = old_master.port
    backend, sentinel = await _sentinel_backend(start, clients, monkeypatch, master)
    client = backend.raw_client()
    assert await client.get("k") == "old-master"
    with pytest.raises(RedisConnectionError, match="previous master"):
        await client.set("k", "v")
    assert await client.get("k") == "new-master"
    assert [c[0] for c in old_master.commands] == ["GET", "SET"]
    assert [c[0] for c in new_master.commands] == ["GET"]
    assert len(sentinel.commands) == 2


async def test_sentinel_master_authenticates_and_selects_database_from_url(resp_servers, monkeypatch):
    start, clients = resp_servers
    master = await start(lambda args, n: _resp("v"))
    backend, _ = await _sentinel_backend(
        start,
        clients,
        monkeypatch,
        master,
        redis_url="redis://cache-user:p%40ss@unreachable-replica:1/5",
    )
    assert await backend.raw_client().get("k") == "v"
    assert ["AUTH", "cache-user", "p@ss"] in master.handshakes
    assert ["SELECT", "5"] in master.handshakes


async def test_concurrent_read_retry_cannot_enable_write_replay(valkey):
    commits = 0
    reads = 0

    def reply(args, n):
        nonlocal commits, reads
        if args[0] == "GET":
            reads += 1
            return None if reads == 1 else _resp("v")
        assert args[0] == "INCRBY"
        commits += 1
        return None

    server, backend = await valkey(reply)
    client = backend.raw_client()
    read, write = await asyncio.gather(client.get("k"), client.incr("counter"), return_exceptions=True)
    assert read == "v"
    assert isinstance(write, RedisConnectionError)
    assert commits == 1
    assert reads == 2
    assert len(server.commands) == 3


async def test_read_only_pipeline_is_not_implicitly_replayed(valkey):
    server, backend = await valkey(lambda args, n: None)
    async with backend.raw_client().pipeline(transaction=False) as pipe:
        pipe.get("k")
        with pytest.raises(RedisConnectionError):
            await pipe.execute()
    assert [c[0] for c in server.commands] == ["GET"]
    assert server.connections == 1
