"""Cloud Shell admission consumes observed native controls, never intent alone."""

import json
from types import SimpleNamespace

import pytest
from openstack.network.v2.security_group import SecurityGroup
from openstack.network.v2.security_group_rule import SecurityGroupRule

from app.services.cloud_shell_security import (
    MANDATORY_BLOCKED_CIDRS,
    RUNTIME_PROFILE_LABEL,
    CloudShellSecurityError,
    validate_security_group,
    verify_runtime_profile,
)


def profile(**changes):
    return {
        "revision": "cloud-shell-v1",
        "cpu": 1.0,
        "memory_mib": 1024,
        "pids_limit": 512,
        "readonly_rootfs": True,
        "tmpfs_mib": 128,
        "shm_mib": 64,
        "log_max_size": "8m",
        "log_max_files": 3,
        "blocked_cidrs": list(MANDATORY_BLOCKED_CIDRS),
        "network_isolated": True,
        **changes,
    }


def settings(**changes):
    return SimpleNamespace(
        **{
            "cloud_shell_cpu": 1.0,
            "cloud_shell_memory_mib": 1024,
            "cloud_shell_blocked_cidrs": list(MANDATORY_BLOCKED_CIDRS),
            **changes,
        }
    )


def container(proof):
    return {"labels": {RUNTIME_PROFILE_LABEL: json.dumps(proof)}}


def test_exact_native_readback_is_admitted_including_lower_requested_resources():
    verify_runtime_profile(container(profile()), settings())
    verify_runtime_profile(
        container(profile(cpu=0.25, memory_mib=256)),
        settings(cloud_shell_cpu=0.25, cloud_shell_memory_mib=256),
    )
    blocked = sorted([*MANDATORY_BLOCKED_CIDRS, "10.42.0.0/16"])
    verify_runtime_profile(container(profile(blocked_cidrs=blocked)), settings(cloud_shell_blocked_cidrs=blocked))


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": "cloud-shell-v0"},
        {"cpu": True},
        {"cpu": "1.0"},
        {"cpu": 0},
        {"cpu": 1.01},
        {"cpu": float("nan")},
        {"cpu": float("inf")},
        {"cpu": 10**1000},
        {"cpu": 0.5},
        {"memory_mib": True},
        {"memory_mib": 1024.0},
        {"memory_mib": 2048},
        {"memory_mib": 512},
        {"pids_limit": -1},
        {"pids_limit": 512.0},
        {"readonly_rootfs": 1},
        {"readonly_rootfs": False},
        {"tmpfs_mib": 129},
        {"shm_mib": 128},
        {"log_max_size": "unlimited"},
        {"log_max_files": 4},
        {"network_isolated": False},
        {"network_isolated": "true"},
        {"blocked_cidrs": []},
        {"blocked_cidrs": list(MANDATORY_BLOCKED_CIDRS[:2])},
        {"blocked_cidrs": list(reversed(MANDATORY_BLOCKED_CIDRS))},
        {"blocked_cidrs": [*MANDATORY_BLOCKED_CIDRS, "10.0.0.1/24"]},
        {"blocked_cidrs": [*MANDATORY_BLOCKED_CIDRS, "10.0.0.0/24"]},
        {"unknown_control": True},
    ],
)
def test_weakened_malformed_or_mismatched_native_controls_are_rejected(changes):
    with pytest.raises(CloudShellSecurityError):
        verify_runtime_profile(container(profile(**changes)), settings())


@pytest.mark.parametrize("missing", list(profile()))
def test_every_control_requires_explicit_native_readback(missing):
    proof = profile()
    del proof[missing]
    with pytest.raises(CloudShellSecurityError):
        verify_runtime_profile(container(proof), settings())


@pytest.mark.parametrize(
    "unproven",
    [
        None,
        [],
        {},
        {"labels": {}},
        {"labels": {"afterglow.signature": "valid-owner-hmac"}},
        {"labels": {RUNTIME_PROFILE_LABEL: {"revision": "cloud-shell-v1"}}},
        {"labels": {RUNTIME_PROFILE_LABEL: "null"}},
        {"labels": {RUNTIME_PROFILE_LABEL: "[1,2]"}},
        {"labels": {RUNTIME_PROFILE_LABEL: "{"}},
        {"labels": {RUNTIME_PROFILE_LABEL: " " * 32769}},
    ],
)
def test_ownership_signature_or_requested_resources_are_not_runtime_proof(unproven):
    with pytest.raises(CloudShellSecurityError):
        verify_runtime_profile(unproven, settings())


def test_duplicate_proof_fields_are_not_last_value_wins():
    raw = json.dumps(profile())[:-1] + ', "readonly_rootfs": true}'
    with pytest.raises(CloudShellSecurityError):
        verify_runtime_profile({"labels": {RUNTIME_PROFILE_LABEL: raw}}, settings())


def group(*rules):
    return {"id": "owned-group", "security_group_rules": list(rules)}


def egress(**changes):
    return {
        "id": "egress-v4",
        "security_group_id": "owned-group",
        "direction": "egress",
        "ethertype": "IPv4",
        "protocol": None,
        "port_range_min": None,
        "port_range_max": None,
        "remote_ip_prefix": None,
        "remote_group_id": None,
        "remote_address_group_id": None,
        **changes,
    }


def test_empty_or_explicit_egress_group_is_allowed_only_for_native_isolated_sessions():
    validate_security_group(group())
    rules = [egress(), egress(id="egress-v6", ethertype="IPv6")]
    validate_security_group(group(*rules))
    validate_security_group(SecurityGroup(**group(*rules)))
    validate_security_group(group(SecurityGroupRule(**egress(protocol="tcp", port_range_min=443, port_range_max=443))))


@pytest.mark.parametrize("tags", [[], ["managed"], ["a", "b"]])
def test_native_rule_tags_are_metadata_for_egress_only_groups(tags):
    validate_security_group(group(egress(tags=tags), egress(id="egress-v6", ethertype="IPv6", tags=tags)))
    validate_security_group(SecurityGroup(**group(egress(tags=tags))))
    validate_security_group(group(SecurityGroupRule(**egress(tags=tags))))


@pytest.mark.parametrize(
    "changes",
    [
        {"tags": "managed"},
        {"tags": {"name": "managed"}},
        {"tags": None},
        {"tags": [1]},
        {"tags": ["ok", None]},
        {"tags": ["ok"], "direction": "ingress"},
        {"tags": ["ok"], "remote_group_id": "owned-group"},
        {"tags": ["ok"], "unknown_remote_policy": "allow"},
    ],
)
def test_tagged_rules_still_require_malformed_tags_and_known_isolated_fields(changes):
    with pytest.raises(CloudShellSecurityError):
        validate_security_group(group(egress(**changes)))


@pytest.mark.parametrize(
    "changes",
    [
        {"direction": "ingress"},
        {"direction": "unknown"},
        {"remote_group_id": "owned-group"},
        {"remote_address_group_id": "lateral-group"},
        {"remote_group_id": ""},
        {"security_group_id": "other-group"},
        {"id": None},
        {"ethertype": "IP"},
        {"protocol": True},
        {"protocol": "gre"},
        {"protocol": "tcp", "port_range_min": True, "port_range_max": 443},
        {"protocol": "tcp", "port_range_min": 444, "port_range_max": 443},
        {"protocol": None, "port_range_min": 443, "port_range_max": 443},
        {"remote_ip_prefix": "::/0"},
        {"remote_ip_prefix": "10.0.0.1/24"},
        {"unknown_remote_policy": "allow"},
    ],
)
def test_ingress_lateral_unknown_and_malformed_rules_are_rejected(changes):
    with pytest.raises(CloudShellSecurityError):
        validate_security_group(group(egress(**changes)))


@pytest.mark.parametrize(
    "unknown",
    [
        None,
        object(),
        {},
        {"id": "owned-group"},
        {"id": "owned-group", "security_group_rules": None},
        {"id": "owned-group", "security_group_rules": {}},
        group(None),
        group(egress(), egress()),
        SecurityGroup(id="owned-group"),
    ],
)
def test_unknown_group_or_unobserved_rule_list_is_not_safe_empty_policy(unknown):
    with pytest.raises(CloudShellSecurityError):
        validate_security_group(unknown)


@pytest.mark.parametrize(
    "missing", ["protocol", "port_range_min", "port_range_max", "remote_ip_prefix", "remote_group_id"]
)
def test_missing_native_rule_fields_are_not_synthesized_to_allow(missing):
    rule = egress()
    del rule[missing]
    with pytest.raises(CloudShellSecurityError):
        validate_security_group(group(rule))


@pytest.mark.parametrize("cpu,accepted", [(0.01, True), (0.009999, False)])
def test_native_cpu_quota_minimum_is_also_required_by_consumer(cpu, accepted):
    if accepted:
        verify_runtime_profile(container(profile(cpu=cpu)), settings(cloud_shell_cpu=cpu))
    else:
        with pytest.raises(CloudShellSecurityError):
            verify_runtime_profile(container(profile(cpu=cpu)), settings(cloud_shell_cpu=cpu))


@pytest.mark.parametrize("count,accepted", [(64, True), (65, False)])
def test_native_deny_route_count_ceiling_is_also_required_by_consumer(count, accepted):
    blocked = sorted([*MANDATORY_BLOCKED_CIDRS, *[f"10.0.0.{n}/32" for n in range(count - 3)]])
    if accepted:
        verify_runtime_profile(container(profile(blocked_cidrs=blocked)), settings(cloud_shell_blocked_cidrs=blocked))
    else:
        with pytest.raises(CloudShellSecurityError):
            verify_runtime_profile(
                container(profile(blocked_cidrs=blocked)), settings(cloud_shell_blocked_cidrs=blocked)
            )
