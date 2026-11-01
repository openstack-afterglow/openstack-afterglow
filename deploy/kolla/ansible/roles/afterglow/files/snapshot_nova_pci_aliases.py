#!/usr/bin/env python3
"""Read effective Nova INI locally; emit only the closed PCI alias projection.

The stdlib-only INI reader follows oslo.config's iniparser rules: duplicate
assignments accumulate, indented lines continue values, blank lines end them,
and only unindented full-line #/; comments are comments. In particular, stripping
inline comments or using ConfigParser would change Nova's MultiStrOpt meaning.
No raw input or exception text is ever returned to Ansible.
"""

import datetime
import json
import os
import stat
import sys

MAX_CONFIG_BYTES = 1024 * 1024
MAX_SNAPSHOT_BYTES = 1024 * 1024
MAX_ALIASES = 256
FIELDS = ("name", "vendor_id", "product_id", "resource_class", "device_type", "traits", "numa_policy")


def unavailable(host):
    return {"host": host, "observed_at": None, "state": "unavailable", "aliases": []}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def sanitize_alias(alias):
    # Unknown fields might be newer Nova constraints. Discarding them could
    # falsely certify an unconstrained alias; fail the whole observation closed.
    if not isinstance(alias, dict) or not set(alias).issubset(FIELDS):
        raise ValueError("Unsupported alias fields")
    if not isinstance(alias.get("name"), str) or not alias["name"].strip():
        raise ValueError("Missing alias name")
    # Nova strips the name before merging same-name alternatives. Preserve exact
    # configured spelling only when it cannot hide a normalized-name collision.
    if alias["name"] != alias["name"].strip():
        raise ValueError("Padded alias name")
    result = {}
    for key in FIELDS:
        value = alias.get(key)
        bound = 4096 if key == "traits" else 256
        if value is not None and (
            not isinstance(value, str) or len(value) > bound
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("Invalid alias value")
        result[key] = value
    return result


def parse_aliases(text):
    section = None
    key = None
    values = []
    aliases = []
    has_section = False

    def flush():
        # Nova's MultiStrOpt adds deprecated DEFAULT.pci_alias values to the
        # current pci.alias values; omitting these would falsely report ready.
        if (section == "pci" and key == "alias") or (section == "DEFAULT" and key == "pci_alias"):
            aliases.append(sanitize_alias(json.loads("\n".join(values), object_pairs_hook=unique_object)))
            if len(aliases) > MAX_ALIASES:
                raise ValueError("Too many aliases")

    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line:
            if key is not None:
                flush()
                key, values = None, []
            continue
        if line.startswith((" ", "\t")):
            if key is None:
                raise ValueError("Unexpected continuation")
            values.append(line.lstrip())
            continue
        if key is not None:
            flush()
            key, values = None, []
        if line.startswith("["):
            if not line.endswith("]") or len(line) <= 2:
                raise ValueError("Invalid section")
            section = line[1:-1]
            if section.lower() == "pci" and section != "pci":
                raise ValueError("Noncanonical PCI section")
            has_section = True
        elif line.startswith(("#", ";")):
            continue
        else:
            separators = [index for index in (line.find("="), line.find(":")) if index >= 0]
            if not separators or section is None:
                raise ValueError("Invalid assignment")
            split = min(separators)
            key, value = line[:split].strip(), line[split + 1:].strip()
            if not key:
                raise ValueError("Empty key")
            if value and value[0] == value[-1] and value.startswith(('"', "'")):
                value = value[1:-1]
            values = [value]
    if key is not None:
        flush()
    if not has_section:
        raise ValueError("Empty configuration")
    return aliases


def collect(host, path):
    result = unavailable(host)
    try:
        # Never follow a replaced source into a device/FIFO/symlink or read an
        # unbounded file. O_NONBLOCK avoids blocking if the source becomes a FIFO.
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_CONFIG_BYTES:
                return result
            raw = source.read(MAX_CONFIG_BYTES + 1)
            after = os.fstat(source.fileno())
        if len(raw) > MAX_CONFIG_BYTES or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ):
            return result
        aliases = parse_aliases(raw.decode("utf-8"))
        # Use the effective source revision time, not poll time: unchanged
        # reconfigure must preserve bytes, single-file bind inode and config_hash.
        observed_at = datetime.datetime.fromtimestamp(before.st_mtime, datetime.timezone.utc).isoformat()
        return {"host": host, "observed_at": observed_at, "state": "ready", "aliases": aliases}
    except (OSError, ValueError, TypeError, RecursionError):
        return result


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def aggregate(hosts, results):
    controllers = []
    for host in sorted(set(hosts)):
        controller = unavailable(host)
        matches = [result for result in results if result.get("item") == host]
        if len(matches) == 1 and matches[0].get("rc") == 0 and not matches[0].get("unreachable", False):
            try:
                record = json.loads(matches[0]["stdout"], object_pairs_hook=unique_object)
                if (record.get("host") != host or record.get("state") != "ready"
                        or not isinstance(record.get("observed_at"), str)
                        or not isinstance(record.get("aliases"), list)
                        or len(record["aliases"]) > MAX_ALIASES):
                    raise ValueError("Invalid observation")
                observed_at = datetime.datetime.fromisoformat(record["observed_at"])
                if observed_at.tzinfo is None:
                    raise ValueError("Missing observation timezone")
                controller = {"host": host, "state": "ready", "observed_at": observed_at.isoformat(),
                              "aliases": [sanitize_alias(alias) for alias in record["aliases"]]}
            except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
                pass
        controllers.append(controller)
    snapshot = {"schema_version": 1, "source": "nova_api_config", "controllers": controllers}
    # Keep the entire file bounded without silently dropping/truncating aliases.
    # An oversized observation is unavailable, never a partial ready list.
    for index in sorted(range(len(controllers)), key=lambda i: len(encode(controllers[i])), reverse=True):
        if len(encode(snapshot)) + 1 <= MAX_SNAPSHOT_BYTES:
            break
        controllers[index] = unavailable(controllers[index]["host"])
    if len(encode(snapshot)) + 1 > MAX_SNAPSHOT_BYTES:
        raise ValueError("Controller inventory exceeds snapshot bound")
    return snapshot


def main():
    try:
        request = json.loads(sys.stdin.read(), object_pairs_hook=unique_object)
        if request.get("mode") == "aggregate":
            result = aggregate(request["controllers"], request.get("results", []))
        else:
            result = collect(request["host"], request["path"])
        print(encode(result))
        return 0
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
        # This indicates invalid role inputs, not source unavailability. Avoid
        # printing exception text because it may contain original input bytes.
        print("Invalid PCI snapshot request", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
