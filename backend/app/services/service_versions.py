"""Read advertised API versions, never infer a deployed package release.

These services currently publish API discovery, not authoritative software-release
metadata. In particular OpenAPI info.version, Server headers and image tags are
not product versions. Discovery uses only this request's validated native catalog
or existing operator-owned overrides, with no authentication refresh or redirects.
"""

from __future__ import annotations

import asyncio
import json
import re
import ssl
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel

from app.config import get_settings

ServiceName = Literal["nova", "neutron", "palimpsest", "drover", "lumen", "waygate"]


class ServiceVersion(BaseModel):
    service: ServiceName
    status: Literal["available", "unavailable", "disabled"]
    version: str | None = None
    version_kind: Literal["product", "api"] | None = None


class ServiceVersions(BaseModel):
    services: list[ServiceVersion]


# Fixed service identities and enablement only; never accept a browser-selected URL.
_SERVICES = (
    ("nova", "compute", None),
    ("neutron", "network", None),
    ("palimpsest", "palimpsest", "service_palimpsest_enabled"),
    ("drover", "drover", "service_k3s_enabled"),
    ("lumen", "lumen", "service_chat_enabled"),
    ("waygate", "waygate", "service_waygate_enabled"),
)
_CONCURRENCY = 3
_TIMEOUT = 3.0
_MAX_BODY = 64 * 1024
_VERSION = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,6}){1,3}")
_SEGMENT = re.compile(r"v[0-9]+(?:\.[0-9]+)*")


def _discovery_url(endpoint: str, service: str) -> str:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in endpoint)
        or any(part in {".", ".."} for part in parsed.path.split("/"))
        or "%" in parsed.path
    ):
        raise ValueError("Invalid configured discovery endpoint")
    # Keep deployment prefixes, but never include Nova's project suffix. Neutron
    # advertises versions at its root; GET /v2.0 is only a resource index.
    parts = [part for part in parsed.path.split("/") if part]
    version_index = next((i for i, part in enumerate(parts) if _SEGMENT.fullmatch(part)), None)
    if version_index is not None:
        parts = parts[: version_index + (service != "neutron")]
    return urlunsplit((parsed.scheme, parsed.netloc, "/" + "/".join(parts) + ("/" if parts else ""), "", ""))


def _api_version(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    document = payload.get("version")
    if isinstance(document, dict):
        documents = [document]
    else:
        documents = payload.get("versions")
        if isinstance(documents, dict):
            documents = documents.get("values")
    if not isinstance(documents, list) or not 1 <= len(documents) <= 32:
        return None
    versions = []
    for entry in documents:
        if not isinstance(entry, dict) or entry.get("status") not in {"CURRENT", "SUPPORTED", "stable", "current"}:
            continue
        identity = entry.get("id")
        if not isinstance(identity, str) or not _VERSION.fullmatch(identity.removeprefix("v")):
            continue
        # Nova calls its maximum supported microversion "version". This is
        # still an API observation, not the Nova package version.
        maximum = entry.get("version")
        if maximum in (None, ""):
            maximum = identity.removeprefix("v")
        if isinstance(maximum, str) and _VERSION.fullmatch(maximum):
            versions.append(maximum)
    return max(versions, key=lambda value: tuple(map(int, value.split(".")))) if versions else None


def _native_access(conn, token_info: dict, access):
    # Reading auth_ref is offline. Never call get_access/get_endpoint here: they
    # can reissue an already scoped/restricted credential on lazy SDK sessions.
    token = getattr(conn, "_afterglow_token", None)
    if not isinstance(token, str) or not token:
        return None
    if access is None or access.auth_token != token:
        access = getattr(conn.session.auth, "auth_ref", None)
    if (
        access is None
        or access.auth_token != token
        or access.user_id != token_info.get("user_id")
        or access.user_domain_id != token_info.get("identity_domain_id")
        or access.will_expire_soon(0)
        or (access.project_id or "") != getattr(conn, "_afterglow_authenticated_project_id", None)
        or not (access.project_scoped is True or access.system_scoped is True)
        or (not access.project_id and access.system_scoped is not True)
    ):
        return None
    return access


def _endpoint(access, service_type: str, settings) -> str | None:
    override = getattr(settings, f"service_{service_type}_internal_url", "")
    if override:
        return override
    # ServiceCatalog is an already validated AccessInfo snapshot. Duplicate
    # catalog choices are ambiguous, not permission to choose another region.
    endpoints = access.service_catalog.get_endpoints(
        service_type=service_type, interface="internal", region_name=settings.os_region_name
    )
    urls = {entry["url"] for group in endpoints.values() for entry in group if isinstance(entry.get("url"), str)}
    return next(iter(urls)) if len(urls) == 1 else None


async def observe_service_versions(conn, token_info: dict, *, native_access=None) -> ServiceVersions:
    settings = get_settings()
    access = _native_access(conn, token_info, native_access)
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    headers = {"accept": "application/json", "accept-encoding": "identity"}
    if access is not None:
        headers["x-auth-token"] = access.auth_token
        if access.project_id:
            headers["x-project-id"] = access.project_id

    async def observe(service, service_type, flag):
        if flag is not None and not getattr(settings, flag):
            return ServiceVersion(service=service, status="disabled")
        unavailable = ServiceVersion(service=service, status="unavailable")
        if access is None:
            return unavailable
        async with semaphore:
            try:
                async with asyncio.timeout(_TIMEOUT):
                    endpoint = _endpoint(access, service_type, settings)
                    if not endpoint:
                        return unavailable
                    url = _discovery_url(endpoint, service)
                    verify = settings.ssl_verify
                    if service == "palimpsest":
                        verify = ssl.create_default_context(cafile=settings.os_cacert or None)
                    elif isinstance(verify, str):
                        verify = ssl.create_default_context(cafile=verify)
                    async with (
                        httpx.AsyncClient(
                            timeout=httpx.Timeout(_TIMEOUT, connect=min(_TIMEOUT, 1.0)),
                            verify=verify,
                            follow_redirects=False,
                            trust_env=False,
                        ) as client,
                        client.stream("GET", url, headers=headers) as response,
                    ):
                        if response.status_code not in {200, 300}:
                            return unavailable
                        # Refuse compression so decompression cannot allocate an
                        # unbounded body before the byte limit is enforced.
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            return unavailable
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            if len(body) + len(chunk) > _MAX_BODY:
                                return unavailable
                            body.extend(chunk)
                    version = _api_version(json.loads(body))
                    if version is not None:
                        return ServiceVersion(service=service, status="available", version=version, version_kind="api")
            except Exception:
                # Transport/auth/status/body errors remain independent unknown
                # observations. Never return their detail, URLs, headers or body.
                pass
        return unavailable

    return ServiceVersions(services=await asyncio.gather(*(observe(*service) for service in _SERVICES)))
