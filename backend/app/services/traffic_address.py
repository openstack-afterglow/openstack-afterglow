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


# Only these standard-purpose ranges (and RFC1918 /16s) can enter Redis.
# Keep this finite rather than deriving prefixes from arbitrary host addresses.
_PRIVATE_V4 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_NONPUBLIC_RANGES = tuple(
    (ipaddress.ip_network(network), kind)
    for network, kind in (
        ("0.0.0.0/8", "unspecified"),
        ("100.64.0.0/10", "shared"),
        ("127.0.0.0/8", "loopback"),
        ("169.254.0.0/16", "link_local"),
        ("192.0.0.0/24", "reserved"),
        ("192.0.2.0/24", "documentation"),
        ("192.88.99.0/24", "reserved"),
        ("198.18.0.0/15", "benchmark"),
        ("198.51.100.0/24", "documentation"),
        ("203.0.113.0/24", "documentation"),
        ("224.0.0.0/4", "multicast"),
        ("240.0.0.0/4", "reserved"),
        ("::/128", "unspecified"),
        ("::1/128", "loopback"),
        ("64:ff9b:1::/48", "reserved"),
        ("100::/64", "reserved"),
        ("100:0:0:1::/64", "reserved"),
        ("2001:2::/48", "benchmark"),
        ("2001:db8::/32", "documentation"),
        ("2001::/23", "reserved"),
        ("2002::/16", "reserved"),
        ("3fff::/20", "documentation"),
        ("fc00::/7", "private"),
        ("fe80::/10", "link_local"),
        ("ff00::/8", "multicast"),
        # Unallocated IPv6 blocks: bounded fallback for non-global addresses.
        ("::/8", "reserved"),
        ("100::/8", "reserved"),
        ("200::/7", "reserved"),
        ("400::/6", "reserved"),
        ("800::/5", "reserved"),
        ("1000::/4", "reserved"),
        ("4000::/3", "reserved"),
        ("6000::/3", "reserved"),
        ("8000::/3", "reserved"),
        ("a000::/3", "reserved"),
        ("c000::/3", "reserved"),
        ("e000::/4", "reserved"),
        ("f000::/5", "reserved"),
        ("f800::/6", "reserved"),
        ("fe00::/9", "reserved"),
        ("fec0::/10", "reserved"),
    )
)


def nonpublic_network(address: str | None) -> tuple[str, str] | None:
    """Classify an independently verified address, never discover an actual subnet.

    Callers distinguish a resolved client from a verified socket peer; this helper
    never inspects XFF. Unknown future special ranges stay unclassified rather
    than persisting an arbitrary prefix.
    """
    ip = _parse(address)
    if ip is None or (ip.is_global and not ip.is_multicast):
        return None
    if ip.version == 4 and any(ip in network for network in _PRIVATE_V4):
        return str(ipaddress.ip_network((ip, 16), strict=False)), "private"
    for network, kind in _NONPUBLIC_RANGES:
        if ip.version == network.version and ip in network:
            return str(network), kind
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
