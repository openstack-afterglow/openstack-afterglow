#!/usr/bin/env python3
"""One-shot, loopback-only GitLab OIDC inspection; never authenticates to Keystone."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit

import httpx
import jwt

GROUP_CLAIMS = (
    "groups",
    "groups_direct",
    *(
        f"https://gitlab.org/claims/groups/{r}"
        for r in ("owner", "maintainer", "developer")
    ),
)
MAX_BYTES = 1024 * 1024


class ProbeError(Exception):
    """Safe operator-facing failure, never a provider response or credential."""


def _https(url):
    try:
        p = urlsplit(url)
        if (
            p.scheme != "https"
            or not p.hostname
            or p.username
            or p.password
            or p.query
            or p.fragment
        ):
            raise ValueError
        return p.scheme, p.hostname, p.port or 443
    except (ValueError, TypeError, AttributeError):
        raise ProbeError("Expected a clean HTTPS provider URL") from None


@dataclass(frozen=True)
class Config:
    issuer: str
    client_id: str
    client_secret: str
    port: int = 8765
    scope: str = "openid profile email"
    timeout: int = 300

    def __post_init__(self):
        _https(self.issuer)
        if (
            not self.client_id
            or not self.client_secret
            or not 1 <= self.port <= 65535
            or not 1 <= self.timeout <= 1800
        ):
            raise ProbeError("Invalid client, port or timeout")
        if "openid" not in self.scope.split() or set(self.scope.split()) - {
            "openid",
            "profile",
            "email",
        }:
            raise ProbeError("Only openid, profile and email scopes are allowed")

    @property
    def redirect_uri(self):
        return f"http://127.0.0.1:{self.port}/callback"


def _json(client, method, url, **kwargs):
    try:
        with client.stream(method, url, follow_redirects=False, **kwargs) as response:
            if response.status_code != 200:
                raise ProbeError("Provider request rejected (non-200 response)")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ProbeError("Provider response exceeds size limit")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ProbeError("Provider JSON must be an object")
        return result
    except (httpx.HTTPError, ValueError):
        raise ProbeError("Provider request or JSON failed") from None


def discover(client, issuer):
    origin = _https(issuer)
    doc = _json(client, "GET", issuer.rstrip("/") + "/.well-known/openid-configuration")
    if doc.get("issuer") != issuer:
        raise ProbeError("Discovery issuer mismatch")
    for key in (
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "userinfo_endpoint",
    ):
        if _https(doc.get(key)) != origin:
            raise ProbeError("Discovery endpoint origin mismatch")
    for key, required, default in (
        ("response_types_supported", "code", []),
        ("code_challenge_methods_supported", "S256", ["S256"]),
        ("id_token_signing_alg_values_supported", "RS256", []),
        (
            "token_endpoint_auth_methods_supported",
            "client_secret_basic",
            ["client_secret_basic"],
        ),
    ):
        values = doc.get(key, default)
        if not isinstance(values, list) or required not in values:
            raise ProbeError(
                "Provider does not support required code/PKCE/RS256/basic flow"
            )
    return doc


def _b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _equal(left, right):
    return isinstance(left, str) and hmac.compare_digest(left.encode(), right.encode())


class Probe:
    def __init__(self, config, client):
        self.config, self.client = config, client
        self.metadata = discover(client, config.issuer)
        self.state, self.nonce, self.verifier, self.binding = (
            secrets.token_urlsafe(32) for _ in range(4)
        )
        self.start_path = "/start/" + secrets.token_urlsafe(24)
        self.redirect_uri = config.redirect_uri
        self.expires_at = time.monotonic() + config.timeout
        self.consumed = False
        self.authorization_url = (
            self.metadata["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "client_id": config.client_id,
                    "redirect_uri": self.redirect_uri,
                    "response_type": "code",
                    "response_mode": "query",
                    "scope": config.scope,
                    "state": self.state,
                    "nonce": self.nonce,
                    "code_challenge": _b64(
                        hashlib.sha256(self.verifier.encode()).digest()
                    ),
                    "code_challenge_method": "S256",
                }
            )
        )

    def callback(self, params, binding):
        if self.consumed or time.monotonic() >= self.expires_at:
            raise ProbeError("Callback expired or already consumed")
        if not _equal(params.get("state"), self.state) or not _equal(
            binding, self.binding
        ):
            raise ProbeError("Callback state or browser binding mismatch")
        self.consumed = True
        if (
            params.get("error")
            or not isinstance(params.get("code"), str)
            or not params["code"]
        ):
            raise ProbeError("Authorization denied or code missing")
        tokens = _json(
            self.client,
            "POST",
            self.metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": params["code"],
                "redirect_uri": self.redirect_uri,
                "code_verifier": self.verifier,
            },
            auth=httpx.BasicAuth(
                quote_plus(self.config.client_id), quote_plus(self.config.client_secret)
            ),
        )
        if tokens.get("error") or str(tokens.get("token_type", "")).lower() != "bearer":
            raise ProbeError("Invalid token response")
        access, encoded = tokens.get("access_token"), tokens.get("id_token")
        if not isinstance(access, str) or not access or not isinstance(encoded, str):
            raise ProbeError("Missing access or ID token")
        try:
            header = jwt.get_unverified_header(encoded)
            if header.get("alg") != "RS256":
                raise ProbeError("Only RS256 ID tokens are accepted")
            keys = _json(self.client, "GET", self.metadata["jwks_uri"]).get("keys", [])
            candidates = [
                k
                for k in keys
                if isinstance(k, dict)
                and k.get("kty") == "RSA"
                and k.get("use", "sig") == "sig"
                and k.get("alg", "RS256") == "RS256"
                and (header.get("kid") is None or k.get("kid") == header["kid"])
            ]
            if len(candidates) != 1:
                raise ProbeError("Signing key is not unique")
            claims = jwt.decode(
                encoded,
                jwt.PyJWK.from_dict(candidates[0]).key,
                algorithms=["RS256"],
                audience=self.config.client_id,
                issuer=self.config.issuer,
                options={"require": ["iss", "aud", "sub", "exp", "iat", "nonce"]},
            )
            if not _equal(claims.get("nonce"), self.nonce):
                raise ProbeError("ID token nonce mismatch")
            if (
                "azp" in claims
                or isinstance(claims["aud"], list)
                and len(claims["aud"]) > 1
            ) and claims.get("azp") != self.config.client_id:
                raise ProbeError("ID token authorized party mismatch")
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise ProbeError("Invalid subject")
            if "at_hash" in claims and not _equal(
                claims["at_hash"], _b64(hashlib.sha256(access.encode()).digest()[:16])
            ):
                raise ProbeError("Access token hash mismatch")
        except (jwt.PyJWTError, TypeError, ValueError, KeyError):
            raise ProbeError("ID token validation failed") from None
        info = _json(
            self.client,
            "GET",
            self.metadata["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access}"},
        )
        if info.get("sub") != claims["sub"]:
            raise ProbeError("UserInfo subject mismatch")
        return build_report(self.config, claims, info, tokens.get("scope"))


def _group(value, present):
    kind = (
        "missing"
        if not present
        else "null"
        if value is None
        else "boolean"
        if isinstance(value, bool)
        else "array"
        if isinstance(value, list)
        else "string"
        if isinstance(value, str)
        else "object"
        if isinstance(value, dict)
        else "number"
    )
    valid = isinstance(value, list) and all(isinstance(v, str) for v in value)
    return {
        "status": "missing" if not present else "array" if valid else "invalid",
        "json_type": kind,
        "values": value if valid else None,
    }


def build_report(config, claims, userinfo, granted_scope=None):
    def section(data):
        return {
            "claim_names": sorted(data),
            "group_claims": {k: _group(data.get(k), k in data) for k in GROUP_CLAIMS},
        }

    direct, all_groups = (
        _group(claims.get("groups_direct"), "groups_direct" in claims),
        _group(userinfo.get("groups"), "groups" in userinfo),
    )
    comparable = direct["status"] == all_groups["status"] == "array"
    return {
        "schema_version": 1,
        "issuer": config.issuer,
        "client_id": config.client_id,
        "requested_scope": config.scope,
        "granted_scope": granted_scope,
        "identity": {
            k: claims[k]
            for k in ("sub", "preferred_username", "email", "email_verified")
            if k in claims
        },
        "id_token": section(claims),
        "userinfo": section(userinfo),
        "comparison": {
            "comparable": comparable,
            "direct_only": sorted(set(direct["values"]) - set(all_groups["values"]))
            if comparable
            else None,
            "all_only": sorted(set(all_groups["values"]) - set(direct["values"]))
            if comparable
            else None,
        },
        "verification": {
            "id_token_verified": True,
            "userinfo_subject_matches": True,
            "keystone_transport_observed": False,
        },
    }


def mapping_input(report, source, claim, prefix="OIDC-", delimiter=";"):
    if (
        source not in ("id_token", "userinfo")
        or claim not in ("groups", "groups_direct")
        or prefix not in ("OIDC-", "HTTP_OIDC_")
        or delimiter != ";"
    ):
        raise ProbeError("Invalid mapping source, claim, prefix or delimiter")
    group = report[source]["group_claims"][claim]
    if group["status"] != "array":
        raise ProbeError("Selected group claim is missing or invalid; no fallback")
    values = {
        "iss": report["issuer"],
        **report["identity"],
        claim: delimiter.join(group["values"]),
    }
    if any(
        not v or delimiter in v or any(ord(c) < 32 or ord(c) == 127 for c in v)
        for v in group["values"]
    ):
        raise ProbeError("Group values cannot be represented unambiguously")
    lines = []
    for key, value in values.items():
        if isinstance(value, bool):
            value = str(value).lower()
        if (
            not isinstance(value, str)
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or (key != claim and delimiter in value)
        ):
            raise ProbeError("Identity cannot be represented safely")
        name = prefix + (key.upper() if prefix == "HTTP_OIDC_" else key)
        lines.append(f"{name}: {value}")
    return "\n".join(lines) + "\n"


def _private_directory(directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = directory.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise ProbeError("Output directory must be private and owned by current user")
    return directory


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(data)


def write_results(directory, report):
    path = _private_directory(directory) / "report.json"
    _write_private(path, json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    return path


class ProbeServer(HTTPServer):
    def __init__(
        self,
        probe,
        output_dir,
        mapping_source=None,
        mapping_claim=None,
        mapping_prefix="OIDC-",
    ):
        self.probe, self.output_dir = probe, output_dir
        self.mapping_source, self.mapping_claim, self.mapping_prefix = (
            mapping_source,
            mapping_claim,
            mapping_prefix,
        )
        self.finished, self.succeeded, self.error = False, False, None
        super().__init__(("127.0.0.1", probe.config.port), _Handler)
        self.timeout = 0.5

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(5)
        return sock, address


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log callback codes, query strings or cookies.

    def _send(self, status, text, headers=()):
        body = text.encode()
        self.send_response(status)
        for key, value in (
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
            *headers,
        ):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        server, probe = self.server, self.server.probe
        if self.headers.get("Host") != f"127.0.0.1:{probe.config.port}":
            return self._send(400, "Invalid host")
        parsed = urlsplit(self.path)
        if (
            self.path == probe.start_path
            and not probe.consumed
            and time.monotonic() < probe.expires_at
        ):
            return self._send(
                302,
                "Continue at identity provider",
                (
                    ("Location", probe.authorization_url),
                    (
                        "Set-Cookie",
                        f"oidc_probe={probe.binding}; HttpOnly; SameSite=Lax; Path=/; Max-Age={probe.config.timeout}",
                    ),
                ),
            )
        if parsed.path != "/callback":
            return self._send(404, "Not found")
        try:
            params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=16)
            if any(len(v) != 1 for v in params.values()):
                raise ProbeError("Duplicate callback parameter")
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            binding = cookie["oidc_probe"].value if "oidc_probe" in cookie else ""
            report = probe.callback({k: v[0] for k, v in params.items()}, binding)
            candidate = (
                mapping_input(
                    report,
                    server.mapping_source,
                    server.mapping_claim,
                    server.mapping_prefix,
                )
                if server.mapping_source
                else None
            )
            write_results(server.output_dir, report)
            if candidate is not None:
                _write_private(Path(server.output_dir) / "mapping-input.txt", candidate)
            server.succeeded, server.finished = True, True
            self._send(
                200,
                "OIDC check complete. Read the private report in your terminal.",
                (
                    (
                        "Set-Cookie",
                        "oidc_probe=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
                    ),
                ),
            )
        except (ProbeError, OSError, ValueError, CookieError) as exc:
            server.error = (
                str(exc)
                if isinstance(exc, ProbeError)
                else "Local callback or output failed"
            )
            server.finished = probe.consumed
            self._send(
                400, "OIDC check failed. Check the terminal; no claims are served here."
            )


def _secret(path):
    if path is None:
        if not sys.stdin.isatty():
            raise ProbeError("Use an interactive terminal or --client-secret-file")
        return getpass.getpass("New diagnostic client secret: ")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        s = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_uid != os.getuid()
            or s.st_nlink != 1
            or s.st_mode & 0o077
            or s.st_size > 16384
        ):
            raise ProbeError("Secret file must be a private owned regular file")
        return stream.read(16385).decode().rstrip("\r\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--client-id")
    parser.add_argument("--client-secret-file", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scope", default="openid profile email")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mapping-source", choices=("id_token", "userinfo"))
    parser.add_argument("--mapping-claim", choices=("groups_direct", "groups"))
    parser.add_argument(
        "--mapping-prefix", choices=("OIDC-", "HTTP_OIDC_"), default="OIDC-"
    )
    args = parser.parse_args(argv)
    if bool(args.mapping_source) != bool(args.mapping_claim):
        parser.error("--mapping-source and --mapping-claim must be supplied together")
    try:
        config = Config(
            args.issuer,
            args.client_id or input("New diagnostic client ID: ").strip(),
            _secret(args.client_secret_file),
            args.port,
            args.scope,
            args.timeout,
        )
        if args.output_dir is None:
            base = _private_directory(
                Path.home() / ".local/share/afterglow/oidc-probes"
            )
            args.output_dir = Path(tempfile.mkdtemp(prefix="probe-", dir=base))
        directory = _private_directory(args.output_dir)
        with httpx.Client(
            timeout=10, follow_redirects=False, trust_env=False
        ) as client:
            probe = Probe(config, client)
            with ProbeServer(
                probe,
                directory,
                args.mapping_source,
                args.mapping_claim,
                args.mapping_prefix,
            ) as server:
                print(f"Register redirect URI: {config.redirect_uri}", flush=True)
                print(
                    f"Open once in this machine's browser: http://127.0.0.1:{config.port}{probe.start_path}",
                    flush=True,
                )
                while not server.finished and time.monotonic() < probe.expires_at:
                    server.handle_request()
                if not server.succeeded:
                    raise ProbeError(server.error or "Authorization timed out")
                print(f"Private report: {directory / 'report.json'}")
                if args.mapping_source:
                    print(
                        f"Candidate only (not observed Keystone transport): {directory / 'mapping-input.txt'}"
                    )
        return 0
    except ProbeError as exc:
        print(f"OIDC probe failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, EOFError, UnicodeError):
        print(
            "OIDC probe failed: local input/output unavailable. No credentials were logged.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
