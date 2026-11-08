"""Per-domain CIDRs reserved for VPN tunnels and the subnet admission check.

A VPN client routes its tunnel subnet (Waygate default ``10.8.0.0/24``) through the
gateway. A tenant or provider subnet overlapping that range makes the client's
routes ambiguous, so new subnet CIDRs and gateway changes overlapping a reserved
range of the project's domain are refused before any native call. Existing
subnets are never rewritten. Absent policy rows keep the documented default.

Provider (admin-created, potentially shared or external) networks are visible to
every domain, so they are checked against the union of every saved domain list
plus the default (domains without a saved row use the default).
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app import database
from app.models.domain_network_policy import DomainNetworkPolicy

logger = logging.getLogger(__name__)

DEFAULT_VPN_RESERVED_CIDRS: tuple[str, ...] = ("10.8.0.0/24",)
MAX_RESERVED_RANGES = 16
MIN_IPV4_PREFIX = 8
MIN_IPV6_PREFIX = 32
VPN_RESERVED_CIDR = "vpn_reserved_cidr"
VPN_RESERVED_DETAIL = "The requested address range overlaps a range reserved for VPN tunnels in this domain"

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class VpnReservedCidrError(ValueError):
    """Non-HTTP refusal (MCP); the message starts with the stable code."""

    code = VPN_RESERVED_CIDR

    def __init__(self, requested: str, reserved: str) -> None:
        self.requested = requested
        self.reserved = reserved
        super().__init__(f"{VPN_RESERVED_CIDR}: {requested} overlaps reserved VPN range {reserved}")


class VpnReservedRangesUnavailable(RuntimeError):
    """The reserved-range policy cannot be read; callers must fail closed."""


class VpnRequestedAddressInvalid(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# ── policy validation ───────────────────────────────────────────────────────


def _invalid(message: str) -> HTTPException:
    return HTTPException(422, {"code": "vpn_reserved_ranges_invalid", "message": message})


def normalize_ranges(values: Any) -> list[str]:
    """Canonical, deduplicated (order-preserving) list of reserved networks."""
    if not isinstance(values, list) or len(values) > MAX_RESERVED_RANGES:
        raise _invalid(f"Supply at most {MAX_RESERVED_RANGES} reserved ranges")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or "/" not in value or len(value) > 64:
            raise _invalid("Each reserved range must be a CIDR network such as 10.8.0.0/24")
        try:
            network = ipaddress.ip_network(value.strip(), strict=False)
        except ValueError:
            raise _invalid("Each reserved range must be a CIDR network such as 10.8.0.0/24") from None
        minimum = MIN_IPV4_PREFIX if network.version == 4 else MIN_IPV6_PREFIX
        if network.prefixlen < minimum:
            raise _invalid(
                f"IPv4 ranges must be /{MIN_IPV4_PREFIX} or narrower and IPv6 ranges /{MIN_IPV6_PREFIX} or narrower"
            )
        canonical = str(network)
        if canonical not in result:
            result.append(canonical)
    return result


def _networks(values: Any) -> list[Network]:
    """Parse a stored/default list; a corrupt stored policy is unavailable, never empty."""
    try:
        return [ipaddress.ip_network(value) for value in normalize_ranges(list(values))]
    except (HTTPException, TypeError, ValueError):
        raise VpnReservedRangesUnavailable("Stored VPN reserved ranges are invalid") from None


# ── storage ─────────────────────────────────────────────────────────────────


def _require_domain_id(domain_id: object) -> str:
    if not isinstance(domain_id, str) or not domain_id or len(domain_id) > 64:
        raise HTTPException(403, "An authoritative domain context is required")
    return domain_id


def _factory():
    if not database.is_db_available() or (factory := database.get_session_factory()) is None:
        raise VpnReservedRangesUnavailable("VPN reserved range storage is unavailable")
    return factory


def _storage_failure(exc: Exception) -> VpnReservedRangesUnavailable:
    if isinstance(exc, OperationalError):
        database.mark_db_unhealthy(exc)
    logger.warning("VPN reserved range storage failed: %s", type(exc).__name__)
    return VpnReservedRangesUnavailable("VPN reserved range storage is unavailable")


async def _stored_row(domain_id: str) -> dict[str, Any] | None:
    try:
        async with _factory()() as session:
            row = await session.get(DomainNetworkPolicy, domain_id)
            if row is None:
                return None
            return {"vpn_reserved_cidrs": list(row.vpn_reserved_cidrs or []), "revision": int(row.revision)}
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def _stored_range_lists() -> list[list[str]]:
    try:
        async with _factory()() as session:
            rows = (await session.execute(select(DomainNetworkPolicy.vpn_reserved_cidrs))).scalars().all()
            return [list(row or []) for row in rows]
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


def _unavailable_http() -> HTTPException:
    return HTTPException(
        503, {"code": "vpn_reserved_ranges_unavailable", "message": "VPN reserved range policy is unavailable"}
    )


def _view(domain_id: str, row: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "domain_id": domain_id,
        "vpn_reserved_cidrs": [str(item) for item in _networks(row["vpn_reserved_cidrs"])]
        if row
        else list(DEFAULT_VPN_RESERVED_CIDRS),
        "default_vpn_reserved_cidrs": list(DEFAULT_VPN_RESERVED_CIDRS),
        "revision": row["revision"] if row else 0,
        "configured": row is not None,
        "max_ranges": MAX_RESERVED_RANGES,
    }


async def policy_view(domain_id: str) -> dict[str, Any]:
    domain_id = _require_domain_id(domain_id)
    try:
        return _view(domain_id, await _stored_row(domain_id))
    except VpnReservedRangesUnavailable:
        raise _unavailable_http() from None


async def update_policy(
    domain_id: str, *, actor_user_id: str, cidrs: list[str], expected_revision: int
) -> dict[str, Any]:
    """Replace the domain list under a row lock with an exact revision precondition."""
    domain_id = _require_domain_id(domain_id)
    values = normalize_ranges(cidrs)
    try:
        async with _factory()() as session, session.begin():
            row = await session.get(DomainNetworkPolicy, domain_id, with_for_update=True)
            current = int(row.revision) if row is not None else 0
            if expected_revision != current:
                raise HTTPException(
                    409, {"code": "revision_conflict", "message": "VPN reserved ranges changed; reload and retry"}
                )
            if row is None:
                row = DomainNetworkPolicy(domain_id=domain_id, revision=0, updated_by_user_id=actor_user_id)
                session.add(row)
            row.vpn_reserved_cidrs = values
            row.revision = current + 1
            row.updated_by_user_id = actor_user_id
            saved = {"vpn_reserved_cidrs": values, "revision": current + 1}
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(
            409, {"code": "revision_conflict", "message": "VPN reserved ranges changed; reload and retry"}
        ) from exc
    except SQLAlchemyError as exc:
        raise _unavailable_http() from _storage_failure(exc)
    except VpnReservedRangesUnavailable:
        raise _unavailable_http() from None
    return _view(domain_id, saved)


async def domain_reserved_networks(domain_id: str) -> list[Network]:
    """Reserved networks for one domain (default when never saved). Fails closed."""
    if not isinstance(domain_id, str) or not domain_id:
        raise VpnReservedRangesUnavailable("The project domain is unknown")
    row = await _stored_row(domain_id)
    return _networks(row["vpn_reserved_cidrs"] if row else DEFAULT_VPN_RESERVED_CIDRS)


async def platform_reserved_networks() -> list[Network]:
    """Union of every domain's reserved networks plus the default. Fails closed."""
    values = list(DEFAULT_VPN_RESERVED_CIDRS)
    for stored in await _stored_range_lists():
        values.extend(str(item) for item in _networks(stored))
    return list(dict.fromkeys(ipaddress.ip_network(value) for value in values))


# ── admission ───────────────────────────────────────────────────────────────


def requested_network(cidr: Any) -> Network:
    if not isinstance(cidr, str) or "/" not in cidr:
        raise VpnRequestedAddressInvalid("subnet_cidr_invalid")
    try:
        return ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        raise VpnRequestedAddressInvalid("subnet_cidr_invalid") from None


def requested_address(value: Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if not isinstance(value, str) or "%" in value:
        raise VpnRequestedAddressInvalid("subnet_gateway_invalid")
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        raise VpnRequestedAddressInvalid("subnet_gateway_invalid") from None


def assert_outside(reserved: list[Network], *, cidr: Any = None, gateway_ip: Any = None) -> None:
    """Raise VpnReservedCidrError for the first overlap; None means "not requested"."""
    if cidr is not None:
        network = requested_network(cidr)
        for item in reserved:
            if item.version == network.version and item.overlaps(network):
                raise VpnReservedCidrError(str(network), str(item))
    if gateway_ip is not None:
        address = requested_address(gateway_ip)
        for item in reserved:
            if item.version == address.version and address in item:
                raise VpnReservedCidrError(str(address), str(item))


def reserved_http_error(exc: VpnReservedCidrError) -> HTTPException:
    return HTTPException(
        422,
        {
            "code": VPN_RESERVED_CIDR,
            "message": VPN_RESERVED_DETAIL,
            "requested": exc.requested,
            "reserved_cidr": exc.reserved,
        },
    )


async def _require_allowed(load, *, cidr: Any = None, gateway_ip: Any = None) -> None:
    try:
        reserved = await load()
        assert_outside(reserved, cidr=cidr, gateway_ip=gateway_ip)
    except VpnReservedCidrError as exc:
        raise reserved_http_error(exc) from None
    except VpnRequestedAddressInvalid as exc:
        raise HTTPException(422, {"code": exc.code, "message": "The requested subnet address is malformed"}) from None
    except VpnReservedRangesUnavailable:
        raise _unavailable_http() from None


async def require_domain_subnet_allowed(domain_id: str, *, cidr: Any = None, gateway_ip: Any = None) -> None:
    """HTTP admission for a project subnet in ``domain_id`` (422/503 before native calls)."""
    await _require_allowed(lambda: domain_reserved_networks(domain_id), cidr=cidr, gateway_ip=gateway_ip)


async def require_platform_subnet_allowed(*, cidr: Any = None, gateway_ip: Any = None) -> None:
    """HTTP admission for an administrator-created (provider) subnet across every domain."""
    await _require_allowed(platform_reserved_networks, cidr=cidr, gateway_ip=gateway_ip)
