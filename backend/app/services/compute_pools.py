"""Afterglow domain compute admission policy; stock Nova remains the allocator.

The service is not a caller authorization substitute: eligibility callers must
retain their existing project/admin/service guards. Cross-project observations
always use a configured operator, never elevated access on a tenant connection.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from contextlib import asynccontextmanager
from functools import cached_property
from urllib.parse import quote, urlencode, urlsplit

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.compute_pools import IDENTIFIER_PATTERN, MAX_AMOUNT, MAX_PROJECTS, NativePoolPolicy
from app.services import flavor_automation_policy, identity_roles, keystone

POLICY_KEY = "afterglow_compute_pool"
_MAX_BYTES = 1_048_576
_MAX_PAGES = 128
_PCI = re.compile(r"^CUSTOM_PCI_([0-9A-F]{4})_([0-9A-F]{4})$")


class ComputePoolUnavailable(Exception):
    """Policy, native directory or complete accounting cannot be proven."""


class ComputePoolDenied(Exception):
    """A verified shared pool or optional project ceiling is exhausted."""

    def __init__(self, blockers):
        self.blockers = blockers
        super().__init__("compute_pool_denied")


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ComputePoolUnavailable("compute_pool_identity_invalid")
    return value


def _pci_resource(resource):
    """Syntax only: GPU approval comes exclusively from administrator policy."""
    return isinstance(resource, str) and _PCI.fullmatch(resource) is not None


def normalize_policy(value):
    """Validate an immutable raw native metadata object; absent means unmanaged."""
    if value is None:
        return {"schema": 1, "revision": 0, "enabled": False, "limits": {}, "project_limits": {}}
    try:
        if not isinstance(value, dict) or type(value.get("schema")) is not int:
            raise ValueError("policy object/schema")
        policy = NativePoolPolicy.model_validate(value).model_dump(by_alias=True)
        if len(json.dumps(policy, separators=(",", ":"))) > _MAX_BYTES:
            raise ValueError("policy size")
        for resource in set(policy["limits"]) | {k for caps in policy["project_limits"].values() for k in caps}:
            if resource not in {"CPU", "MEMORY_MB"} and not _pci_resource(resource):
                raise ValueError("invalid physical PCI resource")
        _validate_caps(policy)
        return policy
    except (ValidationError, ValueError, TypeError) as exc:
        raise ComputePoolUnavailable("compute_pool_policy_invalid") from exc


def _domain_metadata(domain):
    from openstack.resource import Resource

    if isinstance(domain, Resource):
        raise ComputePoolUnavailable("compute_pool_raw_domain_metadata_required")
    info = getattr(domain, "_info", None)
    source = info if isinstance(info, Mapping) else domain
    if isinstance(source, Mapping) and POLICY_KEY in source:
        return True, source[POLICY_KEY]
    value = getattr(domain, POLICY_KEY, None)
    return value is not None, value


def parse_domain_policy(domain):
    """Read raw Keystone metadata without relying on lossy SDK dict snapshots."""
    present, value = _domain_metadata(domain)
    if present and value is None:
        raise ComputePoolUnavailable("compute_pool_policy_invalid")
    return normalize_policy(value)


def domain_pool_state(domain):
    present, _ = _domain_metadata(domain)
    policy = parse_domain_policy(domain)
    return "unmanaged" if not present else "active" if policy["enabled"] else "paused"


def _validate_caps(policy):
    for caps in policy["project_limits"].values():
        for resource, cap in caps.items():
            ceiling = policy["limits"].get(resource, -1 if resource in {"CPU", "MEMORY_MB"} else 0)
            if ceiling != -1 and (cap == -1 or cap > ceiling):
                raise ValueError("compute_pool_project_cap_exceeds_pool")


class _Native:
    def __init__(self, conn):
        self.conn = conn
        self.deadline = time.monotonic() + 45

    @cached_property
    def identity(self):
        return self._service_endpoint("identity")

    @cached_property
    def placement(self):
        return self._service_endpoint("placement")

    def _service_endpoint(self, service):
        try:
            proxy = getattr(self.conn, service)
            endpoint = proxy.get_endpoint_data().url if service == "identity" else proxy.get_endpoint()
            return self._endpoint(endpoint)
        except Exception as exc:
            raise ComputePoolUnavailable("compute_pool_endpoint_unavailable") from exc

    @staticmethod
    def _endpoint(value):
        if not isinstance(value, str) or urlsplit(value).scheme not in {"http", "https"}:
            raise ComputePoolUnavailable("compute_pool_endpoint_unavailable")
        return value.rstrip("/")

    def request(self, method, url, *, version=None, body=None, missing_ok=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ComputePoolUnavailable("compute_pool_native_deadline")
        headers = {"Accept": "application/json"}
        if version:
            headers["OpenStack-API-Version"] = version
        try:
            response = self.conn.session.request(
                url,
                method,
                json=body,
                headers=headers,
                timeout=min(8, remaining),
                connect_retries=0,
                status_code_retries=0,
                allow_reauth=False,
                redirect=False,
                raise_exc=False,
                stream=True,
            )
        except Exception as exc:
            raise ComputePoolUnavailable("compute_pool_native_transport_unavailable") from exc
        try:
            if missing_ok and response.status_code == 404:
                return None
            if type(response.status_code) is not int or not 200 <= response.status_code < 300:
                raise ComputePoolUnavailable("compute_pool_native_http_unavailable")
            chunks = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                if len(chunks) + len(chunk) > _MAX_BYTES:
                    raise ComputePoolUnavailable("compute_pool_native_response_too_large")
                chunks.extend(chunk)
            result = json.loads(chunks)
            if not isinstance(result, dict):
                raise ComputePoolUnavailable("compute_pool_native_response_invalid")
            return result
        except ComputePoolUnavailable:
            raise
        except Exception as exc:
            raise ComputePoolUnavailable("compute_pool_native_response_invalid") from exc
        finally:
            response.close()

    def exact(self, kind, object_id, *, missing_ok=False):
        object_id = _identifier(object_id)
        body = self.request("GET", f"{self.identity}/{kind}/{quote(object_id, safe='')}", missing_ok=missing_ok)
        if body is None:
            return None
        row = body.get(kind[:-1])
        if not isinstance(row, dict) or row.get("id") != object_id or type(row.get("enabled")) is not bool:
            raise ComputePoolUnavailable("compute_pool_native_identity_mismatch")
        return row

    def projects(self, domain_id):
        url = self.identity + "/projects?" + urlencode({"domain_id": domain_id})
        seen_urls, projects = set(), {}
        for _ in range(_MAX_PAGES):
            if url in seen_urls:
                raise ComputePoolUnavailable("compute_pool_directory_pagination_invalid")
            seen_urls.add(url)
            result = self.request("GET", url)
            rows = result.get("projects")
            if result.get("truncated") not in (None, False) or result.get("limited") not in (None, False):
                raise ComputePoolUnavailable("compute_pool_directory_completeness_unknown")
            if not isinstance(rows, list):
                raise ComputePoolUnavailable("compute_pool_directory_invalid")
            for row in rows:
                if not isinstance(row, dict):
                    raise ComputePoolUnavailable("compute_pool_directory_invalid")
                pid = _identifier(row.get("id"))
                if (
                    pid in projects
                    or row.get("domain_id") != domain_id
                    or type(row.get("enabled")) is not bool
                    or not isinstance(row.get("name"), str)
                    or len(row["name"]) > 255
                ):
                    raise ComputePoolUnavailable("compute_pool_directory_invalid")
                projects[pid] = {"id": pid, "name": row["name"], "enabled": row["enabled"]}
                if len(projects) > MAX_PROJECTS:
                    raise ComputePoolUnavailable("compute_pool_directory_limit")
            links = result.get("links")
            if not isinstance(links, dict) or "next" not in links:
                raise ComputePoolUnavailable("compute_pool_directory_completeness_unknown")
            if len(seen_urls) == 1 and links.get("previous") is not None:
                raise ComputePoolUnavailable("compute_pool_directory_completeness_unknown")
            next_url = links["next"]
            if next_url is None:
                return list(projects.values())
            expected = urlsplit(self.identity + "/projects")
            parsed = urlsplit(next_url) if isinstance(next_url, str) else None
            if (
                not rows
                or parsed is None
                or (parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path)
                or parsed.fragment
            ):
                raise ComputePoolUnavailable("compute_pool_directory_pagination_invalid")
            # Follow only the native same-origin directory URL. Every returned row
            # remains domain-checked; a provider dropping its filter cannot leak use.
            url = next_url
        raise ComputePoolUnavailable("compute_pool_directory_limit")

    def raw_usage(self, project_id):
        body = self.request(
            "GET", self.placement + "/usages?" + urlencode({"project_id": project_id}), version="placement 1.9"
        )
        raw = body.get("usages")
        if not isinstance(raw, dict) or len(raw) > 512:
            raise ComputePoolUnavailable("compute_pool_usage_invalid")
        if any(
            not isinstance(resource, str) or type(amount) is not int or not 0 <= amount <= MAX_AMOUNT
            for resource, amount in raw.items()
        ):
            raise ComputePoolUnavailable("compute_pool_usage_invalid")
        return raw

    def usage(self, project_id, *, resource_kinds=None):
        raw = self.raw_usage(project_id)
        usage = {"CPU": 0, "MEMORY_MB": 0}
        for resource, amount in raw.items():
            if resource in {"VCPU", "PCPU"}:
                usage["CPU"] += amount
            elif resource == "MEMORY_MB":
                usage[resource] = amount
            elif _PCI.fullmatch(resource):
                kind = (resource_kinds or {}).get(resource)
                if kind == "gpu":
                    usage[resource] = amount
                elif kind != "companion":
                    raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified")
            elif (resource_kinds or {}).get(resource) == "companion":
                continue
            elif resource in {"VGPU", "PGPU"} or resource.startswith("CUSTOM_"):
                raise ComputePoolUnavailable("compute_pool_gpu_accounting_unsupported")
        return usage


def _resource_kinds(capabilities):
    kinds = dict(capabilities.get("resource_kinds", {}))
    for alias in capabilities["pci_aliases"]:
        resource = alias["resource_class"]
        if alias.get("classification_verified") is not True or not _pci_resource(resource):
            continue
        gpu = alias.get("is_gpu") is True
        companion = alias.get("is_companion") is True or alias.get("is_audio") is True
        if not gpu and not companion:
            continue
        if gpu and companion:
            raise ComputePoolUnavailable("compute_pool_pci_classification_conflict")
        kind = "gpu" if gpu else "companion"
        if resource in kinds and kinds[resource] != kind:
            raise ComputePoolUnavailable("compute_pool_pci_classification_conflict")
        kinds[resource] = kind
    return kinds


@asynccontextmanager
async def _operator():
    try:
        conn = await asyncio.to_thread(keystone.get_admin_project_connection)
    except Exception as exc:
        raise ComputePoolUnavailable("compute_pool_operator_unavailable") from exc
    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)


def _remaining(limits, usage, keys):
    return {
        key: -1
        if limits.get(key, -1 if key in {"CPU", "MEMORY_MB"} else 0) == -1
        else max(0, limits.get(key, 0) - usage.get(key, 0))
        for key in keys
    }


async def _project_usages(projects, resource_kinds, deadline):
    """Read every project with at most four independently owned SDK sessions."""
    pending = iter(projects)

    async def worker():
        project = next(pending, None)
        if project is None:
            return {}
        async with _operator() as operator:
            client = _Native(operator)
            client.deadline = deadline
            result = {}
            while project is not None:
                result[project["id"]] = await asyncio.to_thread(
                    client.usage, project["id"], resource_kinds=resource_kinds
                )
                project = next(pending, None)
            return result

    # Drain every worker before exposing a failure or closing its connection.
    # The enclosing public read is shielded through cancellation, including
    # worker connection acquisition and teardown. No partial usage can escape.
    results = await asyncio.gather(*(worker() for _ in range(min(4, len(projects)))), return_exceptions=True)
    usages = {}
    for result in results:
        if isinstance(result, BaseException):
            raise result
        usages.update(result)
    return usages


async def _snapshot(client, domain_id, capabilities, *, project_id=None, allow_stale_caps=False):
    domain = await asyncio.to_thread(client.exact, "domains", domain_id)
    if domain["enabled"] is not True:
        raise ComputePoolUnavailable("compute_pool_domain_disabled")
    policy = parse_domain_policy(domain)
    projects = await asyncio.to_thread(client.projects, domain_id)
    ids = {p["id"] for p in projects}
    stale = sorted(set(policy["project_limits"]) - ids)
    if stale or (project_id is not None and project_id not in ids):
        if not allow_stale_caps or project_id is not None:
            raise ComputePoolUnavailable("compute_pool_project_directory_mismatch")
        return {
            "domain_id": domain_id,
            "state": domain_pool_state(domain),
            **policy,
            "usage": {},
            "available": {},
            "projects": projects,
            "stale_project_caps": stale,
            "projection_unavailable": True,
            "policy_ready": False,
            "control_scope": "afterglow",
            "gpu_profiles": capabilities.get("gpu_profiles", []),
        }
    qualified = {a["resource_class"] for a in capabilities["aliases"]}
    policy_resources = set(policy["limits"]) | {rc for caps in policy["project_limits"].values() for rc in caps}
    policy_ready = capabilities.get("policy_ready") is True and not any(
        rc not in {"CPU", "MEMORY_MB"} and rc not in qualified for rc in policy_resources
    )
    resource_kinds = _resource_kinds(capabilities)
    usages = await _project_usages(projects, resource_kinds, client.deadline)
    keys = {"CPU", "MEMORY_MB"} | set(policy["limits"]) | {k for usage in usages.values() for k in usage}
    usage = {key: sum(row.get(key, 0) for row in usages.values()) for key in keys}
    result = {
        "domain_id": domain_id,
        "state": domain_pool_state(domain),
        **policy,
        "usage": usage,
        "available": _remaining(policy["limits"], usage, keys),
        "projects": projects,
        "policy_ready": policy_ready,
        "control_scope": "afterglow",
        "gpu_profiles": capabilities.get("gpu_profiles", []),
    }
    if project_id is not None:
        cap = policy["project_limits"].get(project_id, {})
        # Missing project caps inherit the pool ceiling; explicit zero is a denial.
        effective = {**policy["limits"], **cap}
        result.update(
            project_id=project_id,
            project_limits=cap,
            project_usage=usages[project_id],
            project_available=_remaining(effective, usages[project_id], keys),
            _aliases=capabilities["aliases"],
            _pci_aliases=capabilities["pci_aliases"],
            _resource_kinds=resource_kinds,
        )
    return result


async def read_pool(conn, domain_id):
    """Manager/admin projection; finish native reads before cancellation returns."""
    return await identity_roles._to_completion(_read_pool(conn, domain_id))


async def _read_pool(conn, domain_id):
    _identifier(domain_id)
    try:
        async with _operator() as operator:
            capabilities = await flavor_automation_policy.capabilities()
            return await _snapshot(_Native(operator), domain_id, capabilities, allow_stale_caps=True)
    except ComputePoolUnavailable:
        raise
    except Exception as exc:
        raise ComputePoolUnavailable("compute_pool_native_unavailable") from exc


async def project_pool_snapshot(conn, project_id):
    """Fresh operator proof; cancellation drains all independently owned reads."""
    return await identity_roles._to_completion(_project_pool_snapshot(conn, project_id))


async def _project_pool_snapshot(conn, project_id):
    _identifier(project_id)
    try:
        async with _operator() as operator:
            client = _Native(operator)
            project = await asyncio.to_thread(client.exact, "projects", project_id)
            domain_id = _identifier(project.get("domain_id"))
            # Unmanaged domains retain legacy quotas and need no Placement proof.
            domain = await asyncio.to_thread(client.exact, "domains", domain_id)
            policy = parse_domain_policy(domain)
            state = domain_pool_state(domain)
            if state == "unmanaged":
                return {
                    "domain_id": domain_id,
                    "state": state,
                    "enabled": False,
                    "policy_ready": False,
                    "control_scope": "afterglow",
                    "selectable": True,
                    "blockers": [],
                    "limits": policy["limits"],
                    "usage": {},
                    "available": {},
                    "project_limits": {},
                    "project_usage": {},
                    "project_available": {},
                    "_aliases": [],
                    "_pci_aliases": [],
                }
            if state == "paused":
                return {
                    "domain_id": domain_id,
                    "state": state,
                    "enabled": False,
                    "policy_ready": False,
                    "control_scope": "afterglow",
                    "selectable": False,
                    "blockers": [],
                    "limits": policy["limits"],
                    "usage": {},
                    "available": {},
                    "project_limits": policy["project_limits"].get(project_id, {}),
                    "project_usage": {},
                    "project_available": {},
                    "_aliases": [],
                    "_pci_aliases": [],
                }
            if project["enabled"] is not True:
                raise ComputePoolUnavailable("compute_pool_project_disabled")
            capabilities = await flavor_automation_policy.capabilities()
            return await _snapshot(client, domain_id, capabilities, project_id=project_id)
    except ComputePoolUnavailable:
        raise
    except Exception as exc:
        raise ComputePoolUnavailable("compute_pool_native_unavailable") from exc


def _requirements(values):
    if not isinstance(values, dict) or len(values) > 128:
        raise ComputePoolUnavailable("compute_pool_requirements_invalid")
    result = {}
    for resource, amount in values.items():
        if type(amount) is not int or not 0 <= amount <= MAX_AMOUNT:
            raise ComputePoolUnavailable("compute_pool_requirements_invalid")
        key = "CPU" if resource in {"CPU", "VCPU", "PCPU"} else resource
        if key not in {"CPU", "MEMORY_MB"} and not _pci_resource(key):
            raise ComputePoolUnavailable("compute_pool_requirements_unsupported")
        result[key] = result.get(key, 0) + amount
        if result[key] > MAX_AMOUNT:
            raise ComputePoolUnavailable("compute_pool_requirements_invalid")
    return result


def evaluate_pool_snapshot(snapshot, requirements, current_requirements=None):
    """Pure projection from one snapshot; current demand subtracts only positive delta."""
    public = {
        k: snapshot[k]
        for k in (
            "domain_id",
            "state",
            "enabled",
            "policy_ready",
            "control_scope",
            "limits",
            "usage",
            "available",
            "project_limits",
            "project_usage",
            "project_available",
        )
    }
    if snapshot["state"] == "unmanaged":
        return {**public, "selectable": True, "blockers": []}
    if snapshot["state"] == "paused":
        return {
            **public,
            "selectable": False,
            "blockers": [{"code": "domain_pool_paused", "resource": "CPU", "required": 0, "available": 0}],
        }
    requested = _requirements(requirements)
    current = _requirements(current_requirements or {})
    blockers = []
    if snapshot.get("policy_ready") is not True:
        raise ComputePoolUnavailable("compute_pool_policy_unavailable")
    qualified = {alias["resource_class"] for alias in snapshot.get("_aliases", [])}
    if any(_pci_resource(rc) and rc not in qualified for rc in requested.keys() | current.keys()):
        raise ComputePoolUnavailable("compute_pool_gpu_alias_unverified")
    for resource, amount in requested.items():
        delta = max(0, amount - current.get(resource, 0))
        available = snapshot["available"].get(resource, 0)
        if available != -1 and delta > available:
            blockers.append(
                {"code": "domain_pool_exhausted", "resource": resource, "required": delta, "available": available}
            )
        cap = snapshot["project_limits"].get(resource)
        if cap is not None and cap != -1:
            project_available = max(0, cap - snapshot["project_usage"].get(resource, 0))
            if delta > project_available:
                blockers.append(
                    {
                        "code": "project_pool_ceiling_exhausted",
                        "resource": resource,
                        "required": delta,
                        "available": project_available,
                    }
                )
    return {**public, "selectable": not blockers, "blockers": blockers}


async def evaluate_project_pool(conn, project_id, requirements, *, current_requirements=None):
    return evaluate_pool_snapshot(await project_pool_snapshot(conn, project_id), requirements, current_requirements)


async def require_project_pool(conn, project_id, requirements, *, current_requirements=None):
    result = await evaluate_project_pool(conn, project_id, requirements, current_requirements=current_requirements)
    if not result["selectable"]:
        raise ComputePoolDenied(result["blockers"])
    return result


async def flavor_pool_requirements(conn, flavor, count=1, *, snapshot=None):
    """Translate exact approved aliases/resources, never model or display-name guesses."""
    if type(count) is not int or not 1 <= count <= 1000:
        raise ComputePoolUnavailable("compute_pool_count_invalid")

    def field(key, default=None):
        value = getattr(flavor, key, None)
        return value if value is not None else flavor.get(key, default) if isinstance(flavor, dict) else default

    vcpus, ram = field("vcpus"), field("ram")
    if type(vcpus) is not int or type(ram) is not int or min(vcpus, ram) < 0:
        raise ComputePoolUnavailable("compute_pool_flavor_invalid")
    specs = field("extra_specs", {})
    if not isinstance(specs, dict):
        raise ComputePoolUnavailable("compute_pool_flavor_invalid")
    if specs.get("hw:cpu_policy") == "mixed" or specs.get("hw:emulator_threads_policy") == "isolate":
        raise ComputePoolUnavailable("compute_pool_cpu_pinning_projection_unsupported")
    result = {"CPU": vcpus * count, "MEMORY_MB": ram * count}
    if snapshot is None:
        capability = await flavor_automation_policy.capabilities()
        kinds = _resource_kinds(capability)
        pci_aliases = capability["pci_aliases"]
    else:
        pci_aliases = snapshot.get("_pci_aliases", [])
        kinds = snapshot.get("_resource_kinds") or _resource_kinds({"pci_aliases": pci_aliases})
    explicit = {}
    explicit_resources = set()
    for key, value in specs.items():
        if not isinstance(key, str):
            raise ComputePoolUnavailable("compute_pool_flavor_invalid")
        match = re.fullmatch(r"resources(?:[A-Za-z0-9_-]{1,64})?:(.+)", key)
        if not match:
            continue
        resource = match[1]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value):
            raise ComputePoolUnavailable("compute_pool_flavor_resources_invalid")
        amount = int(value) * count
        explicit_resources.add(resource)
        if resource in {"VCPU", "PCPU", "MEMORY_MB"}:
            if not key.startswith("resources:"):
                # Numbered groups add demand to the base flavor request; they
                # cannot replace it like the unsuffixed CPU/RAM overrides.
                raise ComputePoolUnavailable("compute_pool_grouped_base_resources_unsupported")
            resource = "CPU" if resource in {"VCPU", "PCPU"} else resource
            explicit[resource] = explicit.get(resource, 0) + amount
        elif kinds.get(resource) == "gpu":
            explicit[resource] = explicit.get(resource, 0) + amount
        elif kinds.get(resource) == "companion":
            # Explicit administrator-approved companion, not a GPU budget.
            continue
        elif resource in {"VGPU", "PGPU"} or resource.startswith("CUSTOM_"):
            raise ComputePoolUnavailable("compute_pool_gpu_accounting_unsupported")
    result.update(explicit)
    raw_alias = specs.get("pci_passthrough:alias")
    if raw_alias is not None:
        if not isinstance(raw_alias, str) or not raw_alias or len(raw_alias) > 4096:
            raise ComputePoolUnavailable("compute_pool_flavor_alias_invalid")
        mapping = {row["name"]: row["resource_class"] for row in pci_aliases if not row.get("display_only")}
        alias_demand = {}
        seen_aliases = set()
        for item in raw_alias.split(","):
            pair = item.strip().rsplit(":", 1)
            if len(pair) != 2 or not re.fullmatch(r"[1-9][0-9]{0,5}", pair[1]) or pair[0] not in mapping:
                raise ComputePoolUnavailable("compute_pool_flavor_alias_unverified")
            if pair[0] in seen_aliases:
                raise ComputePoolUnavailable("compute_pool_flavor_alias_unverified")
            seen_aliases.add(pair[0])
            resource = mapping[pair[0]]
            if resource in explicit_resources:
                # Nova adds alias-generated groups alongside explicit resource groups.
                # Even equal quantities are separate allocations, never annotations.
                raise ComputePoolUnavailable("compute_pool_flavor_gpu_contradiction")
            if kinds.get(resource) == "gpu":
                alias_demand[resource] = alias_demand.get(resource, 0) + int(pair[1]) * count
            elif kinds.get(resource) != "companion":
                raise ComputePoolUnavailable("compute_pool_flavor_alias_unverified")
        for resource, amount in alias_demand.items():
            result[resource] = amount
    return _requirements(result)


async def approved_gpu_requirements(extra_specs, capabilities):
    """Project GPU metrics from exact approval without CPU admission/name inference."""
    if not isinstance(extra_specs, dict) or capabilities.get("policy_ready") is not True:
        raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified")
    request_specs = {
        key: value
        for key, value in extra_specs.items()
        if isinstance(key, str) and (key.startswith("resources") or key == "pci_passthrough:alias")
    }
    kinds = _resource_kinds(capabilities)
    requirements = await flavor_pool_requirements(
        None,
        {"vcpus": 0, "ram": 0, "extra_specs": request_specs},
        snapshot={"_pci_aliases": capabilities["pci_aliases"], "_resource_kinds": kinds},
    )
    return {resource: amount for resource, amount in requirements.items() if kinds.get(resource) == "gpu"}


async def approved_gpu_projection(extra_specs, capabilities):
    """Count approved primary devices and preserve exact native alias evidence."""
    from app.models.flavor_automation import RESOURCE_SPEC_PATTERN, alias_counts

    requirements = await approved_gpu_requirements(extra_specs, capabilities)
    if extra_specs.get("afterglow:frontend_visible") == "false":
        raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified")

    request = {key: value for key, value in extra_specs.items() if not key.startswith("afterglow:")}
    if requirements:
        try:
            requested_aliases = alias_counts(request)
        except ValueError as exc:
            raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified") from exc
        matched = []
        for profile in capabilities.get("gpu_profiles", []):
            count = requirements.get(profile["resource_class"])
            if not profile.get("enabled") or not count or len(requirements) != 1:
                continue
            expected = dict(profile["extra_specs"])
            try:
                expected_aliases = alias_counts(expected)
            except ValueError as exc:
                raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified") from exc
            scaled_aliases = {name: amount * count for name, amount in expected_aliases.items()}
            for key in expected:
                if RESOURCE_SPEC_PATTERN.fullmatch(key):
                    expected[key] = str(int(expected[key]) * count)
            # Alias ordering is not identity; each exact name and quantity is.
            if requested_aliases != scaled_aliases:
                continue
            if {key: value for key, value in request.items() if key != "pci_passthrough:alias"} != {
                key: value for key, value in expected.items() if key != "pci_passthrough:alias"
            }:
                continue
            matched.append(profile["name"])
        if len(matched) != 1:
            raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified")
    elif extra_specs.get("afterglow:access_mode") == "gpu_quota" or any(
        key.startswith("resources") or key == "pci_passthrough:alias" for key in request
    ):
        raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified")
    primary = {
        row["name"]: row
        for row in capabilities["pci_aliases"]
        if row.get("is_gpu") is True and not row.get("display_only")
    }
    aliases = []
    for entry in extra_specs.get("pci_passthrough:alias", "").split(","):
        if not entry:
            continue
        name, count = entry.strip().rsplit(":", 1)
        row = primary.get(name)
        if row is not None:
            if not isinstance(row.get("profile_name"), str) or not row["profile_name"]:
                raise ComputePoolUnavailable("compute_pool_gpu_accounting_unqualified")
            aliases.append(
                {
                    "name": name,
                    "count": int(count),
                    "resource_class": row["resource_class"],
                    "profile_name": row["profile_name"],
                }
            )
    count = sum(requirements.values())
    return {"gpu_count": count, "is_gpu": count > 0, "gpu_primary_aliases": aliases}


async def _authorize(token_info, domain_id, *, system):
    from app.api.deps import require_admin
    from app.services import domain_iam

    if system:
        await require_admin(dict(token_info))
    else:
        if token_info.get("domain_id") != domain_id:
            raise HTTPException(403, "compute_pool_domain_mismatch")
        context = await domain_iam.context(token_info)
        if context.get("domain_id") != domain_id:
            raise HTTPException(403, "compute_pool_domain_mismatch")


@identity_roles._complete_mutation
async def update_pool(conn, domain_id, revision, enabled, limits, *, token_info):
    return await _mutate(domain_id, revision, token_info=token_info, system=True, enabled=enabled, limits=limits)


@identity_roles._complete_mutation
async def update_project_limits(conn, domain_id, project_id, revision, limits, *, token_info, system=False):
    return await _mutate(
        domain_id, revision, token_info=token_info, system=system, project_id=project_id, limits=limits
    )


@identity_roles._complete_mutation
async def delete_project_limits(conn, domain_id, project_id, revision, *, token_info, system=False):
    return await _mutate(domain_id, revision, token_info=token_info, system=system, project_id=project_id, limits=None)


async def _require_policy_writer():
    capabilities = await flavor_automation_policy.capabilities()
    if capabilities.get("policy_ready") is not True:
        raise HTTPException(409, "compute_pool_policy_unavailable")
    return capabilities


async def assert_project_pool_deletion_ready(domain_id, project_id, *, lease):
    """Check cleanup prerequisites under the caller's existing graph lease.

    This never removes or relaxes a cap before native deletion succeeds.
    """
    _identifier(domain_id)
    _identifier(project_id)
    await lease.assert_owned()
    async with _operator() as operator:
        client = _Native(operator)
        domain = await asyncio.to_thread(client.exact, "domains", domain_id)
        policy = parse_domain_policy(domain)
        if project_id not in policy["project_limits"]:
            return False
        project = await asyncio.to_thread(client.exact, "projects", project_id)
        if project.get("domain_id") != domain_id:
            raise HTTPException(403, "compute_pool_project_domain_mismatch")
        if policy["revision"] >= MAX_AMOUNT:
            raise HTTPException(409, "compute_pool_revision_exhausted")
        await _require_policy_writer()
        await lease.assert_owned()
        return True


async def _prove_deleted_project(client, domain_id, project_id, *, projects=None):
    """Require exact404, complete home directory absence and zero ALL allocations."""
    exact = await asyncio.to_thread(client.exact, "projects", project_id, missing_ok=True)
    if exact is not None:
        if exact.get("domain_id") != domain_id:
            raise HTTPException(403, "compute_pool_project_domain_mismatch")
        raise HTTPException(409, "compute_pool_project_still_present")
    if projects is None:
        projects = await asyncio.to_thread(client.projects, domain_id)
    if any(project["id"] == project_id for project in projects):
        raise ComputePoolUnavailable("compute_pool_project_deletion_unverified")
    raw = await asyncio.to_thread(client.raw_usage, project_id)
    if any(amount != 0 for amount in raw.values()):
        raise ComputePoolUnavailable("compute_pool_deleted_project_allocations_remaining")
    return projects


async def cleanup_deleted_project_limits(domain_id, project_id, *, lease):
    """Remove only a positively deleted project's cap under the caller's SAME lease.

    Caller invokes this only after its authorized native DELETE returns. Unknown
    DELETE outcomes leave the cap intact; explicit cap DELETE provides recovery.
    """
    _identifier(domain_id)
    _identifier(project_id)
    await lease.assert_owned()
    async with _operator() as operator:
        client = _Native(operator)
        before = await asyncio.to_thread(client.exact, "domains", domain_id)
        policy = parse_domain_policy(before)
        result = {"domain_id": domain_id, "project_id": project_id, "revision": policy["revision"], "changed": False}
        if project_id not in policy["project_limits"]:
            return result
        if policy["revision"] >= MAX_AMOUNT:
            raise HTTPException(409, "compute_pool_revision_exhausted")
        await _require_policy_writer()
        projects = await _prove_deleted_project(client, domain_id, project_id)
        del policy["project_limits"][project_id]
        policy["revision"] += 1
        client = _Native(operator)
        fresh = await asyncio.to_thread(client.exact, "domains", domain_id)
        if fresh.get(POLICY_KEY) != before.get(POLICY_KEY):
            raise HTTPException(409, "compute_pool_revision_conflict")
        await _prove_deleted_project(client, domain_id, project_id)
        await lease.assert_owned()
        try:
            await identity_roles._to_completion(
                asyncio.to_thread(
                    client.request,
                    "PATCH",
                    client.identity + "/domains/" + quote(domain_id, safe=""),
                    body={"domain": {POLICY_KEY: policy}},
                )
            )
            await lease.assert_owned()
            after = await asyncio.to_thread(client.exact, "domains", domain_id)
            if parse_domain_policy(after) != policy:
                raise ComputePoolUnavailable("compute_pool_write_readback_mismatch")
        except Exception as exc:
            raise HTTPException(503, "compute_pool_mutation_outcome_unknown") from exc
        finally:
            try:
                await _invalidate_projections({project_id, *(project["id"] for project in projects)})
            except Exception as exc:
                raise HTTPException(503, "compute_pool_projection_invalidation_unavailable") from exc
        return {**result, "revision": policy["revision"], "changed": True}


async def _invalidate_projections(project_ids):
    from app.services.cache import invalidate

    for project_id in project_ids:
        for key in (
            f"afterglow:nova:{project_id}:flavors",
            f"afterglow:nova:{project_id}:quota:strict",
            f"afterglow:dashboard:{project_id}:quotas",
            f"afterglow:dashboard:{project_id}:quotas:native-v2",
            f"afterglow:dashboard:{project_id}:quotas:overview",
        ):
            await invalidate(key)


async def _mutate(domain_id, revision, *, token_info, system, project_id=None, enabled=None, limits=None):
    _identifier(domain_id)
    if project_id is not None:
        _identifier(project_id)
    async with _operator() as operator, identity_roles._graph_lock(operator) as lease:
        await _authorize(token_info, domain_id, system=system)
        client = _Native(operator)
        before = await asyncio.to_thread(client.exact, "domains", domain_id)
        if not before["enabled"]:
            raise HTTPException(403, "compute_pool_domain_disabled")
        policy = parse_domain_policy(before)
        if project_id is not None and domain_pool_state(before) == "unmanaged":
            raise HTTPException(409, "compute_pool_not_configured")
        if type(revision) is not int or policy["revision"] != revision:
            raise HTTPException(409, "compute_pool_revision_conflict")
        if revision >= MAX_AMOUNT:
            raise HTTPException(409, "compute_pool_revision_exhausted")
        projects = await asyncio.to_thread(client.projects, domain_id)
        project_ids = {p["id"] for p in projects}
        recovering = project_id is not None and limits is None and project_id not in project_ids
        if set(policy["project_limits"]) - project_ids and not recovering:
            raise ComputePoolUnavailable("compute_pool_project_directory_mismatch")
        if project_id is not None:
            if recovering:
                await _prove_deleted_project(client, domain_id, project_id, projects=projects)
                if project_id not in policy["project_limits"]:
                    raise HTTPException(404, "compute_pool_project_cap_not_found")
            else:
                exact = await asyncio.to_thread(client.exact, "projects", project_id)
                if exact.get("domain_id") != domain_id or project_id not in project_ids:
                    raise HTTPException(403, "compute_pool_project_domain_mismatch")
            if limits is None:
                policy["project_limits"].pop(project_id, None)
            else:
                policy["project_limits"][project_id] = limits
        else:
            policy.update(enabled=enabled, limits=limits)
        policy["revision"] = revision + 1
        try:
            _validate_caps(policy)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        policy = normalize_policy(policy)
        capabilities = await _require_policy_writer()
        qualified = {row["resource_class"] for row in capabilities["aliases"]}
        resources = set(policy["limits"]) | {rc for caps in policy["project_limits"].values() for rc in caps}
        if any(rc not in {"CPU", "MEMORY_MB"} and rc not in qualified for rc in resources):
            raise HTTPException(409, "compute_pool_gpu_alias_unverified")
        resource_kinds = _resource_kinds(capabilities)
        # A pause/cap change still requires complete standard Placement accounting.
        # This policy controls Afterglow admission, never external Nova requests.
        for project in projects:
            await asyncio.to_thread(client.usage, project["id"], resource_kinds=resource_kinds)
        await lease.assert_owned()
        await _authorize(token_info, domain_id, system=system)
        # Fresh dispatch/readback budget, independent of usage preflight.
        client = _Native(operator)
        fresh = await asyncio.to_thread(client.exact, "domains", domain_id)
        if fresh["enabled"] is not True:
            raise HTTPException(403, "compute_pool_domain_disabled")
        if fresh.get(POLICY_KEY) != before.get(POLICY_KEY):
            raise HTTPException(409, "compute_pool_revision_conflict")
        if project_id is not None:
            if recovering:
                await _prove_deleted_project(client, domain_id, project_id)
            else:
                fresh_project = await asyncio.to_thread(client.exact, "projects", project_id)
                if fresh_project.get("domain_id") != domain_id:
                    raise HTTPException(403, "compute_pool_project_domain_mismatch")
        await lease.assert_owned()
        try:
            await identity_roles._to_completion(
                asyncio.to_thread(
                    client.request,
                    "PATCH",
                    client.identity + "/domains/" + quote(domain_id, safe=""),
                    body={"domain": {POLICY_KEY: policy}},
                )
            )
            await lease.assert_owned()
            after = await asyncio.to_thread(client.exact, "domains", domain_id)
            if parse_domain_policy(after) != policy:
                raise ComputePoolUnavailable("compute_pool_write_readback_mismatch")
        except Exception as exc:
            # Never replay a timed-out native PATCH. A fresh GET/revision is recovery.
            raise HTTPException(503, "compute_pool_mutation_outcome_unknown") from exc
        finally:
            # A lost response may have changed policy; cached projections of
            # every sibling project must be discarded even on unknown outcome.
            try:
                await _invalidate_projections(project_ids | ({project_id} if project_id is not None else set()))
            except Exception as exc:
                raise HTTPException(503, "compute_pool_projection_invalidation_unavailable") from exc
        return await _snapshot(_Native(operator), domain_id, capabilities, allow_stale_caps=True)
