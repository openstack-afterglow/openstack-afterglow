"""Admin telemetry HTTP behavior with real routes, services and fresh admin checks.

Only identity/provider I/O is synthetic. Responses are requests.Response objects
backed by a streaming urllib3 HTTPResponse, not pre-decoded JSON/service mocks.
No cloud, credentials, background app lifecycle or native action URL is contacted.
"""

import copy
import io
import json
import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.catalog import EndpointNotFound
from requests import Response
from requests.exceptions import ConnectionError, ReadTimeout
from urllib3.response import HTTPResponse

from app.api.deps import get_os_conn, get_token_info
from app.api.identity.admin_telemetry import router
from app.services import keystone, telemetry_admin

PREFIX = "/api/v1/admin/telemetry"
ALARM = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
THIRD = "33333333-3333-4333-8333-333333333333"
METRIC = "44444444-4444-4444-8444-444444444444"
SECRET = "never-echo-provider-or-input-secret"
PROJECT = "test-project-123"
STAMP = "2026-10-17T00:00:00+00:00"


def alarm(alarm_id=ALARM, **fields):
    return {
        "alarm_id": alarm_id,
        "name": "Native alarm",
        "description": "Caller-scoped alarm",
        "type": "gnocchi_resources_threshold",
        "enabled": True,
        "severity": "moderate",
        "repeat_actions": False,
        "state": "ok",
        "state_reason": "Measured below threshold",
        "state_timestamp": STAMP,
        "evaluate_timestamp": STAMP,
        "timestamp": STAMP,
        "project_id": PROJECT,
        "user_id": "test-user-123",
        "alarm_actions": [],
        "ok_actions": [],
        "insufficient_data_actions": [],
        "time_constraints": [],
        "gnocchi_resources_threshold_rule": {
            "resource_type": "instance",
            "resource_id": OTHER,
            "metric": "cpu",
            "aggregation_method": "mean",
            "comparison_operator": "gt",
            "threshold": 123456789,
            "granularity": 300,
            "evaluation_periods": 2,
        },
        **fields,
    }


RULES = {
    "gnocchi_resources_threshold": alarm()["gnocchi_resources_threshold_rule"],
    "gnocchi_aggregation_by_metrics_threshold": {
        "metrics": [METRIC],
        "aggregation_method": "mean",
        "threshold": 0,
        "comparison_operator": "ge",
        "granularity": 300,
        "evaluation_periods": 1,
    },
    "gnocchi_aggregation_by_resources_threshold": {
        "resource_type": "instance",
        "metric": "cpu",
        "query": '{"=":{"project_id":"project"}}',
        "aggregation_method": "mean",
        "threshold": 1,
        "granularity": 60,
        "evaluation_periods": 2,
    },
    "event": {
        "event_type": "compute.instance.delete.end",
        "query": [{"field": "traits.instance_id", "op": "eq", "value": OTHER}],
    },
    "composite": {"and": [{"alarm": ALARM}, {"not": {"alarm": OTHER}}]},
    "loadbalancer_member_health": {"pool_id": OTHER},
    "prometheus": {"query": "up == 0", "threshold": 0, "comparison_operator": "eq", "evaluation_periods": 1},
}
EDITABLE = {
    "name",
    "description",
    "type",
    "enabled",
    "severity",
    "repeat_actions",
    "alarm_actions",
    "ok_actions",
    "insufficient_data_actions",
    "time_constraints",
}


def body(kind="gnocchi_resources_threshold", **fields):
    result = {key: copy.deepcopy(value) for key, value in alarm().items() if key in EDITABLE}
    result.update(type=kind, **{kind + "_rule": copy.deepcopy(RULES[kind])})
    result.update(fields)
    return result


class InterruptedBody(io.BytesIO):
    def read(self, size=-1):
        if self.tell() >= 16384:
            raise OSError(SECRET)
        return super().read(size)


class StreamedResponse(Response):
    def __init__(self, value=None, status=200, *, raw=None, interrupted=False):
        super().__init__()
        payload = json.dumps(value).encode() if raw is None else raw
        self.status_code = status
        self.headers["Content-Type"] = "application/json"
        self.headers["Content-Length"] = str(len(payload))
        buffer = InterruptedBody(payload) if interrupted else io.BytesIO(payload)
        self.raw = HTTPResponse(body=buffer, preload_content=False)
        self.close_count = 0

    def close(self):
        self.close_count += 1
        super().close()


class Cloud:
    def __init__(self):
        self.endpoints = {"alarming": "https://aodh.example/v2", "metric": "https://gnocchi.example/v1"}
        self.calls, self.discovery, self.responses = [], [], []
        self.overrides = {}
        self.alarms = [alarm()]
        self.history = []
        self.resources = []
        self.metrics = []
        self.measures = []
        self.page_size = 100
        self.conn = SimpleNamespace(
            session=self,
            config=SimpleNamespace(get_interface=lambda _: "internal", get_region_name=lambda _: "region-a"),
            _afterglow_authenticated_project_id=PROJECT,
        )

    def get_endpoint(self, **kwargs):
        self.discovery.append(kwargs)
        endpoint = self.endpoints[kwargs["service_type"]]
        if isinstance(endpoint, Exception):
            raise endpoint
        return endpoint

    def page(self, rows, params, key):
        marker = params.get("marker")
        index = next((i + 1 for i, row in enumerate(rows) if row[key] == marker), 0) if marker else 0
        return rows[index : index + min(params["limit"], self.page_size)]

    def request(
        self,
        url,
        method,
        *,
        params=None,
        json=None,
        timeout,
        stream,
        raise_exc,
        redirect,
        connect_retries,
        status_code_retries,
        allow_reauth,
        log,
    ):
        parsed = urlsplit(url)
        service, version = ("alarming", "/v2") if parsed.hostname == "aodh.example" else ("metric", "/v1")
        path = unquote(parsed.path.removeprefix(version))
        call = {
            "service": service,
            "method": method,
            "path": path,
            "params": copy.deepcopy(params),
            "json": copy.deepcopy(json),
        }
        self.calls.append(call)
        assert parsed.hostname in {"aodh.example", "gnocchi.example"}, "Action URLs must never be fetched"
        assert 0 < timeout <= 2
        assert stream is True and raise_exc is False
        assert redirect == connect_retries == status_code_retries == 0
        assert allow_reauth is False and log is False
        override = self.overrides.get((service, method, path))
        if override is not None:
            value = override(call) if callable(override) else override
        elif service == "alarming":
            if method == "GET" and path == "/capabilities":
                value = {"alarm_storage": {"storage:production_ready": True}}
            elif method == "GET" and path == "/alarms":
                state = params.get("q.value")
                rows = [row for row in self.alarms if not state or row["state"] == state]
                value = self.page(rows, params, "alarm_id")
            elif method == "GET" and path.endswith("/history"):
                value = self.page(self.history, params, "event_id")
            elif method == "POST" and path == "/alarms":
                row = {**copy.deepcopy(json), "alarm_id": THIRD, "state": "insufficient data"}
                self.alarms.append(row)
                value = StreamedResponse(row, 201)
            else:
                alarm_id = path.rsplit("/", 1)[-1]
                row = next((row for row in self.alarms if row["alarm_id"] == alarm_id), None)
                if row is None:
                    value = StreamedResponse({"error": SECRET}, 404)
                elif method == "PUT":
                    row.update(copy.deepcopy(json))
                    value = row
                elif method == "DELETE":
                    self.alarms.remove(row)
                    value = StreamedResponse(status=204, raw=b"")
                else:
                    assert method == "GET"
                    value = row
        elif method == "GET" and path == "/capabilities":
            value = {"aggregation_methods": ["mean", "sum", "rate:mean"]}
        elif method == "GET" and path == "/status":
            value = {"storage": {"summary": {"measures": 3, "metrics": 2}}}
        elif method == "GET" and path in {"/archive_policy", "/archive_policy_rule", "/resource_type"}:
            value = []
        elif method == "GET" and path.startswith("/resource/"):
            value = self.page(self.resources, params, "id")
        elif method == "GET" and path == "/metric":
            value = self.page(self.metrics, params, "id")
        elif method == "GET" and path == f"/metric/{METRIC}/measures":
            value = self.measures
        elif method == "GET" and path == f"/metric/{METRIC}":
            value = {"id": METRIC, "name": "cpu", "unit": "ns", "resource_id": OTHER, "archive_policy_name": "medium"}
        else:
            raise AssertionError(f"Unexpected native request: {method} {path}")
        if isinstance(value, Exception):
            raise value
        response = value if isinstance(value, Response) else StreamedResponse(value)
        response.url = url
        self.responses.append(response)
        return response


@pytest.fixture
def api(monkeypatch, auth_directory):
    """Retain real require_admin/domain/token/role checks; replace native I/O only."""
    cloud = Cloud()
    token = {
        "token": "synthetic-native-token",
        "user_id": "test-user-123",
        "project_id": PROJECT,
        "connection_project_id": PROJECT,
        "domain_id": "default",
        "identity_domain_id": "default",
        "is_system_admin": True,
    }
    auth_directory.assignments.append(
        {
            "user": {"id": token["user_id"]},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    native_checks = []

    def validate_token(native_token, project_id="", **kwargs):
        native_checks.append((native_token, project_id))
        return {key: value for key, value in token.items() if key != "is_system_admin"}

    monkeypatch.setattr(keystone, "validate_token", validate_token)
    app = FastAPI()
    app.include_router(router, prefix=PREFIX)
    app.dependency_overrides[get_os_conn] = lambda: cloud.conn
    app.dependency_overrides[get_token_info] = lambda: dict(token)
    return SimpleNamespace(app=app, cloud=cloud, token=token, directory=auth_directory, native_checks=native_checks)


@pytest.fixture
async def client(api):
    async with AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test") as http:
        yield http
    assert all(response.close_count == 1 for response in api.cloud.responses)


def safe(response, status=200):
    assert response.status_code == status, response.text
    assert "no-store" in response.headers.get("cache-control", "")
    assert SECRET not in response.text
    return response.json() if response.content else None


@pytest.mark.parametrize("missing", [None, EndpointNotFound()])
async def test_aodh_absence_is_explicit_and_does_not_contact_provider(api, client, missing):
    api.cloud.endpoints["alarming"] = missing
    result = safe(await client.get(PREFIX + "/aodh"))
    assert result["status"] == "not_configured"
    assert result["capabilities"]["status"] == result["alarms"]["status"] == "not_configured"
    assert result["alarms"]["items"] == []
    assert api.cloud.calls == []


@pytest.mark.parametrize("failed,status", [("/capabilities", 403), ("/alarms", 403), ("/capabilities", 500)])
async def test_aodh_capabilities_and_alarm_failures_are_independent(api, client, failed, status):
    api.cloud.overrides[("alarming", "GET", failed)] = StreamedResponse({"error": SECRET}, status)
    result = safe(await client.get(PREFIX + "/aodh"))
    section = "capabilities" if failed == "/capabilities" else "alarms"
    healthy = "alarms" if section == "capabilities" else "capabilities"
    assert result["status"] == "partial"
    assert result[section]["status"] == ("forbidden" if status == 403 else "unavailable")
    assert result[healthy]["status"] == "available"
    assert {call["path"] for call in api.cloud.calls} == {"/capabilities", "/alarms"}


@pytest.mark.parametrize("state", ["ok", "alarm", "insufficient data"])
async def test_aodh_native_state_filter_and_provider_clamped_pages_continue_to_explicit_empty(api, client, state):
    api.cloud.page_size = 1
    api.cloud.alarms = [
        alarm(ALARM, state=state),
        alarm(OTHER, state=state),
        alarm(THIRD, state="alarm" if state == "ok" else "ok"),
    ]
    marker, seen = None, []
    for expected in (ALARM, OTHER, None):
        params = {"limit": 25, "state": state}
        if marker:
            params["marker"] = marker
        result = safe(await client.get(PREFIX + "/aodh/alarms", params=params))
        assert result["status"] == "available"
        assert result["next_marker"] == expected
        if expected:
            assert [row["alarm_id"] for row in result["items"]] == [expected]
            seen.extend(result["items"])
        else:
            assert result["items"] == []
            assert result["truncated"] is False
        marker = result["next_marker"]
    assert len(seen) == 2
    assert [call["params"].get("marker") for call in api.cloud.calls] == [None, ALARM, OTHER]
    assert all(
        call["params"]
        == {"limit": 25, "q.field": "state", "q.op": "eq", "q.value": state, **({"marker": marker} if marker else {})}
        for call, marker in zip(api.cloud.calls, (None, ALARM, OTHER), strict=True)
    )


@pytest.mark.parametrize("status,expected", [(403, "forbidden"), (404, "not_found"), (500, "unavailable")])
async def test_aodh_history_failure_does_not_discard_alarm(api, client, status, expected):
    api.cloud.overrides[("alarming", "GET", f"/alarms/{ALARM}/history")] = StreamedResponse({"detail": SECRET}, status)
    result = safe(await client.get(PREFIX + f"/aodh/alarms/{ALARM}"))
    assert result["alarm"]["alarm_id"] == ALARM
    assert result["history"]["status"] == expected
    assert result["history"]["items"] == []


async def test_aodh_alarm_and_history_output_whitelists_exclude_secret_metadata(api, client):
    api.cloud.alarms[0].update(token=SECRET, links=[SECRET], internal_config={"password": SECRET})
    api.cloud.history = [
        {
            "event_id": OTHER,
            "type": "rule change",
            "timestamp": STAMP,
            "user_id": "operator",
            "project_id": PROJECT,
            "detail": json.dumps({"alarm_actions": [SECRET]}),
            "credentials": SECRET,
        }
    ]
    result = safe(await client.get(PREFIX + f"/aodh/alarms/{ALARM}"))
    assert set(result["alarm"]) <= set(alarm())
    assert result["alarm"]["gnocchi_resources_threshold_rule"] == RULES["gnocchi_resources_threshold"]
    assert result["history"]["items"] == [
        {
            "event_id": OTHER,
            "type": "rule change",
            "timestamp": STAMP,
            "user_id": "operator",
            "project_id": PROJECT,
        }
    ]
    assert result["history"]["next_marker"] == OTHER


@pytest.mark.parametrize("kind", RULES)
async def test_all_seven_native_rule_bodies_create_read_edit_and_delete_without_losing_settings(api, client, kind):
    constraints = [{"name": "business hours", "start": "0 9 * * 1-5", "duration": 28800, "timezone": "Asia/Seoul"}]
    original = body(
        kind, time_constraints=constraints, alarm_actions=["https://receiver.example/hook?token=operator-webhook"]
    )
    created = safe(await client.post(PREFIX + "/aodh/alarms", json=original), 201)
    assert created["alarm_id"] == THIRD
    assert created[kind + "_rule"] == RULES[kind]
    assert api.cloud.calls[-1]["json"] == original
    detail = safe(await client.get(PREFIX + f"/aodh/alarms/{THIRD}"))["alarm"]
    edited = {key: value for key, value in detail.items() if key in EDITABLE or key == kind + "_rule"}
    edited.update(name="Updated", enabled=False, repeat_actions=True, severity="critical")
    updated = safe(await client.put(PREFIX + f"/aodh/alarms/{THIRD}", json=edited))
    assert updated["enabled"] is False
    assert updated["repeat_actions"] is True
    assert updated["severity"] == "critical"
    assert updated["time_constraints"] == constraints
    assert updated[kind + "_rule"] == RULES[kind]
    assert api.cloud.calls[-1]["json"] == edited
    safe(await client.delete(PREFIX + f"/aodh/alarms/{THIRD}"), 204)
    missing = safe(await client.get(PREFIX + f"/aodh/alarms/{THIRD}"))
    assert missing["status"] == "partial" and missing["alarm"] is None
    assert [call["method"] for call in api.cloud.calls if call["method"] != "GET"] == ["POST", "PUT", "DELETE"]


@pytest.mark.parametrize(
    "url",
    [
        "http://receiver.example/hook",
        "https://receiver.example/hook?token=explicit-webhook",
        "trust+http://receiver.example/hook",
        "trust+https://receiver.example/hook",
        "log://",
        "zaqar://?topic=alerts&subscriber=operator&ttl=60",
        "trust+zaqar://?queue_name=alerts",
        "trust+heat://",
    ],
)
@pytest.mark.parametrize("field", ["alarm_actions", "ok_actions", "insufficient_data_actions"])
async def test_native_action_schemes_are_stored_without_fetching_or_rewriting(api, client, url, field):
    payload = body(**{field: [url]})
    result = safe(await client.post(PREFIX + "/aodh/alarms", json=payload), 201)
    assert result[field] == [url]
    assert api.cloud.calls == [
        {"service": "alarming", "method": "POST", "path": "/alarms", "params": None, "json": payload}
    ]


@pytest.mark.parametrize(
    "stored,editable",
    [
        (
            f"trust+http://{SECRET}:delete@receiver.example/hook?token=keep",
            "trust+http://receiver.example/hook?token=keep",
        ),
        (f"trust+https://{SECRET}:delete@receiver.example/hook", "trust+https://receiver.example/hook"),
        (f"trust+zaqar://{SECRET}:delete@?queue_name=alerts", "trust+zaqar://?queue_name=alerts"),
        (f"trust+heat://{SECRET}:delete@", "trust+heat://"),
    ],
)
async def test_aodh_injected_trust_credentials_are_stripped_for_roundtrip_edit(api, client, stored, editable):
    for field in ("alarm_actions", "ok_actions", "insufficient_data_actions"):
        api.cloud.alarms[0][field] = [stored]
    listed = safe(await client.get(PREFIX + "/aodh/alarms"))["items"][0]
    detail = safe(await client.get(PREFIX + f"/aodh/alarms/{ALARM}"))["alarm"]
    for item in (listed, detail):
        for field in ("alarm_actions", "ok_actions", "insufficient_data_actions"):
            assert item[field] == [editable]
    payload = {key: value for key, value in detail.items() if key in EDITABLE or key.endswith("_rule")}
    result = safe(await client.put(PREFIX + f"/aodh/alarms/{ALARM}", json=payload))
    assert api.cloud.calls[-1]["json"] == payload
    assert result["alarm_actions"] == [editable]


@pytest.mark.parametrize(
    "url",
    [
        f"trust+http://{SECRET}@receiver.example/hook",
        f"trust+https://{SECRET}:delete@receiver.example/hook",
        f"trust+zaqar://{SECRET}:delete@?queue_name=alerts",
        f"trust+heat://{SECRET}:delete@",
        f"mailto:{SECRET}@example.test",
        f"slack://{SECRET}",
        f"telegram://{SECRET}",
        f"test://{SECRET}",
        f"file:///{SECRET}",
        f"https://receiver.example/{SECRET}\nInjected: yes",
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_supplied_trust_ids_and_non_native_action_schemes_are_rejected_without_echo(api, client, url, method):
    target = "/aodh/alarms" + (f"/{ALARM}" if method == "PUT" else "")
    response = await client.request(method, PREFIX + target, json=body(alarm_actions=[url]))
    assert response.status_code in (400, 422)
    safe(response, response.status_code)
    assert api.cloud.calls == []


@pytest.mark.parametrize("kind", RULES)
async def test_native_rule_semantics_are_forwarded_to_provider_validation(api, client, kind):
    # Unknown fields and incomplete rules are native policy/semantic decisions,
    # not a second Afterglow schema that silently drops extension settings.
    opaque = {"provider_extension": {"nested": [False, 0, None]}, "native_invalid_semantics": True}
    payload = body(kind, **{kind + "_rule": opaque})
    api.cloud.overrides[("alarming", "POST", "/alarms")] = StreamedResponse({"faultstring": SECRET}, 422)
    result = safe(await client.post(PREFIX + "/aodh/alarms", json=payload), 400)
    assert result == {"detail": {"code": "telemetry_native_invalid"}}
    assert api.cloud.calls[0]["json"] == payload


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize("failure", ["timeout", "connection", "server", "redirect", "malformed", "stream"])
async def test_uncertain_mutations_are_not_retried_redirected_or_reauthenticated(api, client, method, failure):
    native_path = "/alarms" + (f"/{ALARM}" if method != "POST" else "")
    failures = {
        "timeout": ReadTimeout(SECRET),
        "connection": ConnectionError(SECRET),
        "server": StreamedResponse({"detail": SECRET}, 500),
        "redirect": StreamedResponse({"detail": SECRET}, 307),
        "malformed": StreamedResponse(raw=b'{"secret":"' + SECRET.encode()),
        "stream": StreamedResponse(raw=b" " * 32768, interrupted=True),
    }
    if method == "DELETE" and failure in {"malformed", "stream"}:
        # A DELETE has no successful response body to decode. Model transport
        # loss before receiving status instead of inventing a JSON requirement.
        upstream = ReadTimeout(SECRET)
    else:
        upstream = failures[failure]
    api.cloud.overrides[("alarming", method, native_path)] = upstream
    response = await client.request(
        method, PREFIX + "/aodh" + native_path, **({"json": body()} if method != "DELETE" else {})
    )
    assert safe(response, 503) == {"detail": {"code": "telemetry_mutation_uncertain"}}
    assert len(api.cloud.calls) == 1


@pytest.mark.parametrize(
    "native_status,expected,code",
    [
        (400, 400, "native_invalid"),
        (422, 400, "native_invalid"),
        (401, 403, "access_denied"),
        (403, 403, "access_denied"),
        (404, 404, "not_found"),
        (409, 409, "conflict"),
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
async def test_mutation_native_errors_are_fixed_safe_no_store_responses(
    api, client, native_status, expected, code, method
):
    path = "/alarms" + (f"/{ALARM}" if method != "POST" else "")
    api.cloud.overrides[("alarming", method, path)] = StreamedResponse({"error": SECRET}, native_status)
    response = await client.request(method, PREFIX + "/aodh" + path, **({"json": body()} if method != "DELETE" else {}))
    assert safe(response, expected) == {"detail": {"code": "telemetry_" + code}}
    assert len(api.cloud.calls) == 1


@pytest.mark.parametrize(
    "reply",
    [
        {},
        {"alarms": []},
        [None],
        [{"alarm_id": "not-a-uuid", "name": SECRET}],
        [alarm(enabled="true")],
        [alarm(alarm_actions=[123])],
        [alarm(gnocchi_resources_threshold_rule=[])],
    ],
)
async def test_malformed_alarm_shapes_are_not_healthy_empty_lists(api, client, reply):
    api.cloud.overrides[("alarming", "GET", "/alarms")] = StreamedResponse(reply)
    result = safe(await client.get(PREFIX + "/aodh/alarms"))
    assert result["status"] == "unavailable"
    assert result["error"] == "telemetry_malformed_response"
    assert result["items"] == []


@pytest.mark.parametrize("failure", ["invalid_json", "invalid_utf8", "oversize", "interrupted"])
async def test_streamed_read_failures_close_response_and_do_not_expose_body(api, client, failure):
    replies = {
        "invalid_json": StreamedResponse(raw=b'{"secret":"' + SECRET.encode()),
        "invalid_utf8": StreamedResponse(raw=b"\xff" + SECRET.encode()),
        "oversize": StreamedResponse(raw=b" " * (1024 * 1024 + 1)),
        "interrupted": StreamedResponse(raw=b" " * 32768, interrupted=True),
    }
    response = replies[failure]
    api.cloud.overrides[("alarming", "GET", "/alarms")] = response
    result = safe(await client.get(PREFIX + "/aodh/alarms"))
    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert response.close_count == 1
    assert response.raw.closed


async def test_oversized_native_page_is_bounded_with_resumable_marker(api, client):
    api.cloud.overrides[("alarming", "GET", "/alarms")] = [alarm(ALARM), alarm(OTHER), alarm(THIRD)]
    result = safe(await client.get(PREFIX + "/aodh/alarms", params={"limit": 2}))
    assert [row["alarm_id"] for row in result["items"]] == [ALARM, OTHER]
    assert result["next_marker"] == OTHER and result["truncated"] is True


async def test_repeated_native_marker_is_rejected_instead_of_looping(api, client):
    api.cloud.overrides[("alarming", "GET", "/alarms")] = [alarm(ALARM)]
    result = safe(await client.get(PREFIX + "/aodh/alarms", params={"marker": ALARM}))
    assert result["status"] == "unavailable" and result["items"] == []
    assert result["next_marker"] is None
    assert len(api.cloud.calls) == 1


GNOCCHI_SECTIONS = {
    "capabilities": "/capabilities",
    "processing": "/status",
    "archive_policies": "/archive_policy",
    "archive_policy_rules": "/archive_policy_rule",
    "resource_types": "/resource_type",
}


@pytest.mark.parametrize("failed,path", GNOCCHI_SECTIONS.items())
@pytest.mark.parametrize("native_status,expected", [(403, "forbidden"), (404, "not_found"), (503, "unavailable")])
async def test_gnocchi_diagnostic_sections_fail_independently(api, client, failed, path, native_status, expected):
    api.cloud.overrides[("metric", "GET", path)] = StreamedResponse({"detail": SECRET}, native_status)
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["status"] == "partial"
    assert result[failed]["status"] == expected and result[failed]["data"] is None
    for name in GNOCCHI_SECTIONS.keys() - {failed}:
        assert result[name]["status"] == "available"
    assert len(api.cloud.calls) == 5
    assert {call["path"] for call in api.cloud.calls} == set(GNOCCHI_SECTIONS.values())


async def test_gnocchi_absence_does_not_make_aodh_absent(api, client):
    api.cloud.endpoints["metric"] = None
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["status"] == "not_configured"
    assert all(result[key]["status"] == "not_configured" for key in GNOCCHI_SECTIONS)
    assert api.cloud.calls == []
    aodh = safe(await client.get(PREFIX + "/aodh"))
    assert aodh["status"] == "available"


async def test_gnocchi_diagnostics_whitelist_policies_rules_types_and_processing(api, client):
    api.cloud.overrides.update(
        {
            ("metric", "GET", "/capabilities"): {"aggregation_methods": ["mean", "rate:mean"], "secret": SECRET},
            ("metric", "GET", "/status"): {
                "storage": {"summary": {"measures": 0, "metrics": 2, "secret": SECRET}, "details": SECRET},
                "configuration": SECRET,
            },
            ("metric", "GET", "/archive_policy"): [
                {
                    "name": "medium",
                    "back_window": 0,
                    "aggregation_methods": ["mean"],
                    "definition": [{"granularity": 300, "points": 288, "timespan": "1 day, 0:00:00", "secret": SECRET}],
                    "configuration": SECRET,
                }
            ],
            ("metric", "GET", "/archive_policy_rule"): [
                {
                    "name": "cpu",
                    "metric_pattern": "cpu*",
                    "archive_policy_name": "medium",
                    "secret": SECRET,
                }
            ],
            ("metric", "GET", "/resource_type"): ["generic", {"name": "instance", "attributes": {"password": SECRET}}],
        }
    )
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["status"] == "available"
    datetime.fromisoformat(result["checked_at"])
    assert result["capabilities"]["data"] == {"aggregation_methods": ["mean", "rate:mean"]}
    assert result["processing"]["data"] == {"storage": {"summary": {"measures": 0, "metrics": 2}}}
    assert result["archive_policies"]["data"] == [
        {
            "name": "medium",
            "back_window": 0,
            "aggregation_methods": ["mean"],
            "definition": [{"granularity": 300, "points": 288, "timespan": "1 day, 0:00:00"}],
        }
    ]
    assert result["archive_policy_rules"]["data"] == [
        {"name": "cpu", "metric_pattern": "cpu*", "archive_policy_name": "medium"}
    ]
    assert result["resource_types"]["data"] == ["generic", {"name": "instance"}]


@pytest.mark.parametrize(
    "section,path,reply",
    [
        ("capabilities", "/capabilities", {"aggregation_methods": "mean"}),
        ("processing", "/status", {"storage": {"summary": {"metrics": 1, "measures": True}}}),
        ("processing", "/status", {"storage": {"summary": {"metrics": -1, "measures": 0}}}),
        ("archive_policies", "/archive_policy", [{"name": "bad", "back_window": -1}]),
        ("archive_policies", "/archive_policy", [{"name": "bad", "definition": [{"granularity": math.inf}]}]),
        ("archive_policies", "/archive_policy", [{"name": "bad", "definition": [{"granularity": 10**400}]}]),
        ("archive_policy_rules", "/archive_policy_rule", [{"name": []}]),
        ("resource_types", "/resource_type", [{"name": [SECRET]}]),
    ],
)
async def test_gnocchi_malformed_diagnostics_remain_partial_not_fabricated_healthy(api, client, section, path, reply):
    api.cloud.overrides[("metric", "GET", path)] = reply
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["status"] == "partial"
    assert result[section] == {"status": "unavailable", "error": "telemetry_malformed_response", "data": None}


async def test_diagnostic_collection_bound_is_explicit_not_silently_truncated(api, client):
    api.cloud.overrides[("metric", "GET", "/resource_type")] = [{"name": f"type-{i}"} for i in range(257)]
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["resource_types"] == {"status": "partial", "error": "telemetry_section_budget", "data": None}


@pytest.mark.parametrize("kind", ["resources", "metrics"])
async def test_gnocchi_inventory_is_whitelisted_and_clamped_pages_end_only_at_explicit_empty(api, client, kind):
    api.cloud.page_size = 1
    if kind == "resources":
        api.cloud.resources = [
            {
                "id": value,
                "type": "instance",
                "project_id": PROJECT,
                "started_at": STAMP,
                "ended_at": None,
                "metrics": {"cpu": METRIC},
                "display_name": SECRET,
                "host": SECRET,
                "metadata": {"password": SECRET},
            }
            for value in (ALARM, OTHER)
        ]
        allowed = {"id", "type", "project_id", "started_at", "ended_at", "metrics"}
        extra = {"type": "instance"}
    else:
        api.cloud.metrics = [
            {
                "id": value,
                "name": "cpu",
                "unit": "ns",
                "resource_id": THIRD,
                "archive_policy_name": "medium",
                "created_by_project_id": PROJECT,
                "creator": SECRET,
                "metadata": {"password": SECRET},
                "archive_policy": {"name": "medium", "aggregation_methods": ["mean"], "secret": SECRET},
            }
            for value in (ALARM, OTHER)
        ]
        allowed = {
            "id",
            "name",
            "unit",
            "resource_id",
            "archive_policy_name",
            "created_by_project_id",
            "archive_policy",
        }
        extra = {}
    marker = None
    for expected in (ALARM, OTHER, None):
        params = {"limit": 100, **extra, **({"marker": marker} if marker else {})}
        result = safe(await client.get(PREFIX + "/gnocchi/" + kind, params=params))
        assert result["status"] == "available" and result["truncated"] is False
        assert result["next_marker"] == expected
        assert len(result["items"]) == (1 if expected else 0)
        if expected:
            row = result["items"][0]
            assert row["id"] == expected and set(row) == allowed
            if kind == "metrics":
                assert row["archive_policy"] == {"name": "medium", "aggregation_methods": ["mean"]}
        marker = expected
    assert len(api.cloud.calls) == 3
    assert [call["params"].get("marker") for call in api.cloud.calls] == [None, ALARM, OTHER]
    assert all(call["method"] == "GET" for call in api.cloud.calls)
    expected_path = "/resource/instance" if kind == "resources" else "/metric"
    assert all(call["path"] == expected_path for call in api.cloud.calls)


@pytest.mark.parametrize("samples", [[], [0], [123456789]])
async def test_gnocchi_measures_preserve_raw_zero_unit_native_grain_and_no_data(api, client, samples):
    def native(call):
        stop = datetime.fromisoformat(call["params"]["stop"])
        return [[(stop - timedelta(minutes=5)).isoformat(), 300, value] for value in samples]

    api.cloud.overrides[("metric", "GET", f"/metric/{METRIC}/measures")] = native
    result = safe(
        await client.get(
            PREFIX + f"/gnocchi/metrics/{METRIC}/measures",
            params={"hours": 24, "aggregation": "rate:mean", "granularity": 300, "refresh": "true"},
        )
    )
    assert result["status"] == "available" and result["error"] is None
    assert result["metric"]["unit"] == "ns"
    assert [row["value"] for row in result["measures"]] == samples
    assert all(row["granularity"] == 300 for row in result["measures"])
    assert result["truncated"] is False
    assert len(api.cloud.calls) == 2
    params = api.cloud.calls[-1]["params"]
    assert set(params) == {"start", "stop", "aggregation", "granularity"}
    assert datetime.fromisoformat(params["stop"]) - datetime.fromisoformat(params["start"]) == timedelta(hours=24)
    assert params["aggregation"] == "rate:mean" and params["granularity"] == 300


async def test_gnocchi_measure_window_filters_outside_points_without_inventing_data(api, client):
    def native(call):
        start = datetime.fromisoformat(call["params"]["start"])
        stop = datetime.fromisoformat(call["params"]["stop"])
        return [
            [(start - timedelta(seconds=1)).isoformat(), 60, 100],
            [start.isoformat(), 60, 0],
            [stop.isoformat(), 300, 7],
            [(stop + timedelta(seconds=1)).isoformat(), 60, 200],
        ]

    api.cloud.overrides[("metric", "GET", f"/metric/{METRIC}/measures")] = native
    result = safe(await client.get(PREFIX + f"/gnocchi/metrics/{METRIC}/measures"))
    assert [row["value"] for row in result["measures"]] == [0, 7]
    assert [row["granularity"] for row in result["measures"]] == [60, 300]


@pytest.mark.parametrize(
    "bad",
    [
        [STAMP, 300, math.nan],
        [STAMP, 300, math.inf],
        [STAMP, 300, -math.inf],
        [STAMP, 300, 10**400],
        [STAMP, 10**400, 1],
        [STAMP, 0, 1],
        [STAMP, -1, 1],
        [STAMP, True, 1],
        [STAMP, 300, True],
        [STAMP, 300, "123"],
        ["not-a-timestamp", 300, 1],
        [STAMP, 300],
        {"value": 1},
    ],
)
async def test_gnocchi_malformed_nonfinite_or_boolean_samples_are_partial_not_zero(api, client, bad):
    api.cloud.measures = [bad]
    result = safe(await client.get(PREFIX + f"/gnocchi/metrics/{METRIC}/measures"))
    assert result["status"] == "partial" and result["error"] == "telemetry_malformed_response"
    assert result["metric"]["id"] == METRIC and result["measures"] == []


async def test_gnocchi_samples_are_bounded_to_512_and_explicitly_truncated(api, client):
    def native(call):
        stop = datetime.fromisoformat(call["params"]["stop"])
        return [[(stop - timedelta(seconds=i)).isoformat(), 1, i] for i in range(600)]

    api.cloud.overrides[("metric", "GET", f"/metric/{METRIC}/measures")] = native
    result = safe(await client.get(PREFIX + f"/gnocchi/metrics/{METRIC}/measures"))
    assert result["status"] == "partial" and result["error"] == "telemetry_sample_budget"
    assert result["truncated"] is True and len(result["measures"]) == 512
    assert [row["value"] for row in result["measures"]] == list(range(512))


@pytest.mark.parametrize("native_status,expected", [(403, "forbidden"), (404, "not_found"), (500, "unavailable")])
async def test_metric_metadata_failure_stops_measure_fetch(api, client, native_status, expected):
    api.cloud.overrides[("metric", "GET", f"/metric/{METRIC}")] = StreamedResponse({"error": SECRET}, native_status)
    result = safe(await client.get(PREFIX + f"/gnocchi/metrics/{METRIC}/measures"))
    assert result["status"] == expected and result["metric"] is None and result["measures"] == []
    assert len(api.cloud.calls) == 1


async def test_measure_failure_keeps_metadata_and_is_not_native_healthy_zero(api, client):
    api.cloud.overrides[("metric", "GET", f"/metric/{METRIC}/measures")] = StreamedResponse({"error": SECRET}, 503)
    result = safe(await client.get(PREFIX + f"/gnocchi/metrics/{METRIC}/measures"))
    assert result["status"] == "partial" and result["error"] == "telemetry_native_unavailable"
    assert result["metric"]["unit"] == "ns" and result["measures"] == []


async def test_combined_response_byte_budget_is_shared_across_diagnostic_sections(api, client):
    padding = "x" * (900 * 1024)
    api.cloud.overrides.update(
        {
            ("metric", "GET", "/capabilities"): {"aggregation_methods": ["mean"], "ignored": padding},
            ("metric", "GET", "/status"): {"storage": {"summary": {"measures": 1, "metrics": 1}}, "ignored": padding},
            ("metric", "GET", "/archive_policy"): [{"name": "medium", "ignored": padding}],
            ("metric", "GET", "/archive_policy_rule"): [
                {"name": "all", "metric_pattern": "*", "archive_policy_name": "medium", "ignored": padding}
            ],
            ("metric", "GET", "/resource_type"): [{"name": "generic", "ignored": padding}],
        }
    )
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["status"] == "partial"
    assert result["resource_types"] == {"status": "unavailable", "error": "telemetry_response_budget", "data": None}
    assert all(result[key]["status"] == "available" for key in GNOCCHI_SECTIONS.keys() - {"resource_types"})
    assert len(api.cloud.calls) == 5 and all(response.close_count == 1 for response in api.cloud.responses)


async def test_request_budget_stops_remaining_sections_without_provider_calls(api, client, monkeypatch):
    # Reduce only the ceiling to exercise the public endpoint's existing shared
    # transport budget; do not substitute any collector/handler return value.
    monkeypatch.setattr(telemetry_admin, "MAX_CALLS", 2)
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["capabilities"]["status"] == result["processing"]["status"] == "available"
    for name in ("archive_policies", "archive_policy_rules", "resource_types"):
        assert result[name] == {"status": "unavailable", "error": "telemetry_request_budget", "data": None}
    assert len(api.cloud.calls) == 2


async def test_deadline_exhaustion_during_stream_closes_and_stops_later_native_calls(api, client, monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(telemetry_admin, "time", SimpleNamespace(monotonic=lambda: clock.now))

    def slow(_call):
        clock.now = 9.0
        return {"aggregation_methods": ["mean"]}

    api.cloud.overrides[("metric", "GET", "/capabilities")] = slow
    result = safe(await client.get(PREFIX + "/gnocchi"))
    assert result["status"] == "unavailable"
    assert all(result[key]["error"] == "telemetry_time_budget" for key in GNOCCHI_SECTIONS)
    assert len(api.cloud.calls) == 1 and api.cloud.responses[0].close_count == 1


async def test_discovery_uses_caller_catalog_region_interface_without_version_discovery(api, client):
    api.cloud.endpoints = {"alarming": "https://aodh.example/", "metric": "https://gnocchi.example/v1/"}
    aodh = safe(await client.get(PREFIX + "/aodh"))
    gnocchi = safe(await client.get(PREFIX + "/gnocchi"))
    assert aodh["status"] == gnocchi["status"] == "available"
    assert datetime.fromisoformat(aodh["checked_at"]).tzinfo == UTC
    assert api.cloud.discovery == [
        {"service_type": service, "interface": "internal", "region_name": "region-a", "skip_discovery": True}
        for service in ("alarming", "metric")
    ]
    assert len(api.cloud.calls) <= 12
    assert len(api.native_checks) == 2


@pytest.mark.parametrize(
    "endpoint",
    [
        f"https://{SECRET}@aodh.example/v2",
        f"https://aodh.example/v2?token={SECRET}",
        f"https://aodh.example/v2#{SECRET}",
        "file:///var/secrets",
        "https://aodh.example/v1",
    ],
)
async def test_malformed_catalog_endpoint_is_not_contacted_or_echoed(api, client, endpoint):
    api.cloud.endpoints["alarming"] = endpoint
    result = safe(await client.get(PREFIX + "/aodh"))
    assert result["status"] == "unavailable"
    assert api.cloud.calls == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/aodh"),
        ("GET", "/aodh/alarms"),
        ("GET", f"/aodh/alarms/{ALARM}"),
        ("POST", "/aodh/alarms"),
        ("PUT", f"/aodh/alarms/{ALARM}"),
        ("DELETE", f"/aodh/alarms/{ALARM}"),
        ("GET", "/gnocchi"),
        ("GET", "/gnocchi/resources"),
        ("GET", "/gnocchi/metrics"),
        ("GET", f"/gnocchi/metrics/{METRIC}/measures"),
    ],
)
async def test_every_endpoint_denies_non_admin_and_returns_no_store(api, client, method, path):
    api.token["is_system_admin"] = False
    response = await client.request(method, PREFIX + path, **({"json": body()} if method in {"POST", "PUT"} else {}))
    assert safe(response, 403)["detail"]["code"] == "system_admin_required"
    assert api.cloud.calls == [] and api.cloud.discovery == [] and api.native_checks == []


async def test_admin_grant_is_checked_fresh_not_reused_from_token_or_previous_read(api, client):
    safe(await client.get(PREFIX + "/aodh"))
    assert len(api.native_checks) == 1
    before = len(api.cloud.calls)
    api.directory.assignments.clear()
    response = await client.post(PREFIX + "/aodh/alarms", json=body())
    assert safe(response, 403)["detail"]["code"] == "system_admin_required"
    assert len(api.cloud.calls) == before and len(api.native_checks) == 2


async def test_fresh_admin_identity_failure_is_no_store_and_does_not_contact_telemetry(api, client):
    api.directory.users[api.token["user_id"]] = {"id": api.token["user_id"], "domain_id": "default", "enabled": False}
    response = await client.get(PREFIX + "/gnocchi")
    safe(response, 401)
    assert api.cloud.calls == [] and api.cloud.discovery == []


@pytest.mark.parametrize(
    "path,params",
    [
        ("/aodh", {"limit": 0}),
        ("/aodh", {"limit": 101}),
        ("/aodh/alarms", {"limit": "invalid"}),
        ("/aodh/alarms", {"state": SECRET}),
        ("/aodh/alarms", {"marker": SECRET}),
        (f"/aodh/alarms/{ALARM}", {"marker": SECRET}),
        (f"/aodh/alarms/{ALARM}", {"limit": 101}),
        (f"/aodh/alarms/{SECRET}", {}),
        ("/gnocchi/resources", {"type": "../" + SECRET}),
        ("/gnocchi/resources", {"limit": 0}),
        ("/gnocchi/resources", {"type": "a" * 129}),
        ("/gnocchi/resources", {"marker": SECRET}),
        ("/gnocchi/metrics", {"limit": 101}),
        ("/gnocchi/metrics", {"marker": SECRET}),
        (f"/gnocchi/metrics/{SECRET}/measures", {}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"hours": 0}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"hours": 169}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"hours": "1.5"}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"aggregation": SECRET + "&refresh=true"}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"granularity": 0}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"granularity": -1}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"granularity": "nan"}),
        (f"/gnocchi/metrics/{METRIC}/measures", {"granularity": "inf"}),
    ],
)
async def test_query_and_identifier_validation_errors_are_sanitized_no_store_without_native_io(
    api, client, path, params
):
    response = await client.get(PREFIX + path, params=params)
    assert response.status_code in (400, 422)
    result = safe(response, response.status_code)
    assert result == {"detail": {"code": "telemetry_invalid_input"}}
    assert api.cloud.calls == [] and api.cloud.discovery == []


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        {"name": SECRET},
        body(name=""),
        body(name=[SECRET]),
        body(enabled="true"),
        body(repeat_actions=1),
        body(severity=SECRET),
        body(description=[SECRET]),
        body(alarm_actions=SECRET),
        body(time_constraints=[SECRET]),
        body(gnocchi_resources_threshold_rule=[]),
        body(trust_id=SECRET),
        body(user_id=SECRET),
        body(rule={"password": SECRET}),
        body(actions=[SECRET]),
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_invalid_alarm_definition_is_safe_rejected_input_not_provider_io(api, client, payload, method):
    path = "/aodh/alarms" + (f"/{ALARM}" if method == "PUT" else "")
    # Encode null explicitly: httpx json=None means no request body.
    response = await client.request(
        method, PREFIX + path, content=json.dumps(payload), headers={"Content-Type": "application/json"}
    )
    assert response.status_code in (400, 422)
    assert safe(response, response.status_code) == {"detail": {"code": "telemetry_invalid_alarm"}}
    assert api.cloud.calls == [] and api.cloud.discovery == []


@pytest.mark.parametrize("raw", [b'{"name":"' + SECRET.encode(), b"\xff" + SECRET.encode(), b" " * (256 * 1024 + 1)])
async def test_invalid_json_utf8_and_oversized_mutation_body_are_safe_no_store(api, client, raw):
    response = await client.post(PREFIX + "/aodh/alarms", content=raw, headers={"Content-Type": "application/json"})
    assert safe(response, 400) == {"detail": {"code": "telemetry_invalid_alarm"}}
    assert api.cloud.calls == []


async def test_aodh_alarm_denial_does_not_hide_readable_history(api, client):
    api.cloud.overrides[("alarming", "GET", f"/alarms/{ALARM}")] = StreamedResponse({"error": SECRET}, 403)
    api.cloud.history = [{"event_id": OTHER, "type": "state transition", "timestamp": STAMP}]
    result = safe(await client.get(PREFIX + f"/aodh/alarms/{ALARM}"))
    assert result["status"] == "partial" and result["alarm"] is None
    assert result["history"]["status"] == "available"
    assert result["history"]["items"] == api.cloud.history


async def test_history_pagination_preserves_provider_clamped_marker_until_explicit_empty(api, client):
    api.cloud.page_size = 1
    api.cloud.history = [
        {"event_id": event_id, "type": "state transition", "timestamp": STAMP, "detail": SECRET}
        for event_id in (OTHER, THIRD)
    ]
    marker = None
    for expected in (OTHER, THIRD, None):
        result = safe(
            await client.get(
                PREFIX + f"/aodh/alarms/{ALARM}", params={"limit": 25, **({"marker": marker} if marker else {})}
            )
        )
        assert result["alarm"]["alarm_id"] == ALARM
        history = result["history"]
        assert history["status"] == "available" and history["next_marker"] == expected
        assert len(history["items"]) == (1 if expected else 0)
        assert history["truncated"] is False
        marker = expected
    calls = [call for call in api.cloud.calls if call["path"].endswith("/history")]
    assert [call["params"].get("marker") for call in calls] == [None, OTHER, THIRD]


async def test_successive_calls_do_not_cache_native_alarm_or_measure_snapshots(api, client):
    initial = safe(await client.get(PREFIX + "/aodh/alarms"))
    assert initial["items"][0]["state"] == "ok"
    api.cloud.alarms[0]["state"] = "alarm"
    updated = safe(await client.get(PREFIX + "/aodh/alarms"))
    assert updated["items"][0]["state"] == "alarm"
    assert len(api.cloud.calls) == 2 and len(api.native_checks) == 2
