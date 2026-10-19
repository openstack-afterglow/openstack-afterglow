"""Caller-scoped Ceilometer measurements read from Gnocchi, never Ceilometer REST.

Schema/units reviewed against official sources (2026-10-16):
https://github.com/openstack/ceilometer/blob/master/ceilometer/publisher/data/gnocchi_resources.yaml
https://docs.openstack.org/ceilometer/latest/admin/telemetry-measurements.html
https://gnocchi.osci.io/rest.html

Only native-visible resources are covered, not a complete Nova/cloud inventory.
Counters are differentiated at their stored archive granularity; differences of
archived means are estimates, not recovery of discarded raw samples. Missing,
reset, duplicate, nonfinite and noncontiguous intervals are never zero-filled.
Denominators are historical measurements, never today's flavor or host RSS.
Each invocation owns its bounded reader/cache; nothing is shared across callers.
"""

import asyncio
import json
import math
import time
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit
from uuid import UUID

from keystoneauth1.exceptions.catalog import EndpointNotFound

_DEADLINE_S = 6.0
_REQUEST_TIMEOUT_S = 1.5
_MAX_REQUESTS = 96
_MAX_PAGES = 4
_PAGE_SIZE = 32
_MAX_RESOURCES = 128
_MAX_SAMPLES = 2048
_MAX_BYTES = 512 * 1024
_MAX_TOTAL_BYTES = 4 * 1024 * 1024
_MAX_RANGE_S = 31 * 86400

# key: (native resource type, meter, source unit, result unit, counter)
_METERS = {
    "cpu": ("instance", "cpu", "ns", "%", True),
    "memory": ("instance", "memory.usage", "MiB", "%", False),
    "memory_resident": ("instance", "memory.resident", "MiB", "MiB", False),
    "memory_allocated": ("instance", "memory", "MiB", "MiB", False),
    "vcpus": ("instance", "vcpus", "vcpu", "vcpu", False),
    "memory_swap_in": ("instance", "memory.swap.in", "MiB", "MiB/s", True),
    "memory_swap_out": ("instance", "memory.swap.out", "MiB", "MiB/s", True),
    "disk_allocation": ("instance_disk", "disk.device.allocation", "B", "B", False),
    "network_rx": ("instance_network_interface", "network.incoming.bytes", "B", "B/s", True),
    "network_tx": ("instance_network_interface", "network.outgoing.bytes", "B", "B/s", True),
    "network_rx_packets": ("instance_network_interface", "network.incoming.packets", "packet", "packet/s", True),
    "network_tx_packets": ("instance_network_interface", "network.outgoing.packets", "packet", "packet/s", True),
    "disk_read": ("instance_disk", "disk.device.read.bytes", "B", "B/s", True),
    "disk_write": ("instance_disk", "disk.device.write.bytes", "B", "B/s", True),
    "disk_read_iops": ("instance_disk", "disk.device.read.requests", "request", "request/s", True),
    "disk_write_iops": ("instance_disk", "disk.device.write.requests", "request", "request/s", True),
    # Newer pollsters document these per-instance meters. Older publisher maps
    # omit them: accept only actual metrics on the project-owned instance.
    "gpu_util": ("instance", "vgpu.utilization", "%", "%", False),
    "gpu_mem": ("instance", "vgpu.memory.used", "MiB", "%", False),
}
_SYSTEM_METERS = {
    "nova_compute": {
        "compute.node.cpu.percent": "%",
        "compute.node.cpu.idle.percent": "%",
        "compute.node.cpu.iowait.percent": "%",
        "compute.node.cpu.kernel.percent": "%",
        "compute.node.cpu.user.percent": "%",
        "compute.node.cpu.frequency": "MHz",
    },
    "ipmi": {
        "hardware.ipmi.node.power": "W",
        "hardware.ipmi.node.temperature": "C",
        "hardware.ipmi.node.inlet_temperature": "C",
        "hardware.ipmi.node.outlet_temperature": "C",
        "hardware.ipmi.node.fan": "RPM",
    },
    "volume_provider": {
        f"volume.provider.capacity.{name}": "GiB"
        for name in ("total", "free", "allocated", "provisioned", "virtual_free")
    },
    "volume_provider_pool": {
        f"volume.provider.pool.capacity.{name}": "GiB"
        for name in ("total", "free", "allocated", "provisioned", "virtual_free")
    },
}


class _Failure(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def _result(unit, series=None, status=None, error=None, source="gnocchi"):
    points = series if series is not None else []
    return {
        "series": points,
        "source": source,
        "unit": unit,
        "status": status or ("available" if points else "not_collected"),
        "error": error,
    }


def _failed(keys, failure):
    return {
        key: _result(
            _METERS.get(key, (None, None, None, "", False))[3],
            status=failure.status,
            error=failure.code,
            source=None if failure.status == "not_configured" else "gnocchi",
        )
        for key in keys
    }


def _field(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _identity(value):
    if not isinstance(value, str):
        return None
    try:
        return UUID(value).hex
    except ValueError:
        return value


def _same(left, right):
    return bool(left and right) and _identity(left) == _identity(right)


def _duration(value):
    if _number(value):
        return float(value)
    if isinstance(value, str):
        try:
            days, _, clock = value.rpartition(" day")
            if days:
                clock = clock.lstrip("s, ")
                day_s = int(days) * 86400
            else:
                clock, day_s = value, 0
            parts = clock.split(":")
            if len(parts) == 3:
                return day_s + int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except (ValueError, OverflowError):
            pass
    return None


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


class _Reader:
    def __init__(self, conn, start, end, step):
        self.conn, self.start, self.end, self.step = conn, start, end, step
        self.deadline = time.monotonic() + _DEADLINE_S
        self.calls = self.bytes = self.resources = 0
        self.cache = {}
        self.truncated = False
        self.endpoint = None
        if (
            not all(isinstance(x, int) and not isinstance(x, bool) for x in (start, end, step))
            or start < 0
            or end <= start
            or step <= 0
            or end - start > _MAX_RANGE_S
        ):
            raise _Failure("unavailable", "invalid_range")

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.truncated = True
            raise _Failure("unavailable", "time_budget")
        return remaining

    def discover(self):
        try:
            config = self.conn.config
            endpoint = self.conn.session.get_endpoint(
                service_type="metric",
                interface=config.get_interface("metric"),
                region_name=config.get_region_name("metric"),
                skip_discovery=True,
            )
        except EndpointNotFound:
            raise _Failure("not_configured", "endpoint_missing") from None
        except Exception:
            raise _Failure("unavailable", "catalog_unavailable") from None
        if not endpoint:
            raise _Failure("not_configured", "endpoint_missing")
        if not isinstance(endpoint, str):
            raise _Failure("unavailable", "invalid_endpoint")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username
        ):
            raise _Failure("unavailable", "invalid_endpoint")
        self.endpoint = endpoint.rstrip("/")
        if not self.endpoint.endswith("/v1"):
            self.endpoint += "/v1"
        self.remaining()

    def request(self, method, path, *, params=None, body=None):
        remaining = self.remaining()
        if self.calls >= _MAX_REQUESTS:
            self.truncated = True
            raise _Failure("unavailable", "request_budget")
        self.calls += 1
        response = None
        try:
            response = self.conn.session.request(
                self.endpoint + path,
                method,
                params=params,
                json=body,
                timeout=min(_REQUEST_TIMEOUT_S, remaining),
                stream=True,
                raise_exc=False,
                redirect=0,
                connect_retries=0,
                status_code_retries=0,
                allow_reauth=False,
                log=False,
            )
            code = response.status_code
            if code in (401, 403):
                raise _Failure("forbidden", "access_denied")
            if code == 404:
                raise _Failure("not_collected", "resource_missing")
            if not 200 <= code < 300:
                raise _Failure("unavailable", "upstream_error")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=16384):
                self.remaining()
                self.bytes += len(chunk)
                if len(content) + len(chunk) > _MAX_BYTES or self.bytes > _MAX_TOTAL_BYTES:
                    self.truncated = True
                    raise _Failure("unavailable", "response_budget")
                content.extend(chunk)
            try:
                return json.loads(content)
            except (ValueError, UnicodeError, RecursionError):
                raise _Failure("unavailable", "malformed_response") from None
        except _Failure:
            raise
        except Exception:
            raise _Failure("unavailable", "request_failed") from None
        finally:
            if response is not None:
                response.close()

    def listing(self, kind, filters=None):
        rows, seen, marker, error = [], set(), None, None
        for _ in range(_MAX_PAGES):
            params = {"limit": _PAGE_SIZE, "sort": "id:asc"}
            if marker:
                params["marker"] = marker
            try:
                page = self.request(
                    "POST" if filters else "GET",
                    f"/search/resource/{kind}" if filters else f"/resource/{kind}",
                    params=params,
                    body=filters,
                )
            except _Failure as exc:
                return rows, exc
            if not isinstance(page, list):
                return rows, _Failure("unavailable", "malformed_response")
            if not page:
                return rows, error
            if len(page) > _PAGE_SIZE:
                self.truncated = True
                error = _Failure("partial", "resource_budget")
            for row in page[:_PAGE_SIZE]:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                    error = _Failure("partial", "malformed_response")
                    continue
                if row["id"] in seen:
                    self.truncated = True
                    return rows, _Failure("partial", "pagination_stalled")
                seen.add(row["id"])
                if self.resources >= _MAX_RESOURCES:
                    self.truncated = True
                    return rows, _Failure("partial", "resource_budget")
                self.resources += 1
                rows.append(row)
            last = page[min(len(page), _PAGE_SIZE) - 1]
            if not isinstance(last, dict) or not isinstance(last.get("id"), str):
                return rows, _Failure("partial", "malformed_response")
            marker = last["id"]
            # Never follow upstream Link URLs. Markers retain our own endpoint,
            # project filter and limit, including when max_limit clamps pages.
        self.truncated = True
        return rows, _Failure("partial", "page_budget")

    def samples(self, resource, meter, unit, counter=False):
        metrics = resource.get("metrics")
        if not isinstance(metrics, dict):
            return [], _Failure("unavailable", "malformed_response")
        metric_id = metrics.get(meter)
        if not metric_id:
            return [], None
        if not isinstance(metric_id, str) or len(metric_id) > 256:
            return [], _Failure("unavailable", "malformed_response")
        cache_key = (resource["type"], resource["id"], meter, unit, counter)
        if cache_key in self.cache:
            return self.cache[cache_key]
        try:
            # Named relationships let Gnocchi enforce the metric's association
            # as well as resource/metric policy; never trust a foreign metric ID.
            path = f"/resource/{resource['type']}/{quote(resource['id'], safe='')}/metric/{quote(meter, safe='')}"
            metadata = self.request("GET", path)
            if not isinstance(metadata, dict):
                raise _Failure("unavailable", "malformed_response")
            accepted_units = (None, "%", "percent") if unit == "%" else (None, unit)
            if metadata.get("unit") not in accepted_units:
                raise _Failure("unavailable", "unit_mismatch")
            policy = metadata.get("archive_policy")
            if not isinstance(policy, dict) or not isinstance(policy.get("aggregation_methods"), list):
                raise _Failure("unavailable", "malformed_response")
            if "mean" not in policy["aggregation_methods"]:
                raise _Failure("not_collected", "aggregation_missing")
            definition = policy.get("definition")
            if not isinstance(definition, list):
                raise _Failure("unavailable", "malformed_response")
            tiers = []
            for item in definition:
                if not isinstance(item, dict):
                    continue
                gran = _duration(item.get("granularity"))
                span = _duration(item.get("timespan"))
                if gran and math.isfinite(gran) and gran > 0 and span is not None and math.isfinite(span) and span > 0:
                    tiers.append((gran, span))
            if not tiers:
                raise _Failure("not_collected", "granularity_missing")
            duration = self.end - self.start
            # Retention is relative to the last stored point, not wall clock.
            # A stopped resource can retain old samples indefinitely; windows
            # wider than retention can still contain useful recent samples.
            covering = [(gran, span) for gran, span in tiers if span >= duration]
            candidates = covering or tiers
            coarser = [(gran, span) for gran, span in candidates if gran >= self.step]
            granularity, span = min(coarser) if coarser else max(candidates)
            if _MAX_SAMPLES <= 3:
                self.truncated = True
                raise _Failure("unavailable", "sample_budget")
            # If an older interval has expired from a fine tier, try longer
            # lived coarse tiers. Keep one tier intact, never blend archives.
            attempts = [(granularity, span)] + sorted(
                {(gran, lifetime) for gran, lifetime in tiers if gran > granularity}
            )[:2]
            result, best_coverage = ([], None), -1
            for gran, lifetime in attempts:
                try:
                    points, error, discontinuous = self._tier_samples(path, meter, unit, counter, gran, lifetime)
                except _Failure as exc:
                    if result[0]:
                        result = (result[0], result[1] or _Failure("partial", exc.code))
                        break
                    raise
                # Diagnostic precedence must not hide a proven discontinuity
                # and allow a coarser archive to mask a reset or resize.
                candidate = (points, error)
                if counter and any(
                    after[0] - before[0] != after[2] or after[1] < before[1]
                    for before, after in zip(points, points[1:], strict=False)
                ):
                    discontinuous = True
                    error = error or _Failure("partial", "counter_discontinuity")
                    candidate = (points, error)
                if counter:
                    windows = [
                        (before[0], after[0])
                        for before, after in zip(points, points[1:], strict=False)
                        if after[0] - before[0] == after[2] and after[1] >= before[1]
                    ]
                else:
                    windows = [(ts, ts + effective) for ts, _, effective in points]
                coverage = sum(max(0, min(self.end, end) - max(self.start, start)) for start, end in windows)
                if coverage > best_coverage or (coverage == best_coverage and len(points) > len(result[0])):
                    result, best_coverage = candidate, coverage
                if coverage >= duration or discontinuous:
                    break
            if len(attempts) > 1 and result[0] and best_coverage < duration:
                result = (result[0], result[1] or _Failure("partial", "archive_coverage"))
        except _Failure as exc:
            result = ([], exc)
        self.cache[cache_key] = result
        return result

    def _tier_samples(self, path, meter, unit, counter, granularity, span):
        duration = self.end - self.start
        # Provider-side mean resampling preserves the full requested interval
        # and counter baseline within the same fixed response sample budget.
        target = max(self.step, duration / (_MAX_SAMPLES - 3))
        effective = math.ceil(target / granularity) * granularity
        lower = self.start - effective if counter else self.start
        params = {
            "start": max(0, lower),
            "stop": self.end,
            "aggregation": "mean",
            "granularity": granularity,
        }
        if effective > granularity:
            params["resample"] = effective
        payload = self.request("GET", path + "/measures", params=params)
        if not isinstance(payload, list):
            raise _Failure("unavailable", "malformed_response")
        error = _Failure("partial", "archive_coverage") if span < duration else None
        points, duplicate = {}, set()
        if len(payload) > _MAX_SAMPLES:
            self.truncated = True
            error = _Failure("partial", "sample_budget")
        signed_gauge = not counter and (unit == "C" or meter.endswith(".virtual_free"))
        for point in payload[:_MAX_SAMPLES]:
            try:
                if (
                    not isinstance(point, (list, tuple))
                    or len(point) != 3
                    or not _number(point[1])
                    or point[1] != effective
                    or not _number(point[2])
                    or (point[2] < 0 and not signed_gauge)
                ):
                    raise ValueError("sample")
                ts = _timestamp(point[0])
                if not max(0, lower) <= ts <= self.end:
                    continue
                if ts in points or ts in duplicate:
                    duplicate.add(ts)
                    points.pop(ts, None)
                    raise ValueError("duplicate")
                points[ts] = (float(point[2]), effective)
            except (ValueError, TypeError, OverflowError):
                error = _Failure("partial", "invalid_samples")
        continuity_error = None
        if effective > granularity and (counter or meter == "vcpus"):
            invalid, continuity_error = self._native_discontinuities(
                path, counter and meter != "vcpus", granularity, effective, max(0, lower)
            )
            if continuity_error:
                error = error or continuity_error
            points = {
                ts: point for ts, point in points.items() if not any(start <= ts <= stop for start, stop in invalid)
            }
        return [(ts, *points[ts]) for ts in sorted(points)], error, continuity_error is not None

    def _native_discontinuities(self, path, counter, granularity, effective, lower):
        """Bounded native windows qualify reset/gap/resize-hidden coarse means.

        Retain only the previous native sample and invalid time intervals, not
        an unbounded raw history. Shared time/request/byte caps remain in force.
        """
        invalid, previous = [], None
        cursor = math.floor(lower / granularity) * granularity
        limit = self.end
        while cursor <= limit:
            stop = min(limit + granularity, cursor + granularity * (_MAX_SAMPLES - 2))
            raw = self.request(
                "GET",
                path + "/measures",
                params={
                    "start": cursor,
                    "stop": stop,
                    "aggregation": "mean",
                    "granularity": granularity,
                },
            )
            if not isinstance(raw, list):
                raise _Failure("unavailable", "malformed_response")
            if len(raw) > _MAX_SAMPLES:
                self.truncated = True
                raise _Failure("unavailable", "sample_budget")
            native, malformed = {}, False
            for point in raw:
                try:
                    if (
                        not isinstance(point, (list, tuple))
                        or len(point) != 3
                        or not _number(point[1])
                        or point[1] != granularity
                        or not _number(point[2])
                        or point[2] < 0
                    ):
                        raise ValueError("sample")
                    ts = _timestamp(point[0])
                    if not cursor <= ts <= min(stop, limit):
                        continue
                    if ts in native:
                        raise ValueError("duplicate")
                    native[ts] = float(point[2])
                except (ValueError, TypeError, OverflowError):
                    malformed = True
            if malformed or not native:
                invalid.append((math.floor(cursor / effective) * effective, math.floor(stop / effective) * effective))
            for ts, value in sorted(native.items()):
                if previous is not None:
                    before, old_value = previous
                    if ts == before and value == old_value:
                        continue  # Overlap at the adjacent request boundary.
                    discontinuity = ts - before != granularity or (value < old_value if counter else value != old_value)
                    if discontinuity:
                        invalid.append(
                            (math.floor(before / effective) * effective, math.floor(ts / effective) * effective)
                        )
                previous = (ts, value)
            cursor = stop
        merged = []
        for start, stop in sorted(invalid):
            if merged and start <= merged[-1][1] + effective:
                merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
            else:
                merged.append((start, stop))
        code = "counter_discontinuity" if counter else "denominator_discontinuity"
        return merged, _Failure("partial", code) if merged else None


def _series(reader, resource, meter, unit, output_unit, counter=False):
    samples, error = reader.samples(resource, meter, unit, counter)
    points = []
    if counter:
        for before, after in zip(samples, samples[1:], strict=False):
            elapsed = after[0] - before[0]
            if elapsed != before[2] or before[2] != after[2] or after[1] < before[1]:
                error = error or _Failure("partial", "counter_discontinuity")
                continue
            value = (after[1] - before[1]) / elapsed
            if reader.start <= after[0] <= reader.end and math.isfinite(value):
                points.append({"ts": after[0], "value": value})
        if samples and not points:
            error = error or _Failure("partial", "insufficient_samples")
    else:
        points = [{"ts": ts, "value": value} for ts, value, _ in samples if reader.start <= ts <= reader.end]
    return _result(
        output_unit,
        points,
        "partial" if error and points else error.status if error else None,
        error.code if error else None,
    )


def _ratio(numerator, denominator, factor=100.0):
    denom = {point["ts"]: point["value"] for point in denominator["series"]}
    points, missing = [], False
    for point in numerator["series"]:
        divisor = denom.get(point["ts"])
        if divisor is None or divisor <= 0:
            missing = True
            continue
        value = point["value"] / divisor * factor
        if math.isfinite(value):
            points.append({"ts": point["ts"], "value": value})
        else:
            missing = True
    issue = missing or denominator["status"] != "available" or numerator["status"] == "partial"
    error = (
        "denominator_missing" if missing or not denominator["series"] else numerator["error"] or denominator["error"]
    )
    if not numerator["series"]:
        return {**numerator, "unit": "%"}
    if not points and denominator["status"] in ("forbidden", "unavailable"):
        return _result("%", status=denominator["status"], error=denominator["error"])
    return _result("%", points, "partial" if issue else None, error if issue else None)


def _combine(parts, unit, error=None):
    if not parts:
        return _result(unit, status=error.status if error else None, error=error.code if error else None)
    by_time = {}
    for part in parts:
        for point in part["series"]:
            by_time.setdefault(point["ts"], []).append(point["value"])
    # Retain measured subtotal when some children are absent, always labelled
    # partial. Never turn missing children into exact totals or zero samples.
    partial = bool(error) or any(p["status"] != "available" for p in parts)
    points = []
    for ts, values in sorted(by_time.items()):
        partial |= len(values) != len(parts)
        try:
            value = math.fsum(values)
        except OverflowError:
            partial = True
            error = error or _Failure("partial", "numeric_overflow")
            continue
        if math.isfinite(value):
            points.append({"ts": ts, "value": value})
        else:
            partial = True
    if points:
        return _result(
            unit,
            points,
            "partial" if partial else None,
            error.code if error else "incomplete_children" if partial else None,
        )
    failures = [p for p in parts if p["status"] in ("forbidden", "unavailable", "partial")]
    if failures:
        return _result(unit, status=failures[0]["status"], error=failures[0]["error"])
    return _result(unit, status=error.status if error else None, error=error.code if error else None)


def _owned(resource, project, kind, instance=None):
    if not isinstance(resource, dict) or not _same(resource.get("project_id"), project):
        return False
    if resource.get("type") != kind:
        return False
    return instance is None or _same(resource.get("instance_id"), instance)


def _instance(reader, resource, keys, children, child_errors):
    results = {}
    for key in keys:
        spec = _METERS.get(key)
        if spec is None:
            results[key] = _result("", error="unsupported_metric")
            continue
        kind, meter, unit, output_unit, counter = spec
        if kind != "instance":
            rows = children.get(kind, [])
            parts = [_series(reader, child, meter, unit, output_unit, counter) for child in rows]
            intervals = {gran for child in rows for _, _, gran in reader.samples(child, meter, unit, counter)[0]}
            error = child_errors.get(kind)
            if len(intervals) > 1:
                error = error or _Failure("partial", "granularity_mismatch")
            results[key] = _combine(parts, output_unit, error)
            continue
        value = _series(reader, resource, meter, unit, output_unit, counter)
        if key in ("cpu", "memory", "gpu_mem"):
            denominator_name = {"cpu": "vcpus", "memory": "memory", "gpu_mem": "vgpu.memory.total"}[key]
            denominator_unit = "vcpu" if key == "cpu" else "MiB"
            denominator = _series(reader, resource, denominator_name, denominator_unit, denominator_unit)
            native_samples, _ = reader.samples(resource, meter, unit, counter)
            intervals = {ts: gran for ts, _, gran in native_samples}
            raw_gauges, gauge_error = reader.samples(resource, denominator_name, denominator_unit, counter)
            gauges = {ts: (val, gran) for ts, val, gran in raw_gauges}
            previous = {after[0]: before[0] for before, after in zip(native_samples, native_samples[1:], strict=False)}
            stable = []
            for point in denominator["series"]:
                ts, val = point["ts"], point["value"]
                if gauges.get(ts) != (val, intervals.get(ts)):
                    continue
                # A resize spanning a CPU interval has no unambiguous vCPU
                # denominator. Require equal historical gauges at both ends.
                if key == "cpu" and gauges.get(previous.get(ts)) != gauges.get(ts):
                    continue
                stable.append(point)
            denominator = {**denominator, "series": stable}
            if gauge_error:
                denominator.update(status=gauge_error.status, error=gauge_error.code)
            value = _ratio(value, denominator, 100.0 / 1e9 if key == "cpu" else 100.0)
        results[key] = value
    return results


def _children(reader, project, keys, instance=None):
    children, errors = {}, {}
    kinds = {_METERS[key][0] for key in keys if key in _METERS} - {"instance"}
    for kind in sorted(kinds):
        clauses = [{"=": {"project_id": project}}]
        if instance:
            clauses.append({"=": {"instance_id": instance}})
        rows, error = reader.listing(kind, {"and": clauses} if len(clauses) > 1 else clauses[0])
        accepted = [
            row
            for row in rows
            if _owned(row, project, kind, instance) and isinstance(row.get("instance_id"), str) and row["instance_id"]
        ]
        if len(accepted) != len(rows):
            error = _Failure("partial", "ownership_mismatch")
        children[kind], errors[kind] = accepted, error
    return children, errors


def _envelope(reader, entries, *, instances=False, failure=None):
    metrics = [
        metric
        for item in (entries.values() if instances else entries)
        for metric in (item.values() if instances else item["metrics"].values())
    ]
    measured = any(m["series"] for m in metrics)
    incomplete = failure or reader.truncated or any(m["status"] != "available" for m in metrics)
    status = (
        "partial"
        if measured and incomplete
        else "available"
        if measured
        else failure.status
        if failure
        else "not_collected"
    )
    if not measured and not failure:
        bad = next((m for m in metrics if m["status"] in ("forbidden", "unavailable", "partial")), None)
        if bad:
            status = bad["status"]
    return {
        "source": "gnocchi",
        "status": status,
        "error": failure.code if failure else "incomplete_coverage" if incomplete else None,
        "truncated": reader.truncated,
        "instances" if instances else "resources": entries,
    }


def _instance_sync(reader, server, keys):
    project, instance = _field(server, "project_id"), _field(server, "id")
    if not isinstance(project, str) or not project or not isinstance(instance, str) or not instance:
        raise _Failure("forbidden", "ownership_unknown")
    resource = reader.request("GET", f"/resource/instance/{quote(instance, safe='')}")
    if not _owned(resource, project, "instance") or not _same(resource.get("id"), instance):
        raise _Failure("forbidden", "ownership_mismatch")
    children, errors = _children(reader, project, keys, instance)
    return _instance(reader, resource, keys, children, errors)


def _project_sync(reader, project, keys):
    if not isinstance(project, str) or not project:
        raise _Failure("forbidden", "ownership_unknown")
    resources, error = reader.listing("instance", {"=": {"project_id": project}})
    children, errors = _children(reader, project, keys)
    instances = {}
    for resource in resources:
        if not _owned(resource, project, "instance"):
            error = _Failure("partial", "ownership_mismatch")
            continue
        instance = resource["id"]
        matching = {
            kind: [child for child in rows if _same(child.get("instance_id"), instance)]
            for kind, rows in children.items()
        }
        instances[instance] = _instance(reader, resource, keys, matching, errors)
    # A bounded/failed parent listing makes native project coverage partial even
    # if all measurements for the resources we did receive were readable.
    return _envelope(reader, instances, instances=True, failure=error)


def _system_sync(reader):
    resources, failure = [], None
    for kind, meters in _SYSTEM_METERS.items():
        rows, error = reader.listing(kind)
        if error and error.code != "resource_missing":
            failure = error
        for row in rows:
            if row.get("type") != kind:
                failure = _Failure("partial", "malformed_response")
                continue
            actual = row.get("metrics")
            if not isinstance(actual, dict):
                failure = _Failure("partial", "malformed_response")
                continue
            measurements = {
                meter: _series(reader, row, meter, unit, unit) for meter, unit in meters.items() if meter in actual
            }
            if measurements:
                name = row.get("host_name") if kind == "nova_compute" else None
                resources.append(
                    {
                        "id": row["id"][:256],
                        "name": name[:256] if isinstance(name, str) else row["id"][:256],
                        "type": kind,
                        "metrics": measurements,
                    }
                )
    return _envelope(reader, resources, failure=failure)


async def _collect(conn, keys, start, end, step, mode, subject=None):
    def collect():
        reader = _Reader(conn, start, end, step)
        reader.discover()
        if mode == "instance":
            return _instance_sync(reader, subject, keys)
        if mode == "project":
            return _project_sync(reader, subject, keys)
        return _system_sync(reader)

    try:
        if mode == "project" and getattr(conn, "_afterglow_authenticated_project_id", None) != subject:
            raise _Failure("forbidden", "project_scope_mismatch")
        # A caller's Keystone plugin can perform identity I/O during discovery;
        # do not mutate its shared timeout or create replacement credentials.
        return await asyncio.wait_for(asyncio.to_thread(collect), timeout=_DEADLINE_S + 0.1)
    except TimeoutError:
        failure = _Failure("unavailable", "time_budget")
    except _Failure as exc:
        failure = exc
    except Exception:
        failure = _Failure("unavailable", "request_failed")
    if mode == "instance":
        return _failed(keys, failure)
    return {
        "source": None if failure.status == "not_configured" else "gnocchi",
        "status": failure.status,
        "error": failure.code,
        "truncated": failure.code in ("time_budget", "request_budget", "response_budget"),
        "instances" if mode == "project" else "resources": {} if mode == "project" else [],
    }


async def instance_series(conn, server, metrics: list[str], *, start_ts: int, end_ts: int, step_s: int) -> dict:
    """Return normalized meters for a Nova-authorized server with project_id."""
    return await _collect(conn, list(dict.fromkeys(metrics)), start_ts, end_ts, step_s, "instance", server)


async def project_series(conn, project_id: str, metrics: list[str], *, start_ts: int, end_ts: int, step_s: int) -> dict:
    """Return per-instance measurements within caller-native project visibility.

    vcpus and memory_allocated are internal historical denominator gauges. A
    completed native listing does not certify that all Nova instances exist in
    Gnocchi; consumers must compare authorized Nova inventory for project totals.
    """
    return await _collect(conn, list(dict.fromkeys(metrics)), start_ts, end_ts, step_s, "project", project_id)


async def system_series(conn, *, start_ts: int, end_ts: int, step_s: int) -> dict:
    """Return only whitelisted measured host/storage gauges, under native policy.

    The API caller owns the system-admin gate; no global inventory cache, service
    credential fallback, arbitrary metadata or tenant volume allocation is used.
    """
    return await _collect(conn, [], start_ts, end_ts, step_s, "system")
