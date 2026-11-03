"""Isolated SQL/HTTP mail settings, transport and read-only receipt contracts."""

import asyncio
import copy
import json
import socket
import threading
import time
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import aiosmtplib
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_token_info, require_admin
from app.api.identity import admin_mail_settings as api
from app.api.identity import domain_auth as domain_auth_api
from app.api.identity import enrollment_policy as enrollment_api
from app.models.db import RuntimeSetting
from app.models.domain_auth import DomainIdentityProvider, DomainLoginPolicy
from app.models.enrollment_policy import EnrollmentPolicy
from app.services import (
    account_recovery,
    admin_password_reset,
    domain_auth,
    domain_iam,
    email_service,
    enrollment_policy,
    k3s_crypto,
    mail_crypto,
    mail_settings,
    resource_policy_store,
)


@pytest_asyncio.fixture
async def mail_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mail.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(RuntimeSetting.__table__.create)
        await connection.run_sync(EnrollmentPolicy.__table__.create)
        await connection.run_sync(DomainLoginPolicy.__table__.create)
        await connection.run_sync(DomainIdentityProvider.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    base = SimpleNamespace(
        database_url="sqlite+aiosqlite://isolated",
        smtp_enabled=True,
        smtp_host="file.smtp.test",
        smtp_port=587,
        smtp_username="file-user",
        smtp_password="dummy-file-secret",
        smtp_from_address="sender@example.test",
        smtp_from_name="File sender",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        smtp_security="",
        smtp_timeout_seconds=3,
        frontend_base_url="https://console.example.test",
        service_manila_enabled=False,
        auth=SimpleNamespace(public_signup_enabled=True, public_signup_button_visible=True),
    )
    monkeypatch.setattr(mail_settings, "get_session_factory", lambda: factory)
    monkeypatch.setattr(mail_settings, "is_db_available", lambda: True)
    monkeypatch.setattr(mail_settings, "is_db_configured", lambda: True)
    monkeypatch.setattr(mail_settings, "get_settings", lambda: base)
    monkeypatch.setattr(k3s_crypto, "_get_key", lambda: bytes(range(32)))
    for service in (account_recovery, admin_password_reset, domain_auth, domain_iam, enrollment_policy):
        monkeypatch.setattr(service, "get_settings", lambda: base)
    monkeypatch.setattr("app.config.get_settings", lambda: base)
    monkeypatch.setattr(enrollment_policy, "get_session_factory", lambda: factory)
    state = SimpleNamespace(factory=factory, base=base, admin=True)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/admin")
    app.include_router(enrollment_api.router, prefix="/api/v1/admin")

    async def admin():
        if not state.admin:
            raise HTTPException(403, "admin_required")

    app.dependency_overrides[require_admin] = admin
    app.dependency_overrides[get_token_info] = lambda: {"user_id": "administrator"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        state.client = client
        yield state
    await engine.dispose()


def draft(settings):
    result = mail_settings.public_settings(settings)
    result.pop("source")
    return result


async def saved_draft():
    return draft(await mail_settings.effective_settings())


@pytest.mark.asyncio
async def test_endpoint_save_secret_keep_cas_and_reset_tombstone(mail_db):
    client = mail_db.client
    response = await client.get("/api/v1/admin/email/settings")
    assert response.status_code == 200
    assert response.json()["source"] == "config" and response.json()["revision"] == 0
    assert response.json()["smtp"]["password_configured"] is True
    assert "dummy-file-secret" not in response.text
    assert "no-store" in response.headers["cache-control"]
    body = await saved_draft()
    body["smtp"]["password"] = "dummy-web-secret"
    body["smtp"]["host"] = "web.smtp.test"
    response = await client.put("/api/v1/admin/email/settings", json=body)
    assert response.status_code == 200 and response.json()["revision"] == 1
    assert response.json()["source"] == "runtime"
    assert "dummy-web-secret" not in response.text
    async with mail_db.factory() as session:
        record = (await session.get(RuntimeSetting, mail_settings.KEY)).value_json
    assert "dummy-web-secret" not in json.dumps(record)
    assert record["override"]["smtp"]["password_ciphertext"].startswith("v3:")
    assert (await client.put("/api/v1/admin/email/settings", json=body)).status_code == 409
    body = await saved_draft()
    body["smtp"]["from_name"] = "New display name"
    assert (await client.put("/api/v1/admin/email/settings", json=body)).status_code == 200
    assert (await mail_settings.effective_settings()).smtp.password == "dummy-web-secret"
    assert (await client.delete("/api/v1/admin/email/settings?revision=1")).status_code == 409
    response = await client.delete("/api/v1/admin/email/settings?revision=2")
    assert response.status_code == 200
    assert response.json()["revision"] == 3 and response.json()["source"] == "config"
    assert (await mail_settings.effective_settings()).smtp.password == "dummy-file-secret"
    assert (await client.put("/api/v1/admin/email/settings", json=body)).status_code == 409
    response = await client.put("/api/v1/admin/email/settings", json=await saved_draft())
    assert response.status_code == 200 and response.json()["revision"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value", [("host", "changed.smtp.test"), ("port", 465), ("username", "another-user"), ("security", "tls")]
)
async def test_destination_changes_require_explicit_secret_consent(mail_db, field, value):
    body = await saved_draft()
    body["smtp"][field] = value
    response = await mail_db.client.put("/api/v1/admin/email/settings", json=body)
    assert response.status_code == 422 and response.json()["detail"] == "mail_secret_reconfirmation_required"
    body["smtp"]["reconfirm_password"] = True
    assert (await mail_db.client.put("/api/v1/admin/email/settings", json=body)).status_code == 200
    assert (await mail_settings.effective_settings()).smtp.password == "dummy-file-secret"


@pytest.mark.asyncio
async def test_clear_and_secret_replacement_are_explicit(mail_db):
    body = await saved_draft()
    body["smtp"].update(host="changed.smtp.test", clear_password=True)
    response = await mail_db.client.put("/api/v1/admin/email/settings", json=body)
    assert response.status_code == 200 and response.json()["smtp"]["password_configured"] is False
    assert (await mail_settings.effective_settings()).smtp.password == ""
    body = await saved_draft()
    body["imap"].update(enabled=True, host="imap.example.test", username="inbox-user", password="dummy-imap-secret")
    assert (await mail_db.client.put("/api/v1/admin/email/settings", json=body)).status_code == 200
    assert (await mail_settings.effective_settings()).imap.password == "dummy-imap-secret"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "user:dummy-secret@host"),
        ("port", 0),
        ("port", True),
        ("timeout_seconds", 31),
        ("security", "none"),
        ("security", []),
        ("from_address", "A <sender@example.test>"),
        ("password", {"dummy-secret": True}),
        ("password", "********"),
    ],
)
async def test_validation_cannot_echo_password_input(mail_db, field, value):
    body = await saved_draft()
    body["smtp"].update(password="dummy-secret", reconfirm_password=True)
    body["smtp"][field] = value
    response = await mail_db.client.put("/api/v1/admin/email/settings", json=body)
    assert response.status_code == 422
    assert "dummy-secret" not in response.text and "input" not in response.text
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_every_endpoint_requires_fresh_admin(mail_db):
    mail_db.admin = False
    for method, path, body in [
        ("GET", "/settings", None),
        ("PUT", "/settings", {}),
        ("DELETE", "/settings?revision=0", None),
        ("POST", "/connection-check", {}),
        ("POST", "/receipt-check", {"delivery_id": str(uuid4())}),
    ]:
        response = await mail_db.client.request(method, "/api/v1/admin/email" + path, json=body)
        assert response.status_code == 403
        assert "no-store" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_configured_storage_failure_never_bypasses_override(mail_db, monkeypatch):
    await mail_settings.save_settings(await saved_draft())
    monkeypatch.setattr(mail_settings, "is_db_available", lambda: False)
    with pytest.raises(HTTPException) as error:
        await mail_settings.effective_settings()
    assert error.value.status_code == 503
    monkeypatch.setattr(mail_settings, "is_db_configured", lambda: False)
    monkeypatch.setattr(mail_settings, "get_session_factory", lambda: None)
    mail_db.base.database_url = ""
    settings = await mail_settings.effective_settings()
    assert settings.source == "config" and settings.smtp.host == "file.smtp.test"
    with pytest.raises(HTTPException):
        await mail_settings.save_settings(draft(settings))


@pytest.mark.asyncio
async def test_tampered_ciphertext_fails_closed_and_generic_settings_remain_private(mail_db, monkeypatch):
    await mail_settings.save_settings(await saved_draft())
    monkeypatch.setattr(resource_policy_store, "_require_db", lambda: mail_db.factory)
    public = await resource_policy_store.list_runtime_settings()
    assert mail_settings.KEY not in json.dumps(public) and "v3:" not in json.dumps(public)
    with pytest.raises(resource_policy_store.RuntimeSettingValidationError):
        await resource_policy_store.get_runtime_setting(mail_settings.KEY)
    async with mail_db.factory() as session, session.begin():
        row = await session.get(RuntimeSetting, mail_settings.KEY)
        record = copy.deepcopy(row.value_json)
        record["override"]["smtp"]["password_ciphertext"] = "v3:broken"
        row.value_json = record
    response = await mail_db.client.get("/api/v1/admin/email/settings")
    assert response.status_code == 503 and "broken" not in response.text
    response = await mail_db.client.delete("/api/v1/admin/email/settings?revision=1")
    assert response.status_code == 200 and response.json()["revision"] == 2
    assert response.json()["source"] == "config"


@pytest.mark.asyncio
async def test_crypto_is_v3_only_bound_and_repr_hidden(mail_db):
    ciphertext = mail_crypto.encrypt_secret("dummy-secret", purpose="smtp")
    assert mail_crypto.decrypt_secret(ciphertext, purpose="smtp") == "dummy-secret"
    assert "dummy-secret" not in repr(mail_settings.SMTPSettings(password="dummy-secret"))
    for value, purpose in [
        (ciphertext, "imap"),
        (ciphertext[3:], "smtp"),
        ("v2:" + ciphertext[3:], "smtp"),
        (ciphertext[:-2], "smtp"),
    ]:
        with pytest.raises(ValueError, match="mail_secret_unavailable"):
            mail_crypto.decrypt_secret(value, purpose=purpose)
    delivery_id = str(uuid4())
    sealed = mail_crypto.encrypt_secret("private body", purpose="delivery:" + delivery_id)
    with pytest.raises(ValueError):
        mail_crypto.decrypt_secret(sealed, purpose="delivery:" + str(uuid4()))


@pytest.mark.asyncio
async def test_all_readiness_consumers_observe_saved_disable_enable(mail_db):
    assert await account_recovery.recovery_enabled() is True
    assert await domain_auth.smtp_configured() is True
    assert (await enrollment_policy.read_policy()).get("smtp_configured") is None
    assert (await domain_iam.signup_options())["signup_enabled"] is True
    body = await saved_draft()
    body["smtp"]["enabled"] = False
    await mail_settings.save_settings(body)
    assert await account_recovery.recovery_enabled() is False
    assert await domain_auth.smtp_configured() is False
    assert (await enrollment_policy.read_policy()).get("smtp_configured") is None
    assert (await domain_iam.signup_options())["signup_enabled"] is False
    with pytest.raises(HTTPException) as error:
        await admin_password_reset._smtp_ready()
    assert error.value.status_code == 503
    body = await saved_draft()
    body["smtp"]["enabled"] = True
    await mail_settings.save_settings(body)
    assert await account_recovery.recovery_enabled() is True


@pytest.mark.asyncio
async def test_saved_transport_drives_legacy_mail_and_admin_password_preflight(mail_db, monkeypatch):
    options, sent = [], []

    class SMTP:
        def __init__(self, **kwargs):
            options.append(kwargs)

        async def connect(self):
            pass

        async def send_message(self, message, **kwargs):
            sent.append((message, kwargs))
            return {}, "accepted"

        def close(self):
            pass

    monkeypatch.setattr(aiosmtplib, "SMTP", SMTP)
    body = await saved_draft()
    body["smtp"].update(
        host="web.smtp.test", port=465, security="tls", password="dummy-runtime-secret", from_address="web@example.test"
    )
    await mail_settings.save_settings(body)
    assert await email_service.send_email("recipient@example.test", "Subject", "<p>Body</p>", "Body") is True
    client = await admin_password_reset._smtp_ready()
    assert (
        await admin_password_reset._deliver(
            client, SimpleNamespace(name="target"), "recipient@example.test", "dummy-new-password"
        )
        is True
    )
    assert all(item["hostname"] == "web.smtp.test" and item["password"] == "dummy-runtime-secret" for item in options)
    assert all(
        item["use_tls"] is True and item["start_tls"] is False and item["validate_certs"] is True for item in options
    )
    assert all(item[1]["sender"] == "web@example.test" for item in sent)
    assert all("web@example.test" in str(item[0]["From"]) for item in sent)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [("connect", "failed"), ("data", "unknown"), ("reject", "failed"), ("refused", "failed"), ("none", "accepted")],
)
async def test_transport_acceptance_and_unknown_are_truthful(mail_db, monkeypatch, failure, expected):
    calls = []

    class SMTP:
        def __init__(self, **kwargs):
            pass

        async def connect(self):
            if failure == "connect":
                raise ConnectionError("dummy-private-diagnostic")

        async def send_message(self, message, **kwargs):
            calls.append("send")
            if failure == "data":
                raise ConnectionError("dummy-private-body")
            if failure == "reject":
                raise aiosmtplib.SMTPDataError(554, "dummy-private-body")
            return ({"recipient@example.test": "rejected"} if failure == "refused" else {}), "accepted"

        def close(self):
            calls.append("close")

    monkeypatch.setattr(aiosmtplib, "SMTP", SMTP)
    message = EmailMessage()
    message["To"] = "recipient@example.test"
    message.set_content("Private text")
    result = await email_service.send_message(message)
    assert result.status == expected
    assert calls.count("send") == (0 if failure == "connect" else 1)
    assert calls.count("close") == 1


@pytest.mark.asyncio
async def test_transport_cancellation_is_not_suppressed_or_retried(mail_db, monkeypatch):
    closed = []

    class SMTP:
        def __init__(self, **kwargs):
            pass

        async def connect(self):
            pass

        async def send_message(self, *args, **kwargs):
            raise asyncio.CancelledError

        def close(self):
            closed.append(True)

    monkeypatch.setattr(aiosmtplib, "SMTP", SMTP)
    with pytest.raises(asyncio.CancelledError):
        await email_service.send_message(EmailMessage())
    assert closed == [True]


@pytest.mark.asyncio
async def test_file_tls_mapping_and_no_plaintext_auth(mail_db, monkeypatch):
    monkeypatch.setattr(mail_settings, "get_session_factory", lambda: None)
    monkeypatch.setattr(mail_settings, "is_db_configured", lambda: False)
    mail_db.base.database_url = ""
    assert (await mail_settings.effective_settings()).smtp.security == "starttls"
    mail_db.base.smtp_use_ssl = True
    assert (await mail_settings.effective_settings()).smtp.security == "tls"
    mail_db.base.smtp_security = "starttls"
    with pytest.raises(HTTPException):
        await mail_settings.effective_settings()
    mail_db.base.smtp_security = ""
    mail_db.base.smtp_use_ssl = False
    mail_db.base.smtp_use_tls = False
    with pytest.raises(HTTPException):
        await mail_settings.effective_settings()
    mail_db.base.smtp_username = mail_db.base.smtp_password = ""
    assert (await mail_settings.effective_settings()).smtp.security == "none"


@pytest.mark.asyncio
async def test_connection_checks_use_saved_settings_without_unsaved_targets(mail_db, monkeypatch):
    seen = []

    async def smtp_check(config):
        seen.append(config.host)
        return {"status": "ok"}

    monkeypatch.setattr(api, "_smtp_check", smtp_check)
    body = await saved_draft()
    body["smtp"].update(host="saved.smtp.test", password="dummy-new-secret")
    await mail_settings.save_settings(body)
    response = await mail_db.client.post("/api/v1/admin/email/connection-check", json={})
    assert response.json() == {"revision": 1, "smtp": {"status": "ok"}, "imap": {"status": "disabled"}}
    assert seen == ["saved.smtp.test"]
    response = await mail_db.client.post(
        "/api/v1/admin/email/connection-check", json={"host": "unsaved.smtp.test", "password": "dummy-private"}
    )
    assert response.status_code == 422 and "dummy-private" not in response.text
    assert seen == ["saved.smtp.test"]


@pytest.mark.asyncio
async def test_receipt_is_accepted_test_only_and_current_imap(mail_db, monkeypatch):
    from app.services import mail_delivery

    target = {
        "kind": "test",
        "message_id": "<stable-id@example.test>",
        "recipient_email": "recipient@example.test",
        "status": "pending",
    }

    async def receipt(delivery_id):
        return dict(target)

    monkeypatch.setattr(mail_delivery, "get_receipt_target", receipt)
    body = {"delivery_id": str(uuid4())}
    path = "/api/v1/admin/email/receipt-check"
    assert (await mail_db.client.post(path, json=body)).json() == {"status": "not_sent"}
    target["status"] = "accepted"
    assert (await mail_db.client.post(path, json=body)).json() == {"status": "disabled"}
    target["kind"] = "direct"
    assert (await mail_db.client.post(path, json=body)).status_code == 404
    target["kind"] = "test"
    config = await saved_draft()
    config["imap"].update(enabled=True, host="saved.imap.test", username="inbox", password="dummy-imap-secret")
    await mail_settings.save_settings(config)
    seen = []

    def operation(imap, *, message_id, control=None):
        seen.append((imap.host, message_id))
        return {"status": "confirmed"}

    monkeypatch.setattr(api, "_imap_operation", operation)
    assert (await mail_db.client.post(path, json=body)).json() == {"status": "confirmed"}
    assert seen == [("saved.imap.test", target["message_id"])]
    target["status"] = "unknown"
    assert (await mail_db.client.post(path, json=body)).json() == {"status": "confirmed"}
    target["status"] = "dispatching"
    response = await mail_db.client.post(path, json=body)
    assert response.json() == {"status": "failed", "code": "mail_delivery_in_progress"}


@pytest.mark.parametrize("mailbox,quoted", [("INBOX", '"INBOX"'), ("Receipt Folder", '"Receipt Folder"')])
@pytest.mark.parametrize("exact", [False, True])
def test_imap_search_verifies_exact_header_readonly_without_bodies(monkeypatch, exact, mailbox, quoted):
    calls = []

    class IMAP:
        sock = None

        def __init__(self, host, port, **kwargs):
            assert host == "imap.example.test" and port == 993
            assert kwargs["ssl_context"].check_hostname is True
            calls.append("connect")

        def login(self, username, password):
            calls.append("login")

        def select(self, mailbox, *, readonly):
            assert mailbox == quoted and readonly is True
            calls.append("readonly")
            return "OK", [b"1"]

        def uid(self, command, *args):
            calls.append((command, args))
            if command == "SEARCH":
                return "OK", [b"42"]
            assert args == (b"42", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            value = b"<stable-id@example.test>" if exact else b"<prefix-stable-id@example.test>"
            return "OK", [(b"header", b"Message-ID: " + value + b"\r\n\r\n")]

        def shutdown(self):
            calls.append("shutdown")

    monkeypatch.setattr(api.imaplib, "IMAP4_SSL", IMAP)
    config = mail_settings.IMAPSettings(
        enabled=True, host="imap.example.test", username="user", password="dummy-secret", mailbox=mailbox
    )
    result = api._imap_operation(config, message_id="<stable-id@example.test>")
    assert result["status"] == ("confirmed" if exact else "not_found")
    assert calls[-1] == "shutdown"
    assert not any("BODY[]" in str(call) or "STORE" in str(call) or "CLOSE" in str(call) for call in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, {"revision": 0, "override": None}, {"revision": True, "override": None}])
async def test_corrupt_existing_row_cannot_reset_revision_to_zero(mail_db, value):
    async with mail_db.factory() as session, session.begin():
        session.add(RuntimeSetting(setting_key=mail_settings.KEY, value_json=value))
    response = await mail_db.client.get("/api/v1/admin/email/settings")
    assert response.status_code == 503
    response = await mail_db.client.delete("/api/v1/admin/email/settings?revision=0")
    assert response.status_code == 503


def test_imap_starttls_precedes_authentication_and_failures_are_sanitized(monkeypatch):
    calls = []

    class IMAP:
        sock = None

        def __init__(self, host, port, **kwargs):
            assert port == 143 and 0 < kwargs["timeout"] <= 3
            calls.append("connect")

        def starttls(self, *, ssl_context):
            assert ssl_context.check_hostname is True
            calls.append("tls")

        def login(self, username, password):
            assert calls == ["connect", "tls"]
            calls.append("auth")
            raise RuntimeError("dummy-private-password-and-provider-diagnostic")

        def shutdown(self):
            calls.append("shutdown")

    monkeypatch.setattr(api.imaplib, "IMAP4", IMAP)
    config = mail_settings.IMAPSettings(
        enabled=True,
        host="imap.example.test",
        port=143,
        username="inbox",
        password="dummy-secret",
        security="starttls",
        timeout_seconds=3,
    )
    result = api._imap_operation(config)
    assert result == {"status": "failed", "code": "imap_connection_failed"}
    assert calls == ["connect", "tls", "auth", "shutdown"]
    assert "dummy-" not in json.dumps(result)


def test_imap_rejects_oversized_literal_before_reading():
    class Transport:
        def read(self, size):
            raise AssertionError("An oversized server literal must not be read")

    class Client(api._IMAPBounds, Transport):
        pass

    with pytest.raises(ValueError, match="imap_header_bounds"):
        Client().read(1_000_000_000)


@pytest.mark.asyncio
async def test_smtp_saved_probe_checks_connection_auth_without_message(mail_db, monkeypatch):
    events = []

    class SMTP:
        def __init__(self, **kwargs):
            assert kwargs["validate_certs"] is True
            assert kwargs["start_tls"] is True and kwargs["use_tls"] is False

        async def connect(self):
            events.append("connect")

        async def noop(self):
            events.append("noop")

        def close(self):
            events.append("close")

    monkeypatch.setattr(aiosmtplib, "SMTP", SMTP)
    result = await api._smtp_check((await mail_settings.effective_settings()).smtp)
    assert result == {"status": "ok"} and events == ["connect", "noop", "close"]


@pytest.mark.asyncio
async def test_corrupt_mail_does_not_block_login_methods_or_internal_policy(mail_db, monkeypatch):
    async with mail_db.factory() as session, session.begin():
        session.add(
            RuntimeSetting(setting_key=mail_settings.KEY, value_json={"revision": 1, "override": {"corrupt": True}})
        )
        session.add(
            DomainLoginPolicy(
                domain_id="domain",
                password_enabled=True,
                signup_enabled=True,
                signup_email_domains=["example.test"],
                updated_by_user_id="administrator",
            )
        )
    monkeypatch.setattr(domain_auth, "_factory", lambda: mail_db.factory)
    monkeypatch.setattr(
        domain_auth, "_public_providers", lambda domain_id, rows: [{"id": "provider", "name": "SSO", "kind": "oidc"}]
    )
    monkeypatch.setattr(
        domain_auth, "resolve_enabled_domain", AsyncMock(return_value={"id": "domain", "name": "Domain"})
    )
    application = FastAPI()
    application.include_router(domain_auth_api.public_router, prefix="/api/v1/auth")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/domains/resolve?name=Domain")
    assert response.status_code == 200
    assert response.json()["password_enabled"] is True
    assert response.json()["providers"] == [{"id": "provider", "name": "SSO", "kind": "oidc"}]
    assert response.json()["signup_enabled"] is False
    assert (await enrollment_policy.read_policy())["approval_mode"] == "auto"
    assert (await domain_iam.signup_options())["signup_enabled"] is False
    response = await mail_db.client.get("/api/v1/admin/enrollment-policy")
    assert response.status_code == 200 and response.json()["smtp_configured"] is False
    with pytest.raises(HTTPException):
        await account_recovery.recovery_enabled()


@pytest.mark.asyncio
async def test_file_transport_preserves_legacy_hosts_and_missing_host_readiness(mail_db, monkeypatch):
    monkeypatch.setattr(mail_settings, "get_session_factory", lambda: None)
    monkeypatch.setattr(mail_settings, "is_db_configured", lambda: False)
    mail_db.base.database_url = ""
    mail_db.base.smtp_host = "legacy_smtp.example.test."
    mail_db.base.smtp_timeout_seconds = 90
    settings = await mail_settings.effective_settings()
    assert settings.smtp.host == "legacy_smtp.example.test." and settings.smtp.timeout_seconds == 30
    mail_db.base.smtp_host = ""
    assert await mail_settings.smtp_ready() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_imap_timeout_and_cancellation_close_socket_and_drain_thread(monkeypatch, cancel):
    started, finished = threading.Event(), threading.Event()

    def blocking(config, *, message_id=None, control):
        left, right = socket.socketpair()
        try:
            control.bind(left)
            started.set()
            try:
                left.recv(1)
            except OSError:
                pass
            return {"status": "failed", "code": "imap_connection_failed"}
        finally:
            left.close()
            right.close()
            finished.set()

    monkeypatch.setattr(api, "_imap_operation", blocking)
    config = mail_settings.IMAPSettings(enabled=True, host="imap.example.test", timeout_seconds=3 if cancel else 0.1)
    operation = asyncio.create_task(api._imap_check(config))
    assert await asyncio.wait_for(asyncio.to_thread(started.wait, 1), 2)
    if cancel:
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation
    else:
        assert await operation == {"status": "failed", "code": "imap_timeout"}
    assert finished.is_set(), "The request must not return while its credential-bearing thread is alive"


def test_imap_trickle_obeys_absolute_read_deadline():
    class File:
        def read(self, size):
            time.sleep(0.01)
            return b"x"

    client = api._IMAPBounds()
    client._mail_control = api._IMAPControl(0.03)
    client._mail_bytes = 0
    client.sock = SimpleNamespace(settimeout=lambda timeout: None)
    client.file = File()
    with pytest.raises(TimeoutError):
        client.readline()
