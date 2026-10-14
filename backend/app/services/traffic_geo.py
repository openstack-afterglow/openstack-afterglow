"""Complete offline DB-IP Country MMDB, mmap-backed and never fetched at runtime.

Mount the monthly DB read-only and restart workers on replacement. Missing,
corrupt, incompatible databases fail closed; no fixture or network fallback.
"""

import ipaddress
from datetime import UTC, datetime
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
        self.state = "unconfigured" if not filename else "unavailable"
        self.provider = None
        self.version = None
        self.attribution = None
        self.reader = None
        if not filename:
            return
        try:
            import maxminddb

            path = Path(filename)
            if not path.is_file() or not 0 < path.stat().st_size <= 512 * 1024 * 1024:
                return
            reader = maxminddb.open_database(str(path), mode=maxminddb.MODE_MMAP)
            try:
                metadata = reader.metadata()
                if "dbip" not in metadata.database_type.lower() or "country" not in metadata.database_type.lower():
                    raise ValueError("DB-IP country MMDB required")
                self.version = datetime.fromtimestamp(metadata.build_epoch, UTC).strftime("%Y-%m-%d")
                self.reader = reader
                self.provider = "DB-IP"
                self.attribution = "IP Geolocation by DB-IP (https://db-ip.com)" + (
                    ", CC BY 4.0"
                    if "lite" in metadata.database_type.lower()
                    else "; operator-supplied licensed database"
                )
                self.state = "offline_mmdb"
            except Exception:
                reader.close()
                raise
        except Exception:
            # No filename, raw address or library exception enters logs/API.
            self.state = "unavailable"

    def lookup(self, address: str | None) -> tuple[str, str]:
        if address is None:
            return "XX", "address_unavailable"
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return "XX", "invalid_address"
        if not ip.is_global or ip.is_multicast:
            return "XX", "non_global"
        if self.state != "offline_mmdb":
            return "XX", "database_" + self.state
        try:
            row = self.reader.get(str(ip))
            if row is None:
                return "XX", "range_missing"
            country = row.get("country", {}).get("iso_code")
            if country not in ISO_COUNTRIES:
                return "XX", "country_invalid"
            return country, "located"
        except Exception:
            return "XX", "lookup_failed"

    def __del__(self):
        if self.reader is not None:
            self.reader.close()


@lru_cache(maxsize=1)
def country_lookup(filename: str) -> CountryLookup:
    return CountryLookup(filename)
