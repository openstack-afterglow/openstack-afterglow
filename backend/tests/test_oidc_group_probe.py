"""Standalone diagnostic consumers: signed synthetic HTTPS OIDC, no app or DB imports."""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import socket
import stat
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/oidc_group_probe.py"
_SPEC = importlib.util.spec_from_file_location("afterglow_oidc_group_probe_tests", _SCRIPT)
assert _SPEC and _SPEC.loader
probe_cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = probe_cli
_SPEC.loader.exec_module(probe_cli)

ISSUER = "https://issuer.example"
CLIENT_ID = "new diagnostic:client+id"
SECRET = "synthetic-secret:+ /not-production"
ACCESS_TOKEN = "synthetic-access-token-never-write"
REFRESH_TOKEN = "synthetic-refresh-token-never-write"
PRIVATE_VALUE = "unallowlisted-private-value-never-write"
ROLE_OWNER = "https://gitlab.org/claims/groups/owner"
ROLE_MAINTAINER = "https://gitlab.org/claims/groups/maintainer"
ROLE_DEVELOPER = "https://gitlab.org/claims/groups/developer"
_MISSING = object()


def _b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@pytest.fixture(scope="module")
def signing_keys():
    return tuple(rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))


class SignedProvider:
    """Only the HTTPS provider boundary is synthetic; all probe validation is real."""

    def __init__(self, keys):
        self.key, self.other_key = keys
        self.signing_key = self.key
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid="diagnostic-key", use="sig", alg="RS256")
        self.jwks = {"keys": [public]}
        self.discovery = {
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/oauth/authorize",
            "token_endpoint": ISSUER + "/oauth/token",
            "jwks_uri": ISSUER + "/oauth/discovery/keys",
            "userinfo_endpoint": ISSUER + "/oauth/userinfo",
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        }
        self.claim_overrides = {}
        self.omit_claims = set()
        self.userinfo = {
            "sub": "gitlab-subject-42",
            "groups": ["division/direct", "division", "shared/inherited"],
            "groups_direct": ["userinfo/only-direct"],
            ROLE_OWNER: ["direct-owner-name"],
            ROLE_MAINTAINER: ["direct-maintainer-name"],
            ROLE_DEVELOPER: ["direct-developer-name"],
            "private_profile": PRIVATE_VALUE,
        }
        self.responses = {}
        self.requests = []
        self.probe = None
        self.last_token = None

    def claims(self):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "azp": CLIENT_ID,
            "sub": "gitlab-subject-42",
            "iat": now - 10,
            "exp": now + 3600,
            "nonce": self.probe.nonce,
            "at_hash": _b64(hashlib.sha256(ACCESS_TOKEN.encode()).digest()[:16]),
            "preferred_username": "diagnostic.user",
            "email": "diagnostic@example.invalid",
            "email_verified": True,
            "groups_direct": ["division/direct", "id-token/only-direct"],
            "groups": ["id-token/all-is-not-userinfo"],
            "private_profile": PRIVATE_VALUE,
        }
        claims.update(self.claim_overrides)
        return {key: value for key, value in claims.items() if key not in self.omit_claims}

    def handle(self, request):
        self.requests.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == "issuer.example", "Probe followed an untrusted provider destination"
        path = request.url.path
        if path in self.responses:
            return self.responses[path]
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json=self.discovery)
        if path == "/oauth/token":
            assert request.method == "POST"
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            assert form == {
                "grant_type": ["authorization_code"],
                "code": ["synthetic-code"],
                "redirect_uri": [self.probe.redirect_uri],
                "code_verifier": [self.probe.verifier],
            }
            basic = base64.b64encode(f"{quote_plus(CLIENT_ID)}:{quote_plus(SECRET)}".encode()).decode()
            assert request.headers["authorization"] == "Basic " + basic
            query = parse_qs(urlsplit(self.probe.authorization_url).query)
            assert _b64(hashlib.sha256(form["code_verifier"][0].encode()).digest()) == query["code_challenge"][0]
            self.last_token = jwt.encode(
                self.claims(), self.signing_key, algorithm="RS256", headers={"kid": "diagnostic-key"}
            )
            return httpx.Response(
                200,
                json={
                    "access_token": ACCESS_TOKEN,
                    "id_token": self.last_token,
                    "refresh_token": REFRESH_TOKEN,
                    "token_type": "Bearer",
                    "scope": "openid profile email",
                },
            )
        if path == "/oauth/discovery/keys":
            assert request.method == "GET"
            return httpx.Response(200, json=self.jwks)
        if path == "/oauth/userinfo":
            assert request.method == "GET"
            assert request.headers["authorization"] == "Bearer " + ACCESS_TOKEN
            return httpx.Response(200, json=self.userinfo)
        pytest.fail(f"Unexpected synthetic provider path: {path}")

    def paths(self):
        return [request.url.path for request in self.requests]


@pytest.fixture
def wire(signing_keys):
    provider = SignedProvider(signing_keys)
    with httpx.Client(
        transport=httpx.MockTransport(provider.handle), trust_env=False, follow_redirects=False
    ) as client:
        yield provider, client


def _start(wire, **config_overrides):
    provider, client = wire
    fields = {"issuer": ISSUER, "client_id": CLIENT_ID, "client_secret": SECRET, **config_overrides}
    provider.probe = probe_cli.Probe(probe_cli.Config(**fields), client)
    return provider.probe


def _finish(probe):
    return probe.callback({"state": probe.state, "code": "synthetic-code"}, probe.binding)


def _mapping_lines(text):
    return {key: value.lstrip(" ") for key, value in (line.split(":", 1) for line in text.splitlines())}


def test_signed_code_flow_preserves_distinct_claim_sources_and_reports_only_allowlisted_values(wire):
    provider, _ = wire
    probe = _start(wire)
    query = parse_qs(urlsplit(probe.authorization_url).query)
    assert query["response_type"] == ["code"]
    assert query["response_mode"] == ["query"]
    assert query["scope"] == ["openid profile email"]
    assert query["state"] == [probe.state]
    assert query["nonce"] == [probe.nonce]
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [_b64(hashlib.sha256(probe.verifier.encode()).digest())]
    assert SECRET not in probe.authorization_url
    assert probe.verifier not in probe.authorization_url
    assert probe.start_path.startswith("/start/")
    report = _finish(probe)
    assert probe.consumed is True
    assert provider.paths() == [
        "/.well-known/openid-configuration",
        "/oauth/token",
        "/oauth/discovery/keys",
        "/oauth/userinfo",
    ]
    assert report["schema_version"] == 1
    assert report["issuer"] == ISSUER and report["client_id"] == CLIENT_ID
    assert report["requested_scope"] == report["granted_scope"] == "openid profile email"
    assert report["identity"] == {
        "sub": "gitlab-subject-42",
        "preferred_username": "diagnostic.user",
        "email": "diagnostic@example.invalid",
        "email_verified": True,
    }
    assert report["id_token"]["group_claims"]["groups_direct"]["values"] == ["division/direct", "id-token/only-direct"]
    assert report["userinfo"]["group_claims"]["groups"]["values"] == provider.userinfo["groups"]
    for role in (ROLE_OWNER, ROLE_MAINTAINER, ROLE_DEVELOPER):
        assert report["userinfo"]["group_claims"][role]["values"] == provider.userinfo[role]
        assert report["id_token"]["group_claims"][role]["status"] == "missing"
    assert report["id_token"]["claim_names"] == sorted(provider.claims())
    assert report["userinfo"]["claim_names"] == sorted(provider.userinfo)
    assert report["comparison"] == {
        "comparable": True,
        "direct_only": ["id-token/only-direct"],
        "all_only": ["division", "shared/inherited"],
    }
    assert report["verification"] == {
        "id_token_verified": True,
        "userinfo_subject_matches": True,
        "keystone_transport_observed": False,
    }
    encoded = json.dumps(report)
    for sensitive in (SECRET, ACCESS_TOKEN, REFRESH_TOKEN, provider.last_token, PRIVATE_VALUE):
        assert sensitive not in encoded
    for value in vars(probe).values():
        assert value != ACCESS_TOKEN and value != provider.last_token


@pytest.mark.parametrize("source,claim", [("id_token", "groups_direct"), ("userinfo", "groups")])
@pytest.mark.parametrize(
    "value,status,json_type,values",
    [
        (_MISSING, "missing", "missing", None),
        ([], "array", "array", []),
        (["team/path", "team/path", "한글/팀"], "array", "array", ["team/path", "team/path", "한글/팀"]),
        (None, "invalid", "null", None),
        ("team/path", "invalid", "string", None),
        ({"name": "team/path"}, "invalid", "object", None),
        (7, "invalid", "number", None),
        (False, "invalid", "boolean", None),
        (["team/path", 7], "invalid", "array", None),
        ([None], "invalid", "array", None),
    ],
)
def test_group_shapes_are_diagnostic_results_not_missing_empty_coercions(
    wire, source, claim, value, status, json_type, values
):
    provider, _ = wire
    probe = _start(wire)
    if source == "id_token":
        if value is _MISSING:
            provider.omit_claims.add(claim)
        else:
            provider.claim_overrides[claim] = value
    elif value is _MISSING:
        provider.userinfo.pop(claim)
    else:
        provider.userinfo[claim] = value
    report = _finish(probe)
    assert report[source]["group_claims"][claim] == {"status": status, "json_type": json_type, "values": values}
    assert report["comparison"]["comparable"] is (status == "array")
    if status != "array":
        assert report["comparison"]["direct_only"] is None
        assert report["comparison"]["all_only"] is None


@pytest.mark.parametrize("wrong", ["state", "binding", "missing-state", "missing-binding"])
def test_wrong_browser_binding_or_state_never_reaches_exchange_or_consumes_valid_attempt(wire, wrong):
    provider, _ = wire
    probe = _start(wire)
    params, binding = {"state": probe.state, "code": "synthetic-code"}, probe.binding
    if wrong == "state":
        params["state"] = "wrong-state"
    elif wrong == "missing-state":
        params.pop("state")
    else:
        binding = "wrong-binding" if wrong == "binding" else ""
    before = list(provider.paths())
    with pytest.raises(probe_cli.ProbeError):
        probe.callback(params, binding)
    assert provider.paths() == before
    assert probe.consumed is False
    assert _finish(probe)["verification"]["id_token_verified"] is True


@pytest.mark.parametrize("first_result", ["success", "token-failure", "denied", "missing-code"])
def test_consumed_callback_is_never_replayed_even_when_first_exchange_fails(wire, first_result):
    provider, _ = wire
    probe = _start(wire)
    params = {"state": probe.state, "code": "synthetic-code"}
    if first_result == "token-failure":
        provider.responses["/oauth/token"] = httpx.Response(503, text=SECRET + PRIVATE_VALUE)
    elif first_result == "denied":
        params = {"state": probe.state, "error": PRIVATE_VALUE, "error_description": SECRET}
    elif first_result == "missing-code":
        params.pop("code")
    if first_result == "success":
        _finish(probe)
    else:
        with pytest.raises(probe_cli.ProbeError) as failure:
            probe.callback(params, probe.binding)
        assert SECRET not in str(failure.value) and PRIVATE_VALUE not in str(failure.value)
    assert probe.consumed is True
    before = list(provider.paths())
    with pytest.raises(probe_cli.ProbeError):
        _finish(probe)
    assert provider.paths() == before


def test_expired_callback_fails_before_any_token_network(wire):
    provider, _ = wire
    probe = _start(wire)
    probe.expires_at = time.monotonic() - 1
    with pytest.raises(probe_cli.ProbeError):
        _finish(probe)
    assert provider.paths() == ["/.well-known/openid-configuration"]


@pytest.mark.parametrize(
    "failure",
    [
        "signature",
        "issuer",
        "audience",
        "nonce",
        "azp",
        "multi-audience-missing-azp",
        "at_hash",
        "expired",
        "future-iat",
        "missing-iss",
        "missing-aud",
        "missing-sub",
        "missing-exp",
        "missing-iat",
        "missing-nonce",
        "empty-sub",
    ],
)
def test_invalid_signed_identity_fails_closed_before_userinfo_and_cannot_retry(wire, failure):
    provider, _ = wire
    probe = _start(wire)
    changes = {
        "issuer": {"iss": "https://other.example"},
        "audience": {"aud": "production-client-not-this-diagnostic"},
        "nonce": {"nonce": "not-this-login"},
        "azp": {"azp": "another-client"},
        "multi-audience-missing-azp": {"aud": [CLIENT_ID, "other-client"]},
        "at_hash": {"at_hash": _b64(b"not-the-access-token")},
        "expired": {"exp": int(time.time()) - 3600},
        "future-iat": {"iat": int(time.time()) + 3600},
        "empty-sub": {"sub": ""},
    }
    if failure == "signature":
        provider.signing_key = provider.other_key
    elif failure.startswith("missing-"):
        provider.omit_claims.add(failure.removeprefix("missing-"))
    else:
        provider.claim_overrides.update(changes[failure])
        if failure == "multi-audience-missing-azp":
            provider.omit_claims.add("azp")
    with pytest.raises(probe_cli.ProbeError):
        _finish(probe)
    assert probe.consumed is True
    assert "/oauth/userinfo" not in provider.paths()
    before = list(provider.paths())
    with pytest.raises(probe_cli.ProbeError):
        _finish(probe)
    assert provider.paths() == before


def test_correct_multi_audience_authorized_party_and_optional_at_hash_are_accepted(wire):
    provider, _ = wire
    probe = _start(wire)
    provider.claim_overrides["aud"] = [CLIENT_ID, "another-resource"]
    provider.omit_claims.add("at_hash")
    assert _finish(probe)["verification"]["id_token_verified"] is True


@pytest.mark.parametrize("subject", ["different-subject", None, 42, ""])
def test_userinfo_must_match_verified_id_token_subject(wire, subject):
    provider, _ = wire
    probe = _start(wire)
    provider.userinfo["sub"] = subject
    with pytest.raises(probe_cli.ProbeError):
        _finish(probe)
    assert provider.paths()[-1] == "/oauth/userinfo"
    assert probe.consumed is True


@pytest.mark.parametrize("field", ["authorization_endpoint", "token_endpoint", "jwks_uri", "userinfo_endpoint"])
@pytest.mark.parametrize(
    "endpoint",
    [
        "https://hostile.example/path",
        "http://issuer.example/path",
        "https://user:pass@issuer.example/path",
        "https://issuer.example/path#fragment",
    ],
)
def test_hostile_discovery_endpoint_is_rejected_before_credentials_can_leave_origin(wire, field, endpoint):
    provider, client = wire
    provider.discovery[field] = endpoint
    with pytest.raises(probe_cli.ProbeError):
        probe_cli.discover(client, ISSUER)
    assert provider.paths() == ["/.well-known/openid-configuration"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", "https://other.example"),
        ("response_types_supported", ["token"]),
        ("code_challenge_methods_supported", ["plain"]),
        ("id_token_signing_alg_values_supported", ["HS256"]),
        ("token_endpoint_auth_methods_supported", ["client_secret_post"]),
    ],
)
def test_incompatible_discovery_is_not_silently_downgraded(wire, field, value):
    provider, client = wire
    provider.discovery[field] = value
    with pytest.raises(probe_cli.ProbeError):
        probe_cli.discover(client, ISSUER)


@pytest.mark.parametrize(
    "path", ["/.well-known/openid-configuration", "/oauth/token", "/oauth/discovery/keys", "/oauth/userinfo"]
)
@pytest.mark.parametrize("bad_response", ["redirect", "non-json", "oversized", "not-object", "failed"])
def test_each_provider_boundary_rejects_redirects_and_unusable_or_oversized_json(wire, path, bad_response):
    provider, client = wire
    responses = {
        "redirect": httpx.Response(302, headers={"Location": "https://hostile.example/steal"}),
        "non-json": httpx.Response(200, text=PRIVATE_VALUE),
        "oversized": httpx.Response(200, content=b'{"padding":"' + b"x" * (1024 * 1024) + b'"}'),
        "not-object": httpx.Response(200, json=[]),
        "failed": httpx.Response(503, text=PRIVATE_VALUE),
    }
    provider.responses[path] = responses[bad_response]
    with pytest.raises(probe_cli.ProbeError) as failure:
        if path == "/.well-known/openid-configuration":
            probe_cli.discover(client, ISSUER)
        else:
            _finish(_start(wire))
    assert provider.paths()[-1] == path
    assert PRIVATE_VALUE not in str(failure.value)
    assert SECRET not in str(failure.value)
    assert ACCESS_TOKEN not in str(failure.value)


@pytest.mark.parametrize(
    "fields",
    [
        {"issuer": "http://issuer.example"},
        {"issuer": "https://user:pass@issuer.example"},
        {"issuer": ISSUER + "?query=value"},
        {"issuer": ISSUER + "#fragment"},
        {"port": 0},
        {"port": 65536},
        {"scope": "profile email"},
        {"scope": "openid api"},
        {"scope": "openid read_user"},
    ],
)
def test_configuration_rejects_unsafe_or_unrequested_authority(fields):
    with pytest.raises(probe_cli.ProbeError):
        probe_cli.Config(**{"issuer": ISSUER, "client_id": CLIENT_ID, "client_secret": SECRET, **fields})


@pytest.mark.parametrize(
    "source,claim,expected",
    [
        ("id_token", "groups_direct", "division/direct;id-token/only-direct"),
        ("userinfo", "groups", "division/direct;division;shared/inherited"),
        ("userinfo", "groups_direct", "userinfo/only-direct"),
        ("id_token", "groups", "id-token/all-is-not-userinfo"),
    ],
)
@pytest.mark.parametrize("prefix", ["OIDC-", "HTTP_OIDC_"])
def test_mapping_candidate_uses_exact_selected_source_and_native_header_spelling(wire, source, claim, expected, prefix):
    report = _finish(_start(wire))
    lines = _mapping_lines(probe_cli.mapping_input(report, source, claim, prefix=prefix))
    normalize = str.upper if prefix == "HTTP_OIDC_" else str
    assert lines == {
        prefix + normalize("iss"): ISSUER,
        prefix + normalize("sub"): "gitlab-subject-42",
        prefix + normalize("preferred_username"): "diagnostic.user",
        prefix + normalize("email"): "diagnostic@example.invalid",
        prefix + normalize("email_verified"): "true",
        prefix + normalize(claim): expected,
    }


@pytest.mark.parametrize("value", [_MISSING, None, "one/group", ["group", 1]])
@pytest.mark.parametrize("source,claim", [("id_token", "groups_direct"), ("userinfo", "groups")])
def test_mapping_never_falls_back_to_other_token_source_or_claim(wire, value, source, claim):
    provider, _ = wire
    probe = _start(wire)
    if source == "id_token":
        if value is _MISSING:
            provider.omit_claims.add(claim)
        else:
            provider.claim_overrides[claim] = value
    elif value is _MISSING:
        provider.userinfo.pop(claim)
    else:
        provider.userinfo[claim] = value
    report = _finish(probe)
    with pytest.raises(probe_cli.ProbeError):
        probe_cli.mapping_input(report, source, claim)


def test_empty_mapping_claim_is_present_and_optional_identity_is_not_invented(wire):
    provider, _ = wire
    probe = _start(wire)
    provider.claim_overrides["groups_direct"] = []
    provider.omit_claims.update({"preferred_username", "email", "email_verified"})
    report = _finish(probe)
    lines = _mapping_lines(probe_cli.mapping_input(report, "id_token", "groups_direct"))
    assert lines == {"OIDC-iss": ISSUER, "OIDC-sub": "gitlab-subject-42", "OIDC-groups_direct": ""}


@pytest.mark.parametrize(
    "member",
    [
        "",
        "ambiguous;two-groups",
        "group\nOIDC-sub: forged",
        "group\rname",
        "group\tname",
        "group\x00name",
        "group\x7fname",
    ],
)
def test_mapping_rejects_delimiter_or_control_ambiguity_without_altering_report(wire, member):
    provider, _ = wire
    probe = _start(wire)
    provider.claim_overrides["groups_direct"] = [member]
    report = _finish(probe)
    before = copy.deepcopy(report)
    with pytest.raises(probe_cli.ProbeError):
        probe_cli.mapping_input(report, "id_token", "groups_direct")
    assert report == before
    assert report["id_token"]["group_claims"]["groups_direct"]["values"] == [member]


@pytest.mark.parametrize(
    "source,claim,prefix,delimiter",
    [
        ("merged", "groups", "OIDC-", ";"),
        ("id_token", ROLE_OWNER, "OIDC-", ";"),
        ("id_token", "groups_direct", "HTTP_EVIL_", ";"),
        ("id_token", "groups_direct", "OIDC-", ","),
    ],
)
def test_mapping_rejects_unrecognized_transport_or_claim_choices(wire, source, claim, prefix, delimiter):
    report = _finish(_start(wire))
    with pytest.raises(probe_cli.ProbeError):
        probe_cli.mapping_input(report, source, claim, prefix=prefix, delimiter=delimiter)


def test_report_write_is_private_exclusive_and_contains_no_raw_tokens_or_secret(wire, tmp_path):
    provider, _ = wire
    report = _finish(_start(wire))
    directory = tmp_path / "private-result"
    path = probe_cli.write_results(directory, report)
    assert path == directory / "report.json"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == report
    assert {entry.name for entry in directory.iterdir()} == {"report.json"}
    original = path.read_bytes()
    for sensitive in (SECRET, ACCESS_TOKEN, REFRESH_TOKEN, provider.last_token, PRIVATE_VALUE):
        assert sensitive.encode() not in original
    with pytest.raises((probe_cli.ProbeError, OSError)):
        probe_cli.write_results(directory, report)
    assert path.read_bytes() == original


@pytest.mark.parametrize("unsafe", ["directory-symlink", "report-symlink", "world-readable-directory"])
def test_output_refuses_symlink_and_nonprivate_locations_without_overwriting_target(wire, tmp_path, unsafe):
    report = _finish(_start(wire))
    target = tmp_path / "untouched"
    target.write_text("original target")
    directory = tmp_path / "output"
    if unsafe == "directory-symlink":
        real = tmp_path / "real-output"
        real.mkdir(mode=0o700)
        directory.symlink_to(real, target_is_directory=True)
    else:
        directory.mkdir(mode=0o700)
        if unsafe == "report-symlink":
            (directory / "report.json").symlink_to(target)
        else:
            directory.chmod(0o755)
    with pytest.raises((probe_cli.ProbeError, OSError)):
        probe_cli.write_results(directory, report)
    assert target.read_text() == "original target"
    if unsafe != "report-symlink":
        assert not (directory / "report.json").exists()


@contextmanager
def _callback_server(wire, output_dir, **kwargs):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    probe = _start(wire, port=port)
    server = probe_cli.ProbeServer(probe, output_dir, **kwargs)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, follow_redirects=False, timeout=5
        ) as browser:
            yield server, browser
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


def test_loopback_start_callback_writes_private_results_without_serving_or_logging_claims(wire, tmp_path, capsys):
    provider, _ = wire
    directory = tmp_path / "browser-output"
    with _callback_server(wire, directory, mapping_source="id_token", mapping_claim="groups_direct") as (
        server,
        browser,
    ):
        probe = server.probe
        assert server.server_address[0] == "127.0.0.1"
        assert browser.get("/start/not-the-one-use-path").status_code == 404
        started = browser.get(probe.start_path)
        assert started.status_code == 302
        assert started.headers["location"] == probe.authorization_url
        cookie = started.headers["set-cookie"]
        assert f"oidc_probe={probe.binding}" in cookie
        assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
        response = browser.get("/callback", params={"state": probe.state, "code": "synthetic-code"})
        assert response.status_code == 200
        assert server.finished is True and server.succeeded is True and server.error is None
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "Max-Age=0" in response.headers["set-cookie"]
        assert browser.get("/report.json").status_code == 404
        assert browser.get("/mapping-input.txt").status_code == 404
        before = list(provider.paths())
        assert browser.get("/callback", params={"state": probe.state, "code": "synthetic-code"}).status_code == 400
        assert provider.paths() == before
        assert stat.S_IMODE((directory / "mapping-input.txt").stat().st_mode) == 0o600
        assert (
            _mapping_lines((directory / "mapping-input.txt").read_text())["OIDC-groups_direct"]
            == "division/direct;id-token/only-direct"
        )
        for sensitive in (
            SECRET,
            ACCESS_TOKEN,
            REFRESH_TOKEN,
            PRIVATE_VALUE,
            "synthetic-code",
            "division/direct",
            probe.state,
        ):
            assert sensitive not in response.text
    captured = capsys.readouterr()
    for sensitive in (SECRET, ACCESS_TOKEN, "synthetic-code", probe.state, probe.binding):
        assert sensitive not in captured.out + captured.err


@pytest.mark.parametrize("attack", ["host", "duplicate-state", "duplicate-code", "missing-cookie", "wrong-state"])
def test_loopback_rejects_host_query_and_browser_attacks_before_network(wire, tmp_path, attack):
    provider, _ = wire
    with _callback_server(wire, tmp_path / "rejected") as (server, browser):
        probe = server.probe
        browser.cookies.set("oidc_probe", probe.binding)
        params = [("state", probe.state), ("code", "synthetic-code")]
        headers = {}
        if attack == "host":
            headers["Host"] = "hostile.example"
        elif attack == "duplicate-state":
            params.append(("state", probe.state))
        elif attack == "duplicate-code":
            params.append(("code", "attacker-code"))
        elif attack == "missing-cookie":
            browser.cookies.clear()
        else:
            params[0] = ("state", "attacker-state")
        response = browser.get("/callback?" + urlencode(params), headers=headers)
        assert response.status_code == 400
        assert provider.paths() == ["/.well-known/openid-configuration"]
        assert probe.consumed is False and server.finished is False and server.succeeded is False
        assert not (tmp_path / "rejected").exists()
        assert "synthetic-code" not in response.text and probe.state not in response.text


def test_loopback_provider_denial_finishes_one_shot_without_reflecting_provider_error(wire, tmp_path, capsys):
    provider, _ = wire
    with _callback_server(wire, tmp_path / "denied") as (server, browser):
        probe = server.probe
        browser.cookies.set("oidc_probe", probe.binding)
        response = browser.get(
            "/callback",
            params={
                "state": probe.state,
                "error": PRIVATE_VALUE,
                "error_description": SECRET,
            },
        )
        assert response.status_code == 400
        assert server.finished is True and server.succeeded is False
        assert isinstance(server.error, str) and server.error
        assert PRIVATE_VALUE not in response.text + server.error
        assert SECRET not in response.text + server.error
        assert provider.paths() == ["/.well-known/openid-configuration"]
        assert not (tmp_path / "denied").exists()
    captured = capsys.readouterr()
    assert PRIVATE_VALUE not in captured.out + captured.err
    assert SECRET not in captured.out + captured.err
