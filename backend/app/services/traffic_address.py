"""Analytics-only original-address policy. Never used by auth or rate limiting.

XFF is authoritative only behind an exact configured proxy CIDR and an original
socket peer. Walk right-to-left, stopping at the first nontrusted hop. Validate
the entire bounded chain first: malformed or ambiguous input fails closed.
"""

import ipaddress
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class AddressObservation:
    address: str | None
    origin: str
    reason: str


@lru_cache(maxsize=8)
def _networks(cidrs: tuple[str, ...]):
    return tuple(ipaddress.ip_network(value, strict=True) for value in cidrs)


def _parse(value):
    if not isinstance(value, str) or not value or "%" in value:
        return None
    try:
        address = ipaddress.ip_address(value)
        return address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
    except ValueError:
        return None


def resolve_address(peer_ip, peer_verified: bool, forwarded_for, proxy_cidrs, cluster_cidrs) -> AddressObservation:
    if not peer_verified:
        return AddressObservation(None, "unknown", "peer_unverified")
    peer = _parse(peer_ip)
    if peer is None:
        return AddressObservation(None, "unknown", "address_unavailable" if peer_ip is None else "invalid_address")
    proxies = _networks(tuple(proxy_cidrs))

    def trusted(ip):
        return any(ip.version == network.version and ip in network for network in proxies)

    address = peer
    if trusted(peer):
        if forwarded_for is None or forwarded_for == "":
            return AddressObservation(None, "unknown", "forwarded_missing")
        if not isinstance(forwarded_for, str) or len(forwarded_for) > 1024:
            return AddressObservation(None, "unknown", "forwarded_invalid")
        chain = forwarded_for.split(",")
        if len(chain) > 16:
            return AddressObservation(None, "unknown", "forwarded_invalid")
        hops = [_parse(part.strip()) for part in chain]
        if any(hop is None for hop in hops):
            return AddressObservation(None, "unknown", "forwarded_invalid")
        for hop in reversed(hops):
            if not trusted(address):
                break
            address = hop
        if trusted(address):
            return AddressObservation(None, "unknown", "forwarded_all_trusted")
    # Forged headers from a nonproxy peer are ignored, never promoted to authority.
    clusters = _networks(tuple(cluster_cidrs))
    if any(address.version == network.version and address in network for network in clusters):
        return AddressObservation(str(address), "internal", "classified")
    if address.is_global and not address.is_multicast:
        return AddressObservation(str(address), "external", "classified")
    return AddressObservation(str(address), "unknown", "non_global_noncluster")
