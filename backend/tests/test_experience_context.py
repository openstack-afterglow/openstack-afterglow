"""Semantic context is diagnostic-only and never resolves another principal."""

import asyncio
import sys
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.middleware.experience import ExperienceMiddleware
from app.services import experience_context as ec


def request_scope(**updates):
    headers = [
        (b"x-afterglow-experience-segment", str(uuid4()).encode()),
        (b"x-afterglow-experience-page-view", str(uuid4()).encode()),
        (b"x-afterglow-experience-action", str(uuid4()).encode()),
        (b"x-afterglow-page", b"/compute/instances"),
    ]
    return {
        "type": "http",
        "path": "/api/v1/compute/instances",
        "method": "POST",
        "headers": headers,
        "state": {},
        **updates,
    }


@pytest.fixture
def diagnostics(monkeypatch):
    monkeypatch.setattr(ec, "get_settings", lambda: SimpleNamespace(experience_enabled=True))
    store = SimpleNamespace(
        record_server_event=AsyncMock(), bind_operation=AsyncMock(), read_operation_context=AsyncMock(return_value=None)
    )
    monkeypatch.setitem(sys.modules, "app.services.experience", store)
    return store


def test_canonical_headers_do_not_capture_input_or_identity(diagnostics):
    scope = request_scope()
    scope["headers"].extend([(b"authorization", b"Bearer secret"), (b"x-user-id", b"forged")])
    context = ec.capture_request_context(
        Request(scope),
        "req-" + "a" * 32,
        {"user_id": "owner", "project_id": "project", "token": "secret", "username": "private"},
    )
    assert context["actor"] == {"user_id": "owner", "project_id": "project"}
    assert "secret" not in repr(context)
    assert "forged" not in repr(context)
    assert ec.capture_request_context(Request(request_scope(headers=[])), "req-" + "a" * 32, {}) is None
    scope["headers"][-3] = (b"x-afterglow-page", b"/compute/instances?name=private")
    assert ec.capture_request_context(Request(scope), "req-" + "a" * 32, {}) is None


@pytest.mark.asyncio
async def test_explicit_context_survives_await_without_last_click(diagnostics):
    async def action(identity):
        value = asdict(
            ec.SafeExperienceContext(
                segment_id=str(uuid4()),
                page_view_id=str(uuid4()),
                route="/",
                action_id=identity,
                actor={"user_id": "owner", "project_id": "project"},
            )
        )
        with ec.experience_scope(value):
            await asyncio.sleep(0)
            captured = ec.capture_experience_context()
            captured["actor"]["user_id"] = "changed-copy"
            assert ec.capture_experience_context()["actor"]["user_id"] == "owner"
            return ec.capture_experience_context()["action_id"]

    first, second = str(uuid4()), str(uuid4())
    assert await asyncio.gather(action(first), action(second)) == [first, second]
    assert ec.capture_experience_context() is None


@pytest.mark.asyncio
async def test_restore_requires_actual_owner_or_explicit_mail_origin_receipt(diagnostics):
    assert await ec.restore_experience_operation("library_build", "12", {"user_id": "owner"}) is None
    diagnostics.read_operation_context.assert_not_awaited()
    restored = {"actor": {"user_id": "owner", "project_id": "origin"}, "source": "api"}
    diagnostics.read_operation_context.return_value = restored
    assert await ec.restore_experience_operation(
        "email_operation", "actual-id", {"user_id": "owner", "ownership_mode": "origin_receipt"}
    ) == {**restored, "source": "worker"}
    diagnostics.read_operation_context.assert_awaited_once_with(
        "email_operation", "actual-id", {"user_id": "owner", "ownership_mode": "origin_receipt"}
    )


@pytest.mark.asyncio
async def test_diagnostic_timeout_is_bounded_and_never_retried(diagnostics, monkeypatch):
    monkeypatch.setattr(ec, "_TIMEOUT", 0.001)

    async def stalled(**kwargs):
        await asyncio.Event().wait()

    diagnostics.record_server_event.side_effect = stalled
    await ec.emit_experience(
        {"actor": {}}, "stage.completed", stage="native", status="outcome_unknown", reason="unknown"
    )
    diagnostics.record_server_event.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("complete", [False, True])
async def test_stream_finalization_uses_only_existing_verified_actor(diagnostics, complete):
    sent = []
    actual_id = "req-" + "b" * 32

    async def app(scope, receive, send):
        diagnostics.record_server_event.assert_not_awaited()
        scope["state"]["token_info"] = {"user_id": "owner", "project_id": "project", "token": "never-retained"}
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-request-id", actual_id.encode())]})
        await send({"type": "http.response.body", "body": b"private stream content", "more_body": not complete})

    async def send(message):
        sent.append(message)

    await ExperienceMiddleware(app)(request_scope(), AsyncMock(), send)
    call = diagnostics.record_server_event.await_args_list[-1].kwargs
    assert call["event_type"] == "request.completed"
    assert call["context"]["actor"] == {"user_id": "owner", "project_id": "project"}
    assert call["context"]["request_id"] == actual_id
    assert call["status"] == ("observed" if complete else "outcome_unknown")
    assert call["http_status"] == 200
    assert call["reason"] == ("transport_complete" if complete else "transport_incomplete")
    assert "private stream content" not in repr(diagnostics.record_server_event.await_args_list)
    assert [value for key, value in sent[0]["headers"] if key == b"x-request-id"] == [actual_id.encode()]
    started = diagnostics.record_server_event.await_args_list[0].kwargs
    assert started["event_type"] == "request.started"
    assert started["context"]["actor"] == call["context"]["actor"]
    assert started["occurred_at"].tzinfo is not None
    assert started["occurred_at"] <= call["occurred_at"]
    assert (call["context"]["feature"], call["context"]["action"], call["context"]["component"]) == (
        "unknown",
        "unknown",
        "unknown",
    )


@pytest.mark.asyncio
async def test_default_off_and_missing_headers_never_write(diagnostics, monkeypatch):
    monkeypatch.setattr(ec, "get_settings", lambda: SimpleNamespace(experience_enabled=False))
    await ec.emit_experience({"actor": {}}, "stage.started", stage="worker", status="running")
    await ec.bind_experience_operation({"actor": {}}, "library_build", "1")
    assert ec.unlinked_worker_context() is None
    diagnostics.record_server_event.assert_not_awaited()
    diagnostics.bind_operation.assert_not_awaited()


def test_periodic_worker_is_explicitly_unlinked(diagnostics):
    context = ec.unlinked_worker_context()
    assert context["source"] == "worker"
    assert context["actor"] == {}
    assert context["action_id"] is None
    assert context["caused_by_event_id"] is None
    assert context["trace_id"] is None


@pytest.mark.asyncio
async def test_request_cancellation_is_not_native_terminal_or_extra_auth(diagnostics, monkeypatch):
    from app.api import deps

    principal = AsyncMock(side_effect=AssertionError("Diagnostics cannot resolve a principal"))
    monkeypatch.setattr(deps, "get_token_info", principal)

    async def app(scope, receive, send):
        scope["state"]["token_info"] = {"user_id": "owner", "project_id": "project"}
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await ExperienceMiddleware(app)(request_scope(), AsyncMock(), AsyncMock())
    principal.assert_not_awaited()
    final = diagnostics.record_server_event.await_args_list[-1].kwargs
    assert final["event_type"] == "request.completed"
    assert final["status"] == "outcome_unknown"
    assert final["reason"] == "transport_incomplete"


@pytest.mark.asyncio
async def test_native_volume_readback_observes_real_state_without_new_requests(diagnostics, monkeypatch):
    from app.api.storage import volumes

    identity = str(uuid4())
    conn = SimpleNamespace(_afterglow_project_id="project")
    owner_check = AsyncMock(return_value=SimpleNamespace(project_id="project"))
    monkeypatch.setattr(volumes, "_assert_volume_owner", owner_check)
    read = AsyncMock(return_value=SimpleNamespace(id=identity, status="available"))
    monkeypatch.setattr(volumes.asyncio, "to_thread", read)
    context = asdict(
        ec.SafeExperienceContext(
            segment_id=str(uuid4()),
            page_view_id=str(uuid4()),
            route="/compute/volumes",
            actor={"user_id": "owner", "project_id": "project"},
        )
    )
    with ec.experience_scope(context):
        result = await volumes.get_volume(identity, conn, {"user_id": "owner", "project_id": "project"})
    assert result.id == identity
    owner_check.assert_awaited_once()
    read.assert_awaited_once_with(volumes.cinder.get_volume, conn, identity)
    event = diagnostics.record_server_event.await_args.kwargs
    assert event["stage"] == "readback"
    assert event["status"] == "succeeded"
    assert event["resource_ref"] == identity


@pytest.mark.asyncio
@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize("cancel_claim", [False, True])
async def test_mail_unknown_is_not_retried_or_attributed_to_recipient(diagnostics, monkeypatch, linked, cancel_claim):
    from app.services import email_service, mail_delivery

    identity = str(uuid4())
    operation = SimpleNamespace(id="a" * 32, actor_id="actual-sender", kind="individual")
    row = SimpleNamespace(
        id=identity,
        status="pending",
        operation_key=operation.id,
        kind="individual",
        recipient_email="synthetic@example.invalid",
        message_id="<synthetic@example.invalid>",
    )
    origin = asdict(
        ec.SafeExperienceContext(
            segment_id=str(uuid4()),
            page_view_id=str(uuid4()),
            route="/admin/users",
            actor={"user_id": "actual-sender", "project_id": "origin-project"},
        )
    )
    diagnostics.read_operation_context.return_value = origin if linked else None

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, model, key):
            return row if key == identity else operation

    monkeypatch.setattr(mail_delivery, "_factory", lambda: Session)
    smtp = SimpleNamespace(enabled=True, from_name="Synthetic", from_address="sender@example.invalid")
    monkeypatch.setattr(
        mail_delivery.mail_settings, "effective_settings", AsyncMock(return_value=SimpleNamespace(smtp=smtp))
    )
    monkeypatch.setattr(mail_delivery, "_payload", lambda _: {"subject": "Synthetic", "body": "Synthetic"})
    monkeypatch.setattr(mail_delivery, "_eligible_delivery", AsyncMock(return_value=None))
    monkeypatch.setattr(mail_delivery, "checkpoint", AsyncMock())
    settle = AsyncMock(return_value=True)
    monkeypatch.setattr(mail_delivery, "_set_status", settle)
    send = AsyncMock(return_value=SimpleNamespace(status="unknown", code="synthetic_unknown"))
    monkeypatch.setattr(email_service, "send_message", send)

    if cancel_claim:
        claim_entered = asyncio.Event()
        cancel_notice = asyncio.Event()
        release_send = asyncio.Event()

        async def delayed_send(*args, **kwargs):
            await release_send.wait()
            return SimpleNamespace(status="unknown", code="synthetic_unknown")

        send.side_effect = delayed_send

        async def record(**fields):
            if fields["event_type"] == "worker.claimed":
                claim_entered.set()
                await asyncio.Event().wait()
            if fields["status"] == "cancel_requested":
                cancel_notice.set()
                await asyncio.sleep(0.02)

        diagnostics.record_server_event.side_effect = record
        task = asyncio.create_task(mail_delivery._dispatch_one(identity))
        await claim_entered.wait()
        task.cancel()
        await asyncio.wait_for(cancel_notice.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert [call.args[1] for call in settle.await_args_list] == ["dispatching"]
        release_send.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert any(
            call.kwargs["stage"] == "native.drain" and call.kwargs["status"] == "observed"
            for call in diagnostics.record_server_event.await_args_list
        )
    else:
        await mail_delivery._dispatch_one(identity)

    send.assert_awaited_once()
    assert [call.args[1] for call in settle.await_args_list] == ["dispatching", "unknown"]
    final = [
        call.kwargs
        for call in diagnostics.record_server_event.await_args_list
        if call.kwargs["stage"] == "mail.dispatch"
    ][-1]
    assert final["status"] == "outcome_unknown"
    assert final["stage"] == "mail.dispatch"
    assert final["context"]["source"] == "worker"
    assert final["context"]["actor"] == (origin["actor"] if linked else {})
    diagnostics.read_operation_context.assert_awaited_once_with(
        "email_operation", operation.id, {"user_id": "actual-sender", "ownership_mode": "origin_receipt"}
    )
    if linked:
        assert diagnostics.bind_operation.await_args.args[0]["actor"]["project_id"] == "origin-project"
    else:
        diagnostics.bind_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_mail_accepted_is_durable_before_completion_diagnostic_can_cancel(diagnostics, monkeypatch):
    """SMTP accepted 뒤 best-effort 완료 진단이 취소돼도 accepted를 unknown으로 강등하지 않는다."""
    from app.services import email_service, mail_delivery

    identity = str(uuid4())
    operation = SimpleNamespace(id="a" * 32, actor_id="actual-sender", kind="individual")
    row = SimpleNamespace(
        id=identity,
        status="pending",
        operation_key=operation.id,
        kind="individual",
        recipient_email="synthetic@example.invalid",
        message_id="<synthetic@example.invalid>",
    )
    diagnostics.read_operation_context.return_value = None

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, model, key):
            return row if key == identity else operation

    monkeypatch.setattr(mail_delivery, "_factory", lambda: Session)
    smtp = SimpleNamespace(enabled=True, from_name="Synthetic", from_address="sender@example.invalid")
    monkeypatch.setattr(
        mail_delivery.mail_settings, "effective_settings", AsyncMock(return_value=SimpleNamespace(smtp=smtp))
    )
    monkeypatch.setattr(mail_delivery, "_payload", lambda _: {"subject": "Synthetic", "body": "Synthetic"})
    monkeypatch.setattr(mail_delivery, "_eligible_delivery", AsyncMock(return_value=None))
    monkeypatch.setattr(mail_delivery, "checkpoint", AsyncMock())
    settle = AsyncMock(return_value=True)
    monkeypatch.setattr(mail_delivery, "_set_status", settle)
    send = AsyncMock(return_value=SimpleNamespace(status="accepted", code=None))
    monkeypatch.setattr(email_service, "send_message", send)

    async def record(**fields):
        if fields["event_type"] == "stage.completed":
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

    diagnostics.record_server_event.side_effect = record

    with pytest.raises(asyncio.CancelledError):
        await mail_delivery._dispatch_one(identity)

    send.assert_awaited_once()
    assert [call.args[1] for call in settle.await_args_list] == ["dispatching", "accepted"]


def test_existing_audit_actor_is_used_without_inheriting_it_into_workers(diagnostics):
    from app.services.activity import _audit_ctx

    scope = request_scope(
        state={
            "experience_audit_context": {
                "actor": {"user_id": "verified-login", "project_id": "project", "username": "private"},
                "request_id": "req-" + "c" * 32,
            }
        }
    )
    request = Request(scope)
    context = ec.capture_request_context(request, "req-" + "a" * 32, None)
    with ec.experience_scope(context, request=request):
        captured = ec.capture_experience_context()
        assert captured["actor"] == {"user_id": "verified-login", "project_id": "project"}
        assert captured["request_id"] == "req-" + "c" * 32
    token = _audit_ctx.set({"actor": {"user_id": "different-request"}, "request_id": "req-" + "d" * 32})
    try:
        with ec.experience_scope({**context, "source": "worker", "request_id": "req-" + "e" * 32}):
            assert ec.capture_experience_context()["request_id"] == "req-" + "e" * 32
            assert ec.capture_experience_context()["actor"] == {}
    finally:
        _audit_ctx.reset(token)


@pytest.mark.asyncio
async def test_diagnostic_child_cancellation_does_not_cancel_business(diagnostics):
    diagnostics.record_server_event.side_effect = asyncio.CancelledError
    await ec.emit_experience({"actor": {}}, "stage.completed", stage="native", status="outcome_unknown")
    diagnostics.record_server_event.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_mcp_transport_diagnostics_do_not_synthesize_business_token_info(diagnostics, monkeypatch, enabled):
    from contextlib import asynccontextmanager

    from app.services.mcp_control_plane import transport
    from app.services.mcp_control_plane.authentication import McpPrincipal

    monkeypatch.setattr(ec, "get_settings", lambda: SimpleNamespace(experience_enabled=enabled))
    monkeypatch.setattr(
        transport, "get_settings", lambda: SimpleNamespace(service_mcp_enabled=True, mcp_request_max_bytes=32768)
    )
    monkeypatch.setattr(transport, "mcp_paths", lambda: frozenset({"/api/v1/mcp"}))
    monkeypatch.setattr(transport, "_canonical_origin", lambda: ("https://synthetic.invalid", "synthetic.invalid"))
    monkeypatch.setattr(transport, "_urls", lambda: SimpleNamespace(resource="https://synthetic.invalid/api/v1/mcp"))
    monkeypatch.setattr(transport, "_initialization_observation", lambda *_: None)
    principal = McpPrincipal(
        grant_id="grant",
        user_id="verified-owner",
        project_id="selected-project",
        owner_project_id="anchor-project",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )
    monkeypatch.setattr(transport, "verify_mcp_bearer", AsyncMock(return_value=principal))
    manager = SimpleNamespace(handle_request=AsyncMock())
    monkeypatch.setattr(transport, "_manager", manager)

    @asynccontextmanager
    async def slot(*args, **kwargs):
        yield

    monkeypatch.setattr(transport, "grant_call_slot", slot)
    scope = request_scope(
        path="/api/v1/mcp",
        headers=[
            (b"host", b"synthetic.invalid"),
            (b"authorization", b"Bearer synthetic"),
            (b"content-type", b"application/json"),
            (b"accept", b"application/json, text/event-stream"),
        ],
    )
    await transport.mcp_asgi_app(
        scope, AsyncMock(return_value={"type": "http.request", "body": b"{}", "more_body": False}), AsyncMock()
    )
    manager.handle_request.assert_awaited_once()
    assert "token_info" not in scope["state"]
    if enabled:
        assert scope["state"]["experience_actor"] == {"user_id": "verified-owner", "project_id": "anchor-project"}
    else:
        assert "experience_actor" not in scope["state"]


@pytest.mark.asyncio
async def test_mcp_committed_admission_uses_ledger_anchor_owner(diagnostics, monkeypatch):
    from app.services.mcp_control_plane import ledger
    from app.services.mcp_control_plane.authentication import McpPrincipal

    claim = ledger.MutationClaim(state="claimed", invocation_id=str(uuid4()))
    monkeypatch.setattr(ledger, "_claim_mutation", AsyncMock(return_value=claim))
    principal = McpPrincipal(
        grant_id="grant",
        user_id="verified-owner",
        project_id="selected-project",
        owner_project_id="anchor-project",
        credential_epoch=1,
        scopes=frozenset({"mcp:write"}),
        source="personal_token",
    )
    context = asdict(ec.SafeExperienceContext(segment_id=str(uuid4()), page_view_id=str(uuid4()), route="/", actor={}))
    with ec.experience_scope(context):
        result = await ledger.claim_mutation(principal, entry=None, arguments={}, idempotency_key="synthetic-key")
    assert result == claim
    bound = diagnostics.bind_operation.await_args.args[0]
    assert bound["actor"] == {"user_id": "verified-owner", "project_id": "anchor-project"}
    assert (bound["feature"], bound["action"], bound["component"]) == ("mcp", "submit", "page")


@pytest.mark.asyncio
async def test_failed_protected_request_preserves_anonymous_route_without_extra_auth(diagnostics):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    await ExperienceMiddleware(app)(request_scope(), AsyncMock(), AsyncMock())
    event = diagnostics.record_server_event.await_args.kwargs
    assert event["context"]["actor"] == {}
    assert event["context"]["route"] == "/compute/instances"
    assert event["http_status"] == 401
    assert event["status"] == "failed"
    assert event["reason"] == "transport_complete"


@pytest.mark.asyncio
async def test_level_cancelled_stream_finalization_is_shielded(diagnostics):
    import anyio

    async def record(**fields):
        await anyio.sleep(0)

    diagnostics.record_server_event.side_effect = record
    with anyio.CancelScope() as cancelled:

        async def app(scope, receive, send):
            scope["state"]["token_info"] = {"user_id": "owner", "project_id": "project"}
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": True})
            cancelled.cancel()
            await anyio.sleep_forever()

        await ExperienceMiddleware(app)(request_scope(), AsyncMock(), AsyncMock())
    assert [call.kwargs["event_type"] for call in diagnostics.record_server_event.await_args_list] == [
        "request.started",
        "request.completed",
    ]
    assert diagnostics.record_server_event.await_args.kwargs["status"] == "outcome_unknown"
