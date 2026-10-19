"""Uncached caller-session Aodh management and independent Gnocchi inspection.

Catalog endpoints only; action URLs are data, never HTTP destinations. Native
policy/rule validation remains authoritative. Capabilities are not plugin discovery.
All bounds are invocation-local; transport never retries or reauthenticates writes.
"""

import json
import math
import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from keystoneauth1.exceptions.catalog import EndpointNotFound

MAX_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 4 * MAX_BYTES
MAX_CALLS = 12
DEADLINE = 8.0
REQUEST_TIMEOUT = 2.0
MAX_SAMPLES = 512
MAX_SECTION_ITEMS = 256
TYPES = (
    "gnocchi_resources_threshold",
    "gnocchi_aggregation_by_metrics_threshold",
    "gnocchi_aggregation_by_resources_threshold",
    "event",
    "composite",
    "loadbalancer_member_health",
    "prometheus",
)
ACTIONS = ("alarm_actions", "ok_actions", "insufficient_data_actions")
SCHEMES = {"http", "https", "trust+http", "trust+https", "log", "zaqar", "trust+zaqar", "trust+heat"}
ALARM_STRINGS = (
    "alarm_id",
    "name",
    "description",
    "type",
    "severity",
    "state",
    "state_reason",
    "state_timestamp",
    "evaluate_timestamp",
    "timestamp",
    "project_id",
    "user_id",
)


class Failure(Exception):
    def __init__(self, status, code, http_status=503):
        self.status, self.code, self.http_status = status, "telemetry_" + code, http_status
        super().__init__(self.code)


def malformed():
    raise Failure("unavailable", "malformed_response", 502)


def number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def identifier(value):
    if not isinstance(value, str):
        malformed()
    try:
        return str(UUID(value))
    except ValueError:
        malformed()


def text(value, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or len(value) > 16384:
        malformed()
    return value


def obj(value):
    if not isinstance(value, dict):
        malformed()
    return value


def array(value):
    if not isinstance(value, list):
        malformed()
    return value


def json_tree(value, depth=0):
    """Validate opaque native rule JSON without silently dropping provider fields."""
    if depth > 24:
        malformed()
    if value is None or isinstance(value, (str, bool)) or number(value):
        return value
    if isinstance(value, list):
        return [json_tree(v, depth + 1) for v in value]
    if isinstance(value, dict):
        return {text(k): json_tree(v, depth + 1) for k, v in value.items()}
    malformed()


def action(value, writing=False):
    value = text(value)
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in SCHEMES or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError
        if parsed.scheme.startswith("trust+") and "@" in parsed.netloc:
            if writing:
                raise ValueError
            # Aodh injects trust_id:delete@. Remove only userinfo, retaining host,
            # path/query and hostless schemes (urlunsplit otherwise loses ://).
            authority = parsed.netloc.rsplit("@", 1)[1]
            return (
                value.split(":", 1)[0]
                + "://"
                + authority
                + urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
            )
        if parsed.scheme in {"http", "https", "trust+http", "trust+https"}:
            if not parsed.hostname:
                raise ValueError
            _ = parsed.port  # Validate malformed ports/IPv6 before forwarding data.
        return value
    except ValueError:
        if writing:
            raise Failure("unavailable", "invalid_action", 400) from None
        malformed()


def alarm(value):
    value = obj(value)
    result = {k: text(value[k], nullable=True) for k in ALARM_STRINGS if k in value}
    identifier(value.get("alarm_id"))
    for key in ("enabled", "repeat_actions"):
        if key in value:
            if type(value[key]) is not bool:
                malformed()
            result[key] = value[key]
    for key in ACTIONS:
        if key in value:
            result[key] = [action(v) for v in array(value[key])]
    if "time_constraints" in value:
        result["time_constraints"] = [json_tree(obj(v)) for v in array(value["time_constraints"])]
    kind = value.get("type")
    if kind in TYPES and kind + "_rule" in value:
        result[kind + "_rule"] = json_tree(obj(value[kind + "_rule"]))
    return result


def alarm_body(value):
    """Full editable definition. Require the rule; never replace it with defaults."""
    try:
        value = obj(value)
        kind = value.get("type")
        allowed = {"name", "description", "type", "enabled", "severity", "repeat_actions", "time_constraints", *ACTIONS}
        if kind not in TYPES or set(value) - (allowed | {kind + "_rule"}):
            raise ValueError
        if not text(value.get("name")).strip() or not isinstance(value.get(kind + "_rule"), dict):
            raise ValueError
        result = json_tree(value)
        if "severity" in value and value["severity"] not in ("low", "moderate", "critical"):
            raise ValueError
        for key in ("enabled", "repeat_actions"):
            if key in value and type(value[key]) is not bool:
                raise ValueError
        if "description" in value:
            text(value["description"])
        if "time_constraints" in value:
            for row in array(value["time_constraints"]):
                obj(row)
        for key in ACTIONS:
            if key in value:
                result[key] = [action(v, writing=True) for v in array(value[key])]
        if len(json.dumps(result, allow_nan=False).encode()) > 256 * 1024:
            raise ValueError
        return result
    except (Failure, ValueError, TypeError, RecursionError):
        raise Failure("unavailable", "invalid_alarm", 400) from None


class Transport:
    def __init__(self, conn, service):
        self.conn, self.service = conn, service
        self.deadline = time.monotonic() + DEADLINE
        self.calls = self.bytes = 0
        self.endpoint = None

    def remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Failure("unavailable", "time_budget")
        return left

    def discover(self):
        try:
            endpoint = self.conn.session.get_endpoint(
                service_type=self.service,
                interface=self.conn.config.get_interface(self.service),
                region_name=self.conn.config.get_region_name(self.service),
                skip_discovery=True,
            )
        except EndpointNotFound:
            raise Failure("not_configured", "endpoint_missing") from None
        except Exception:
            raise Failure("unavailable", "catalog_unavailable") from None
        if not endpoint:
            raise Failure("not_configured", "endpoint_missing")
        try:
            parsed = urlsplit(endpoint)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
            _ = parsed.port
            base = endpoint.rstrip("/")
            version = "v2" if self.service == "alarming" else "v1"
            # Accept root or versioned catalog, never append duplicate versions.
            if not base.endswith("/" + version):
                if re.search(r"/v\d+(?:\.\d+)?$", base):
                    raise ValueError
                base += "/" + version
            self.endpoint = base
        except (ValueError, TypeError, AttributeError):
            raise Failure("unavailable", "invalid_endpoint") from None
        self.remaining()

    def request(self, method, path, *, params=None, body=None):
        mutation = method != "GET"
        response = None
        try:
            if self.endpoint is None:
                self.discover()
            left = self.remaining()
            if self.calls >= MAX_CALLS:
                raise Failure("unavailable", "request_budget")
            self.calls += 1
            response = self.conn.session.request(
                self.endpoint + path,
                method,
                params=params,
                json=body,
                timeout=min(REQUEST_TIMEOUT, left),
                stream=True,
                raise_exc=False,
                redirect=0,
                connect_retries=0,
                status_code_retries=0,
                allow_reauth=False,
                log=False,
            )
            status = response.status_code
            if status in (401, 403):
                raise Failure("forbidden", "access_denied", 403)
            if status == 404:
                raise Failure("not_found", "not_found", 404)
            if status in (400, 422):
                raise Failure("unavailable", "native_invalid", 400)
            if status == 409:
                raise Failure("unavailable", "conflict", 409)
            if not 200 <= status < 300:
                raise Failure("unavailable", "mutation_uncertain" if mutation else "native_unavailable", 503)
            if method == "DELETE":
                self.remaining()
                return None
            buffer = bytearray()
            for chunk in response.iter_content(chunk_size=16384):
                self.remaining()
                if not isinstance(chunk, bytes):
                    malformed()
                self.bytes += len(chunk)
                if len(buffer) + len(chunk) > MAX_BYTES or self.bytes > MAX_TOTAL_BYTES:
                    raise Failure("unavailable", "response_budget", 502)
                buffer.extend(chunk)
            self.remaining()
            try:
                return json.loads(buffer, parse_constant=lambda _: malformed())
            except (ValueError, UnicodeError, RecursionError):
                malformed()
        except Failure as exc:
            # Once submitted, any incomplete/unparseable successful reply could
            # hide a committed write. Never suggest automatic resubmission.
            if mutation and response is not None and 200 <= response.status_code < 300:
                raise Failure("unavailable", "mutation_uncertain", 503) from None
            raise exc
        except Exception:
            raise Failure("unavailable", "mutation_uncertain" if mutation else "transport_unavailable", 503) from None
        finally:
            if response is not None:
                response.close()


def section(reader, path, sanitize):
    try:
        data = sanitize(reader.request("GET", path))
        return {"status": "available", "error": None, "data": data}
    except Failure as exc:
        return {"status": exc.status, "error": exc.code, "data": None}


def page(reader, path, limit, marker, sanitize, id_key, extra=None):
    try:
        params = {"limit": limit, **(extra or {})}
        if marker:
            params["marker"] = marker
        rows = array(reader.request("GET", path, params=params))
        items = [sanitize(row) for row in rows[:limit]]
        next_marker = identifier(items[-1].get(id_key)) if items else None
        if next_marker and marker and UUID(next_marker) == UUID(marker):
            malformed()
        return {
            "status": "available",
            "error": None,
            "items": items,
            "next_marker": next_marker,
            "truncated": len(rows) > limit,
        }
    except Failure as exc:
        return {
            "status": exc.status,
            "error": exc.code,
            "items": [],
            "next_marker": None,
            "truncated": exc.code.endswith(("budget", "malformed_response")),
        }


def aggregate(parts):
    statuses = [p["status"] for p in parts]
    if all(s == "available" for s in statuses):
        return "available", None
    if all(s == statuses[0] for s in statuses):
        return statuses[0], next((p["error"] for p in parts if p["error"]), None)
    return "partial", "telemetry_partial"


def aodh_capabilities(value):
    value = obj(value)
    result = {}
    for key in ("api", "alarm_storage"):
        if key in value:
            entries = obj(value[key])
            if len(entries) > MAX_SECTION_ITEMS or any(type(v) is not bool for v in entries.values()):
                malformed()
            result[key] = {text(k): v for k, v in entries.items()}
    if not result:
        malformed()
    return result


def list_alarms(reader, limit=25, marker=None, state=None):
    extra = {"q.field": "state", "q.op": "eq", "q.value": state} if state else None
    return page(reader, "/alarms", limit, marker, alarm, "alarm_id", extra)


def aodh(conn, limit=25, marker=None, state=None):
    reader = Transport(conn, "alarming")
    capabilities = section(reader, "/capabilities", aodh_capabilities)
    alarms = list_alarms(reader, limit, marker, state)
    status, error = aggregate([capabilities, alarms])
    return {
        "status": status,
        "error": error,
        "checked_at": datetime.now(UTC).isoformat(),
        "capabilities": capabilities,
        "alarms": alarms,
    }


def history_row(value):
    value = obj(value)
    identifier(value.get("event_id"))
    return {
        key: text(value[key], nullable=True)
        for key in ("event_id", "type", "timestamp", "user_id", "project_id")
        if key in value
    }


def alarm_detail(conn, alarm_id, limit=25, marker=None):
    reader = Transport(conn, "alarming")
    selected = section(reader, "/alarms/" + alarm_id, alarm)
    history = page(reader, "/alarms/" + alarm_id + "/history", limit, marker, history_row, "event_id")
    status, error = aggregate([selected, history])
    return {"status": status, "error": error, "alarm": selected["data"], "history": history}


def mutate(conn, method, alarm_id=None, body=None):
    payload = alarm_body(body) if method != "DELETE" else None
    reader = Transport(conn, "alarming")
    value = reader.request(method, "/alarms" + ("/" + alarm_id if alarm_id else ""), body=payload)
    if method == "DELETE":
        return None
    try:
        return alarm(value)
    except Failure:
        raise Failure("unavailable", "mutation_uncertain", 503) from None


def fields(value, keys):
    value = obj(value)
    return {key: text(value[key], nullable=True) for key in keys if key in value}


def policy(value):
    value = obj(value)
    result = {"name": text(value.get("name"))}
    if "back_window" in value:
        if type(value["back_window"]) is not int or value["back_window"] < 0:
            malformed()
        result["back_window"] = value["back_window"]
    if "aggregation_methods" in value:
        result["aggregation_methods"] = [text(v) for v in array(value["aggregation_methods"])]
    if "definition" in value:
        result["definition"] = []
        for row in array(value["definition"]):
            row = obj(row)
            safe = {}
            for key in ("granularity", "points", "timespan"):
                if key in row:
                    v = row[key]
                    if v is not None and not isinstance(v, str) and not number(v):
                        malformed()
                    safe[key] = v
            result["definition"].append(safe)
    return result


def metric(value):
    result = fields(value, ("id", "name", "unit", "resource_id", "archive_policy_name", "created_by_project_id"))
    identifier(value.get("id"))
    if "archive_policy" in value:
        result["archive_policy"] = policy(value["archive_policy"])
    return result


def resource(value):
    result = fields(value, ("id", "type", "project_id", "started_at", "ended_at"))
    identifier(value.get("id"))
    result["metrics"] = {text(k): identifier(v) for k, v in obj(value.get("metrics", {})).items()}
    return result


def collection(value, sanitize):
    rows = array(value)
    if len(rows) > MAX_SECTION_ITEMS:
        # Section has no truncation flag: don't silently claim completeness.
        raise Failure("partial", "section_budget", 502)
    return [sanitize(row) for row in rows]


def gnocchi_capabilities(value):
    return {"aggregation_methods": collection(obj(value).get("aggregation_methods"), text)}


def processing(value):
    summary = obj(obj(obj(value).get("storage")).get("summary"))
    safe = {}
    for key in ("measures", "metrics"):
        v = summary.get(key)
        if type(v) is not int or v < 0:
            malformed()
        safe[key] = v
    return {"storage": {"summary": safe}}


def gnocchi(conn):
    reader = Transport(conn, "metric")
    result = {
        "capabilities": section(reader, "/capabilities", gnocchi_capabilities),
        "processing": section(reader, "/status", processing),
        "archive_policies": section(reader, "/archive_policy", lambda v: collection(v, policy)),
        "archive_policy_rules": section(
            reader,
            "/archive_policy_rule",
            lambda v: collection(v, lambda r: fields(r, ("name", "metric_pattern", "archive_policy_name"))),
        ),
        "resource_types": section(
            reader,
            "/resource_type",
            lambda v: collection(v, lambda r: {"name": text(obj(r).get("name"))} if isinstance(r, dict) else text(r)),
        ),
    }
    status, error = aggregate(list(result.values()))
    return {"status": status, "error": error, "checked_at": datetime.now(UTC).isoformat(), **result}


def measures(conn, metric_id, hours=1, aggregation="mean", granularity=None):
    reader = Transport(conn, "metric")
    metadata = section(reader, "/metric/" + metric_id, metric)
    result = {
        "status": metadata["status"],
        "error": metadata["error"],
        "metric": metadata["data"],
        "measures": [],
        "truncated": False,
    }
    # Do not query measures after metadata denial (also preserves useful units).
    if metadata["status"] != "available":
        return result
    stop = datetime.now(UTC)
    start = stop - timedelta(hours=hours)
    params = {"start": start.isoformat(), "stop": stop.isoformat(), "aggregation": aggregation}
    if granularity is not None:
        params["granularity"] = granularity
    try:
        rows = array(reader.request("GET", "/metric/" + metric_id + "/measures", params=params))
        points = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 3 or not number(row[1]) or row[1] <= 0 or not number(row[2]):
                malformed()
            stamp = text(row[0])
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
            except ValueError:
                malformed()
            if start <= parsed <= stop:
                if len(points) < MAX_SAMPLES:
                    points.append({"timestamp": stamp, "granularity": row[1], "value": row[2]})
                else:
                    result["truncated"] = True
        result["measures"] = points
        if result["truncated"]:
            result.update(status="partial", error="telemetry_sample_budget")
    except Failure as exc:
        result.update(status="partial", error=exc.code, truncated=exc.code.endswith("budget"))
    return result
