"""Authenticate Afterglow's Keystone ingress to Lumen."""

import hashlib
import hmac
import time

import httpx
from pydantic import SecretStr

HEADER = "X-Lumen-Ingress"


def sign_lumen_ingress(
    secret: bytes, *, timestamp: int, method: str, path: bytes, token: str, project: str, target_project: str
) -> str:
    """Sign the exact upstream raw path and forwarded Keystone headers, without the query."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    message = b"\n".join(
        (
            b"v1",
            str(timestamp).encode(),
            method.upper().encode(),
            path,
            token_hash.encode(),
            project.encode(),
            target_project.encode(),
        )
    )
    signature = hmac.digest(secret, message, "sha256").hex()
    return f"v1:{timestamp}:{signature}"


def attach_lumen_ingress(headers: dict[str, str], *, secret: SecretStr, method: str, url: str | httpx.URL) -> None:
    """Attach only to trusted Lumen requests, after the native headers and URL are resolved."""
    value = secret.get_secret_value()
    token = headers.get("x-auth-token")
    if not value or not token:
        return
    raw_path = httpx.URL(url).raw_path.partition(b"?")[0]
    headers[HEADER] = sign_lumen_ingress(
        value.encode(),
        timestamp=int(time.time()),
        method=method,
        path=raw_path,
        token=token,
        project=headers.get("x-project-id", ""),
        target_project=headers.get("x-target-project-id", ""),
    )
