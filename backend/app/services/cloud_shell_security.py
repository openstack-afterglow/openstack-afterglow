"""Fail-closed consumers of native Cloud Shell isolation evidence.

The runtime label is a driver readback, not an application-signed request. Its
trust boundary is the installed native extension on every eligible compute,
which reserves it and enforces the dedicated project independently of labels.
Security-group egress is safe only together with that verified native profile;
Neutron allow rules alone cannot express the metadata/management deny policy.
"""

from __future__ import annotations

import ipaddress
import json
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

RUNTIME_PROFILE_LABEL = "afterglow.runtime_profile"
RUNTIME_PROFILE_REVISION = "cloud-shell-v1"
MANDATORY_BLOCKED_CIDRS = ("169.254.169.254/32", "fd00:ec2::254/128", "fe80::a9fe:a9fe/128")
_PROFILE_KEYS = frozenset(
    {
        "revision",
        "cpu",
        "memory_mib",
        "pids_limit",
        "readonly_rootfs",
        "tmpfs_mib",
        "shm_mib",
        "log_max_size",
        "log_max_files",
        "blocked_cidrs",
        "network_isolated",
    }
)


class CloudShellSecurityError(ValueError):
    """Native isolation evidence or the selected network policy is unsafe."""


def canonical_blocked_cidrs(value: object) -> list[str]:
    """Validate an explicit canonical deny list without silently adding routes."""
    if type(value) is not list or not value or len(value) > 64:
        raise ValueError("cloud_shell.blocked_cidrs must be a nonempty CIDR list (at most 64)")
    result = []
    for cidr in value:
        if type(cidr) is not str:
            raise ValueError("cloud_shell.blocked_cidrs entries must be canonical CIDR strings")
        try:
            network = ipaddress.ip_network(cidr, strict=True)
        except ValueError:
            raise ValueError("cloud_shell.blocked_cidrs entries must be canonical CIDRs") from None
        if str(network) != cidr:
            raise ValueError("cloud_shell.blocked_cidrs entries must be canonical CIDRs")
        result.append(cidr)
    if len(set(result)) != len(result) or not set(MANDATORY_BLOCKED_CIDRS).issubset(result):
        raise ValueError("cloud_shell.blocked_cidrs must include all metadata routes without duplicates")
    return sorted(result)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CloudShellSecurityError("Cloud Shell runtime profile has duplicate fields")
        result[key] = value
    return result


def verify_runtime_profile(container: dict, settings: Settings) -> None:
    """Require an exact native readback matching the configured fixed profile."""
    if type(container) is not dict or type(container.get("labels")) is not dict:
        raise CloudShellSecurityError("Cloud Shell native runtime profile is unavailable")
    raw = container["labels"].get(RUNTIME_PROFILE_LABEL)
    if type(raw) is not str or not raw or len(raw) > 32768:
        raise CloudShellSecurityError("Cloud Shell native runtime profile is unavailable")
    try:
        profile = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError):
        raise CloudShellSecurityError("Cloud Shell native runtime profile is malformed") from None
    if type(profile) is not dict or set(profile) != _PROFILE_KEYS:
        raise CloudShellSecurityError("Cloud Shell native runtime profile schema is unsupported")
    expected_cpu = settings.cloud_shell_cpu
    cpu = profile["cpu"]
    if (
        type(cpu) not in (int, float)
        or not 0 < cpu <= 1
        or not math.isfinite(cpu)
        or int(cpu * 100000) < 1000
        or type(expected_cpu) not in (int, float)
        or not 0 < expected_cpu <= 1
        or not math.isfinite(expected_cpu)
        or int(expected_cpu * 100000) < 1000
        or cpu != expected_cpu
    ):
        raise CloudShellSecurityError("Cloud Shell native CPU quota does not match")
    memory = profile["memory_mib"]
    if (
        type(memory) is not int
        or not 256 <= memory <= 1024
        or type(settings.cloud_shell_memory_mib) is not int
        or memory != settings.cloud_shell_memory_mib
    ):
        raise CloudShellSecurityError("Cloud Shell native memory limit does not match")
    fixed = {
        "revision": RUNTIME_PROFILE_REVISION,
        "pids_limit": 512,
        "readonly_rootfs": True,
        "tmpfs_mib": 128,
        "shm_mib": 64,
        "log_max_size": "8m",
        "log_max_files": 3,
        "network_isolated": True,
    }
    if any(type(profile[key]) is not type(value) or profile[key] != value for key, value in fixed.items()):
        raise CloudShellSecurityError("Cloud Shell native runtime controls do not match")
    try:
        expected_cidrs = canonical_blocked_cidrs(settings.cloud_shell_blocked_cidrs)
        observed_cidrs = canonical_blocked_cidrs(profile["blocked_cidrs"])
    except ValueError:
        raise CloudShellSecurityError("Cloud Shell native network deny policy is malformed") from None
    if profile["blocked_cidrs"] != observed_cidrs or observed_cidrs != expected_cidrs:
        raise CloudShellSecurityError("Cloud Shell native network deny policy does not match")


def _observed_fields(resource: object) -> Mapping:
    from openstack.resource import Resource

    # Resource's Mapping facade can synthesize absent defaults. In particular a
    # missing native rule list must never become an apparently safe empty list.
    if isinstance(resource, Resource):
        return resource._body.attributes
    if type(resource) is dict:
        return resource
    raise CloudShellSecurityError("Cloud Shell security group response is unsupported")


def validate_security_group(group: object) -> None:
    """Reject ingress/lateral policies; egress requires native deny enforcement.

    The caller must resolve exact project ownership and verify_runtime_profile
    before user code or credentials are admitted. This does not create rules,
    infer that a default group is safe, or claim an SG denies metadata egress.
    """
    fields = _observed_fields(group)
    group_id = fields.get("id")
    rules = fields.get("security_group_rules")
    if type(group_id) is not str or not group_id or type(rules) is not list:
        raise CloudShellSecurityError("Cloud Shell security group rules are unavailable")
    allowed_fields = {
        "id",
        "security_group_id",
        "project_id",
        "tenant_id",
        "direction",
        "ethertype",
        "protocol",
        "port_range_min",
        "port_range_max",
        "remote_ip_prefix",
        "remote_group_id",
        "remote_address_group_id",
        "description",
        "revision_number",
        "created_at",
        "updated_at",
        "standard_attr_id",
        "belongs_to_default_sg",
        "normalized_cidr",
        "tags",
    }
    required_fields = {
        "id",
        "security_group_id",
        "direction",
        "ethertype",
        "protocol",
        "port_range_min",
        "port_range_max",
        "remote_ip_prefix",
        "remote_group_id",
    }
    seen = set()
    for resource in rules:
        rule = _observed_fields(resource)
        if not required_fields.issubset(rule) or set(rule) - allowed_fields or rule.get("direction") != "egress":
            raise CloudShellSecurityError("Cloud Shell security group must contain only known egress rules")
        identifier = rule.get("id")
        if (
            type(identifier) is not str
            or not identifier
            or identifier in seen
            or rule.get("security_group_id") != group_id
            or rule.get("ethertype") not in ("IPv4", "IPv6")
            or rule.get("remote_group_id") is not None
            or rule.get("remote_address_group_id") is not None
        ):
            raise CloudShellSecurityError("Cloud Shell security group rule is malformed or lateral")
        seen.add(identifier)
        if "tags" in rule and (type(rule["tags"]) is not list or any(type(tag) is not str for tag in rule["tags"])):
            raise CloudShellSecurityError("Cloud Shell security group rule tags are malformed")
        protocol = rule.get("protocol")
        if protocol is not None and (
            type(protocol) is not str or protocol not in {"tcp", "udp", "icmp", "ipv6-icmp", "icmpv6"}
        ):
            raise CloudShellSecurityError("Cloud Shell security group protocol is unsupported")
        low, high = rule.get("port_range_min"), rule.get("port_range_max")
        if low is not None or high is not None:
            ceiling = 65535 if protocol in {"tcp", "udp"} else 255
            if (
                protocol is None
                or type(low) is not int
                or type(high) is not int
                or not 0 <= low <= ceiling
                or not 0 <= high <= ceiling
                or (protocol in {"tcp", "udp"} and (low == 0 or high < low))
            ):
                raise CloudShellSecurityError("Cloud Shell security group port range is malformed")
        prefix = rule.get("remote_ip_prefix")
        if prefix is not None:
            try:
                network = ipaddress.ip_network(prefix, strict=True) if type(prefix) is str else None
            except ValueError:
                network = None
            if network is None or network.version != (4 if rule["ethertype"] == "IPv4" else 6):
                raise CloudShellSecurityError("Cloud Shell security group destination is malformed")
