"""Offline-only country lookup; CSV is operator-owned, never downloaded at runtime.

Schema: cidr,country (ISO 3166-1 alpha-2), e.g. 8.8.8.0/24,US.
Longest prefix wins. Private/reserved IPs and missing entries are unlocated (XX).
Restart workers after replacing the read-only CSV; malformed tables fail closed.
"""

import csv
import ipaddress
from functools import lru_cache
from pathlib import Path

ISO_COUNTRIES = frozenset(
    [
        "AD",
        "AE",
        "AF",
        "AG",
        "AI",
        "AL",
        "AM",
        "AO",
        "AQ",
        "AR",
        "AS",
        "AT",
        "AU",
        "AW",
        "AX",
        "AZ",
        "BA",
        "BB",
        "BD",
        "BE",
        "BF",
        "BG",
        "BH",
        "BI",
        "BJ",
        "BL",
        "BM",
        "BN",
        "BO",
        "BQ",
        "BR",
        "BS",
        "BT",
        "BV",
        "BW",
        "BY",
        "BZ",
        "CA",
        "CC",
        "CD",
        "CF",
        "CG",
        "CH",
        "CI",
        "CK",
        "CL",
        "CM",
        "CN",
        "CO",
        "CR",
        "CU",
        "CV",
        "CW",
        "CX",
        "CY",
        "CZ",
        "DE",
        "DJ",
        "DK",
        "DM",
        "DO",
        "DZ",
        "EC",
        "EE",
        "EG",
        "EH",
        "ER",
        "ES",
        "ET",
        "FI",
        "FJ",
        "FK",
        "FM",
        "FO",
        "FR",
        "GA",
        "GB",
        "GD",
        "GE",
        "GF",
        "GG",
        "GH",
        "GI",
        "GL",
        "GM",
        "GN",
        "GP",
        "GQ",
        "GR",
        "GS",
        "GT",
        "GU",
        "GW",
        "GY",
        "HK",
        "HM",
        "HN",
        "HR",
        "HT",
        "HU",
        "ID",
        "IE",
        "IL",
        "IM",
        "IN",
        "IO",
        "IQ",
        "IR",
        "IS",
        "IT",
        "JE",
        "JM",
        "JO",
        "JP",
        "KE",
        "KG",
        "KH",
        "KI",
        "KM",
        "KN",
        "KP",
        "KR",
        "KW",
        "KY",
        "KZ",
        "LA",
        "LB",
        "LC",
        "LI",
        "LK",
        "LR",
        "LS",
        "LT",
        "LU",
        "LV",
        "LY",
        "MA",
        "MC",
        "MD",
        "ME",
        "MF",
        "MG",
        "MH",
        "MK",
        "ML",
        "MM",
        "MN",
        "MO",
        "MP",
        "MQ",
        "MR",
        "MS",
        "MT",
        "MU",
        "MV",
        "MW",
        "MX",
        "MY",
        "MZ",
        "NA",
        "NC",
        "NE",
        "NF",
        "NG",
        "NI",
        "NL",
        "NO",
        "NP",
        "NR",
        "NU",
        "NZ",
        "OM",
        "PA",
        "PE",
        "PF",
        "PG",
        "PH",
        "PK",
        "PL",
        "PM",
        "PN",
        "PR",
        "PS",
        "PT",
        "PW",
        "PY",
        "QA",
        "RE",
        "RO",
        "RS",
        "RU",
        "RW",
        "SA",
        "SB",
        "SC",
        "SD",
        "SE",
        "SG",
        "SH",
        "SI",
        "SJ",
        "SK",
        "SL",
        "SM",
        "SN",
        "SO",
        "SR",
        "SS",
        "ST",
        "SV",
        "SX",
        "SY",
        "SZ",
        "TC",
        "TD",
        "TF",
        "TG",
        "TH",
        "TJ",
        "TK",
        "TL",
        "TM",
        "TN",
        "TO",
        "TR",
        "TT",
        "TV",
        "TW",
        "TZ",
        "UA",
        "UG",
        "UM",
        "US",
        "UY",
        "UZ",
        "VA",
        "VC",
        "VE",
        "VG",
        "VI",
        "VN",
        "VU",
        "WF",
        "WS",
        "YE",
        "YT",
        "ZA",
        "ZM",
        "ZW",
    ]
)


class CountryLookup:
    def __init__(self, filename: str):
        self.state = "unconfigured" if not filename else "offline_cidr"
        self.networks: dict[tuple[int, int, int], str] = {}
        if not filename:
            return
        try:
            path = Path(filename)
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("country table exceeds size limit")
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != ["cidr", "country"]:
                    raise ValueError("country table requires cidr,country header")
                for index, row in enumerate(reader):
                    if index >= 250_000 or None in row:
                        raise ValueError("country table exceeds record/schema limit")
                    network = ipaddress.ip_network(row["cidr"].strip(), strict=True)
                    country = row["country"].strip().upper()
                    if country not in ISO_COUNTRIES:
                        raise ValueError("invalid country code")
                    key = (network.version, network.prefixlen, int(network.network_address))
                    if key in self.networks:
                        raise ValueError("duplicate network")
                    self.networks[key] = country
        except (OSError, ValueError, csv.Error, UnicodeError, AttributeError):
            self.networks.clear()
            self.state = "unavailable"

    def country(self, address: str | None) -> str:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return "XX"
        if not ip.is_global or self.state != "offline_cidr":
            return "XX"
        bits = ip.max_prefixlen
        value = int(ip)
        for prefix in range(bits, -1, -1):
            mask = ((1 << bits) - 1) ^ ((1 << (bits - prefix)) - 1)
            country = self.networks.get((ip.version, prefix, value & mask))
            if country:
                return country
        return "XX"


@lru_cache(maxsize=1)
def country_lookup(filename: str) -> CountryLookup:
    return CountryLookup(filename)
