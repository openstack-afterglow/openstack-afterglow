"""Finite, shared browser route vocabulary; never retain raw paths or query data."""

from __future__ import annotations

import re
from uuid import UUID

STATIC_SEGMENTS = frozenset(
    [
        "dashboard",
        "admin",
        "account",
        "activity",
        "auth",
        "callback",
        "login",
        "signup",
        "recover",
        "invitations",
        "registrations",
        "docs",
        "select-project",
        "select-domain",
        "oauth",
        "claude",
        "mcp",
        "authorize",
        "settings",
        "create",
        "palimpsest",
        "packages",
        "volumes",
        "snapshots",
        "backups",
        "compute",
        "instances",
        "console-log",
        "images",
        "keypairs",
        "network",
        "networks",
        "topology",
        "loadbalancers",
        "new",
        "routers",
        "floating-ips",
        "security-groups",
        "waygate",
        "usage",
        "observability",
        "drover",
        "notifications",
        "sessions",
        "beta",
        "usage-report",
        "iam",
        "projects",
        "users",
        "my-resources",
        "secrets",
        "containers",
        "clusters",
        "database",
        "file-storage",
        "security-services",
        "manage",
        "project-settings",
        "chat",
        "tools",
        "realtime",
        "audio",
        "object-storage",
        "buckets",
        "quotas",
        "flavors",
        "domains",
        "libraries",
        "monitoring",
        "traffic",
        "aodh",
        "gnocchi",
        "logins",
        "rabbitmq",
        "proxysql",
        "openstack",
        "node",
        "temperatures",
        "mysql",
        "memcached",
        "libvirt",
        "haproxy",
        "etcd",
        "ceph",
        "resources",
        "orphans",
        "ports",
        "system-admins",
        "hypervisors",
        "announcements",
        "roles",
        "subnets",
        "events",
        "stats",
        "models",
        "groups",
        "user-credentials",
        "application-credentials",
        "infrastructure-topology",
        "services",
        "notion",
        "layers",
        "gpu",
    ]
)
PUBLIC_ROOTS = frozenset({"login", "signup", "recover", "invitations", "registrations", "docs", "auth", "oauth"})


def canonical_page(value: str) -> str:
    """Keep only source-literal segments; all dynamic segments become ``:id``.

    Query/hash/percent/Unicode/control/URL syntax is rejected rather than split or
    decoded. Source route parameters (``[id]``, ``[...slug]``, ``{id}``) and opaque
    resource identifiers have exactly the same non-identifying representation.
    """
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 255:
        raise ValueError("Invalid route template")
    if not re.fullmatch(r"/[A-Za-z0-9_:/\[\]{}.=\-]*", value) or "//" in value:
        raise ValueError("Invalid route template")
    parts = value.strip("/").split("/") if value.strip("/") else []
    if len(parts) > 12:
        raise ValueError("Invalid route template")
    return "/" + "/".join(part if part in STATIC_SEGMENTS else ":id" for part in parts)


def public_page(value: str) -> bool:
    return value == "/" or value.split("/")[1] in PUBLIC_ROOTS


def interaction_id(value: str | None) -> str | None:
    """Client correlation is untrusted, bounded UUID metadata, never authority."""
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return str(parsed) if str(parsed) == value.lower() else None
