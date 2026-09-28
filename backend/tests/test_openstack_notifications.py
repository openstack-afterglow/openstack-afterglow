"""Native notification behavior; no live broker or OpenStack required."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import Integer, MetaData, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.activity import ActivityLog
from app.services import openstack_notifications as notifications


def encode(event_type="compute.instance.create.end", **changes):
    envelope = {
        "message_id": "notification-1",
        "event_type": event_type,
        "priority": "INFO",
        "timestamp": "2026-09-28 10:11:12.123456",
        "_context_request_id": "req-123",
        "_context_user_id": "user-1",
        "payload": {"instance_id": "instance-1", "tenant_id": "project-1"},
    }
    envelope.update(changes)
    return json.dumps(envelope).encode()


def test_legacy_envelope_normalizes_correlation_and_never_retains_secrets():
    body = encode(
        payload={
            "instance_id": "instance-1",
            "tenant_id": "project-1",
            "display_name": "password=hunter2",
            "metadata": {"token": "secret-token"},
            "exception": {"message": "Authorization: Bearer secret-token", "code": 500},
        },
        _context_auth_token="secret-token",
    )
    row = notifications.normalize_notification(body, "nova")
    assert (row["source"], row["service"], row["status"]) == ("openstack", "nova", "success")
    assert (row["project_id"], row["user_id"], row["resource_id"]) == ("project-1", "user-1", "instance-1")
    assert row["request_id"] == "req-123"
    assert row["created_at"].microsecond == 123456
    assert row["resource_name"] is None
    assert row["extra"] == {"priority": "info", "normalization_version": 1, "error_code": 500}
    assert "secret-token" not in str(row)
    assert "hunter2" not in str(row)


def test_versioned_oslo_nova_failure_uses_safe_error_summary():
    body = encode(
        "instance.create.error",
        priority="ERROR",
        payload={
            "nova_object.name": "InstanceActionPayload",
            "nova_object.data": {
                "uuid": "instance-2",
                "project_id": "project-2",
                "user_id": "user-2",
                "exception": {
                    "nova_object.data": {"code": 403, "type": "MaxRetriesExceeded", "message": "password=do-not-store"}
                },
            },
        },
    )
    row = notifications.normalize_notification(
        json.dumps({"oslo.version": "2.0", "oslo.message": body.decode()}).encode(), "nova"
    )
    assert row["resource_id"] == "instance-2"
    assert row["user_id"] == "user-2"
    assert row["project_id"] == "project-2"
    assert row["status"] == "failed"
    assert row["extra"]["error_code"] == 403
    assert row["extra"]["error_type"] == "MaxRetriesExceeded"
    assert row["http_status"] == 403
    assert "do-not-store" not in str(row)


@pytest.mark.parametrize(
    ("event_type", "priority", "status"),
    [
        ("volume.create.start", "INFO", "started"),
        ("volume.update", "INFO", "started"),
        ("identity.user.created", "AUDIT", "success"),
        ("port.update.end", "WARNING", "success"),
        ("compute.instance.create.end", "ERROR", "failed"),
        ("compute.instance.create.error", "INFO", "failed"),
        ("unknown.notification", "unexpected", "started"),
    ],
)
def test_status_preserves_uncertainty_and_error_priority_wins(event_type, priority, status):
    row = notifications.normalize_notification(encode(event_type, priority=priority), "nova")
    assert row["status"] == status


def test_neutron_uses_affected_port_not_related_network():
    row = notifications.normalize_notification(
        encode(
            "port.update.end",
            payload={
                "port": {"id": "port-1", "network_id": "network-1", "project_id": "owner-project"},
            },
        ),
        "neutron",
    )
    assert row["resource_type"] == "port"
    assert row["resource_id"] == "port-1"
    assert row["project_id"] == "owner-project"


def test_keystone_cadf_target_and_unscoped_events_remain_unknown():
    row = notifications.normalize_notification(
        encode(
            "identity.user.created",
            payload={
                "target": {"id": "affected-user"},
                "initiator": {"id": "https://identity.example/user"},
            },
            _context_user_id=None,
        ),
        "keystone",
    )
    assert row["resource_type"] == "user"
    assert row["resource_id"] == "affected-user"
    assert row["project_id"] == ""
    assert row["user_id"] == ""
    assert row["status"] == "success"


def test_untrusted_detail_is_bounded_or_omitted_not_clipped_into_identifiers():
    row = notifications.normalize_notification(
        encode(
            payload={
                "instance_id": "x" * 129,
                "project_id": "p" * 65,
                "user_id": "Bearer secret",
                "exception": {"code": "token=secret"},
                "extra": {"password": "secret"},
            },
            _context_user_id=None,
            _context_request_id="r" * 129,
        ),
        "nova",
    )
    assert row["resource_id"] is None
    assert row["project_id"] == ""
    assert row["user_id"] == ""
    assert row["request_id"] is None
    assert row["extra"] == {"priority": "info", "normalization_version": 1}


@pytest.mark.parametrize(
    "body",
    [b"not-json", b"[]", b'{"oslo.message": "[]"}', b"{}", b'{"event_type": 12}', b'{"event_type":"x", "payload":NaN}'],
)
def test_malformed_envelopes_are_rejected(body):
    with pytest.raises(notifications.InvalidNotification):
        notifications.normalize_notification(body, "nova")


def test_oversized_message_is_rejected_before_decoding():
    with pytest.raises(notifications.InvalidNotification):
        notifications.normalize_notification(b"x" * 1025, "nova", max_bytes=1024)


def test_external_id_survives_transport_wrappers_and_is_service_scoped():
    body = encode()
    direct = notifications.normalize_notification(body, "nova")
    wrapped = notifications.normalize_notification(
        json.dumps({"oslo.message": body.decode(), "_unique_id": "transport-redelivery"}).encode(), "nova"
    )
    assert direct["external_id"] == wrapped["external_id"]
    assert direct["external_id"] != notifications.normalize_notification(body, "cinder")["external_id"]
    assert (
        direct["external_id"]
        != notifications.normalize_notification(encode(message_id="notification-2"), "nova")["external_id"]
    )


def test_missing_message_id_hashes_canonical_event_without_collapsing_distinct_events():
    envelope = json.loads(encode(message_id=None))
    first = notifications.normalize_notification(json.dumps(envelope).encode(), "nova")
    reordered = notifications.normalize_notification(
        json.dumps(dict(reversed(list(envelope.items())))).encode(), "nova"
    )
    assert first["external_id"] == reordered["external_id"]
    envelope["timestamp"] = "2026-09-28 10:11:13"
    assert (
        first["external_id"]
        != notifications.normalize_notification(json.dumps(envelope).encode(), "nova")["external_id"]
    )


@pytest.fixture
async def notification_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # SQLite autoincrement requires INTEGER, not the production BIGINT spelling.
    # Copy metadata locally rather than changing shared ORM metadata for the suite.
    table = ActivityLog.__table__.to_metadata(MetaData())
    table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def test_redelivery_after_commit_creates_one_durable_activity(notification_db):
    _, factory = notification_db
    row = notifications.normalize_notification(encode(), "nova")
    assert await notifications.persist_notification(row, factory) is True
    assert await notifications.persist_notification(row, factory) is False
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ActivityLog)) == 1
        saved = await session.scalar(select(ActivityLog))
        assert saved.external_id == row["external_id"]
        assert saved.status == "success"
    distinct = notifications.normalize_notification(encode(message_id="another-event"), "nova")
    assert await notifications.persist_notification(distinct, factory) is True
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ActivityLog)) == 2


class Delivery:
    def __init__(self, body, factory):
        self.body = body
        self.factory = factory
        self.outcome = None

    async def ack(self):
        # Ack is observable only after another DB session sees the committed row.
        async with self.factory() as session:
            assert await session.scalar(select(func.count()).select_from(ActivityLog)) == 1
        self.outcome = "acked"

    async def nack(self, *, requeue):
        self.outcome = "requeued" if requeue else "dropped"

    async def reject(self, *, requeue):
        self.outcome = "requeued" if requeue else "rejected"


async def test_database_outage_requeues_then_redelivery_commits_before_ack(notification_db, monkeypatch):
    engine, factory = notification_db
    monkeypatch.setattr(notifications, "get_session_factory", lambda: factory)
    collector = notifications.NotificationCollector(
        SimpleNamespace(openstack_notifications_max_message_bytes=1048576), None
    )
    message = Delivery(encode(), factory)

    def database_outage(*args):
        raise OperationalError("database unavailable", {}, Exception())

    event.listen(engine.sync_engine, "before_cursor_execute", database_outage)
    try:
        with pytest.raises(OperationalError):
            await collector.handle_message(message, "nova")
        assert message.outcome == "requeued"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", database_outage)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ActivityLog)) == 0
    await collector.handle_message(message, "nova")
    assert message.outcome == "acked"
    await collector.handle_message(Delivery(encode(), factory), "nova")
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ActivityLog)) == 1


async def test_poison_message_rejected_without_database_write(notification_db):
    _, factory = notification_db
    collector = notifications.NotificationCollector(
        SimpleNamespace(openstack_notifications_max_message_bytes=1048576), None
    )
    message = Delivery(b"not-json", factory)
    await collector.handle_message(message, "nova")
    assert message.outcome == "rejected"
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ActivityLog)) == 0


async def test_disabled_start_does_not_require_amqp_dependency_or_url():
    assert (
        await notifications.start_notification_collector(SimpleNamespace(openstack_notifications_enabled=False)) is None
    )
    await notifications.stop_notification_collector(None)


def test_cinder_versioned_ids_and_legacy_request_context():
    row = notifications.normalize_notification(
        encode(
            "volume.create.error",
            payload={
                "oslo.versionedobjects.data": {"volume_id": "volume-1"},
            },
            _context_user_id=None,
            _context_user="legacy-user",
            _context_tenant="legacy-project",
        ),
        "cinder",
    )
    assert row["service"] == "cinder"
    assert row["status"] == "failed"
    assert row["resource_id"] == "volume-1"
    assert row["project_id"] == "legacy-project"
    assert row["user_id"] == "legacy-user"


def test_unpaired_unicode_message_id_is_hashed_without_poisoning_delivery():
    row = notifications.normalize_notification(encode(message_id="bad-surrogate-\ud800"), "nova")
    assert (row["status"], row["resource_id"]) == ("success", "instance-1")
    assert "bad-surrogate" not in str(row)


@pytest.mark.parametrize(
    "url", ["", "http://broker", "amqp://broker", "amqp://user@broker", "amqp://user:password@broker:0"]
)
async def test_enabled_collector_never_falls_back_to_implicit_broker_credentials(url):
    from pydantic import SecretStr

    settings = SimpleNamespace(openstack_notifications_enabled=True, openstack_notifications_amqp_url=SecretStr(url))
    with pytest.raises(ValueError, match="explicit credentials"):
        await notifications.start_notification_collector(settings)


def test_long_event_type_preserves_failure_status_before_storage_bound():
    row = notifications.normalize_notification(encode("instance." + "x" * 130 + ".error"), "nova")
    assert row["event_type"] == "instance." + "x" * 119
    assert row["status"] == "failed"
    assert row["resource_type"] == "instance"


@pytest.mark.parametrize(("outcome", "status"), [("success", "success"), ("failure", "failed"), ("pending", "started")])
def test_keystone_cadf_authentication_uses_outcome_actor_and_target_not_event_id(outcome, status):
    # Shape follows Keystone's documented authentication CADF notification:
    # https://docs.openstack.org/keystone/latest/admin/event_notifications.html
    row = notifications.normalize_notification(
        encode(
            "identity.authenticate",
            payload={
                "typeURI": "http://schemas.dmtf.org/cloud/audit/1.0/event",
                "eventType": "activity",
                "action": "authenticate",
                "outcome": outcome,
                "id": "openstack:audit-event-id",
                "initiator": {
                    "typeURI": "service/security/account/user",
                    "id": "actor-user",
                    "credential": {"token": "never-store-token"},
                },
                "target": {"typeURI": "service/security/account/user", "id": "openstack:target-id"},
                "reason": {"reasonCode": 401, "reasonType": "password=never-store-password"},
            },
            _context_user_id=None,
        ),
        "keystone",
    )
    assert row["status"] == status
    assert row["resource_id"] == "openstack:target-id"
    assert row["user_id"] == "actor-user"
    assert row["project_id"] == ""
    assert row["http_status"] == 401
    assert "audit-event-id" not in str(row)
    assert "never-store" not in str(row)


@pytest.mark.parametrize("cadf", [False, True])
def test_keystone_resource_info_is_affected_resource_for_basic_and_cadf(cadf):
    payload = {"resource_info": "affected-project"}
    if cadf:
        payload.update(
            {
                "eventType": "activity",
                "outcome": "success",
                "id": "audit-event-id",
                "target": {"id": "openstack:cadf-target"},
            }
        )
    row = notifications.normalize_notification(encode("identity.project.created", payload=payload), "keystone")
    assert row["resource_type"] == "project"
    assert row["resource_id"] == "affected-project"
    assert row["project_id"] == ""  # Affected project is not an emitted request scope.


@pytest.mark.parametrize("resource", ["backup", "snapshot"])
def test_cinder_specific_resource_wins_over_containing_volume(resource):
    row = notifications.normalize_notification(
        encode(
            f"volume.{resource}.create.end",
            payload={
                "volume_id": "source-volume",
                f"{resource}_id": "affected-resource",
            },
        ),
        "cinder",
    )
    assert row["resource_type"] == resource
    assert row["resource_id"] == "affected-resource"


@pytest.mark.parametrize("error_type", ["password=secret", "Error with raw prose", "Error\nAuthorization", "X" * 65])
def test_failure_type_never_accepts_prose_or_unbounded_values(error_type):
    row = notifications.normalize_notification(
        encode(
            "instance.create.error",
            payload={
                "exception": {"type": error_type, "message": "raw secret text", "code": 500},
            },
        ),
        "nova",
    )
    assert row["extra"] == {"priority": "info", "normalization_version": 1, "error_code": 500}
    assert row["http_status"] == 500
    assert "raw secret text" not in str(row)


def test_top_level_allowlisted_exception_name_preserves_max_retries_reason():
    row = notifications.normalize_notification(
        encode(
            "instance.create.error",
            payload={
                "exception_name": "MaxRetriesExceeded",
                "exception_code": 500,
                "exception_message": "password=do-not-retain",
                "name": "untrusted-resource-name",
            },
        ),
        "nova",
    )
    assert row["extra"]["error_type"] == "MaxRetriesExceeded"
    assert row["http_status"] == 500
    assert "do-not-retain" not in str(row)
    assert "untrusted-resource-name" not in str(row)


def test_nova_volume_attach_preserves_instance_as_primary_resource():
    row = notifications.normalize_notification(
        encode(
            "instance.volume_attach.end",
            payload={
                "instance_id": "affected-instance",
                "volume_id": "attached-volume",
            },
        ),
        "nova",
    )
    assert row["resource_type"] == "instance"
    assert row["resource_id"] == "affected-instance"


def test_nova_real_exception_payload_keeps_class_but_not_message_or_traceback():
    # Nova doc/notification_samples/instance-create-error.json uses fault's
    # versioned ExceptionPayload.data.exception, not exception_name/type.
    row = notifications.normalize_notification(
        encode(
            "instance.create.error",
            priority="ERROR",
            payload={
                "nova_object.data": {
                    "uuid": "instance-1",
                    "fault": {
                        "nova_object.name": "ExceptionPayload",
                        "nova_object.version": "1.1",
                        "nova_object.data": {
                            "exception": "MaxRetriesExceeded",
                            "exception_message": "password=raw-message",
                            "traceback": "token=raw-traceback",
                            "function_name": "_build_resources",
                        },
                    },
                },
            },
        ),
        "nova",
    )
    assert row["status"] == "failed"
    assert row["extra"]["error_type"] == "MaxRetriesExceeded"
    assert row["resource_id"] == "instance-1"
    assert "raw-message" not in str(row)
    assert "raw-traceback" not in str(row)


@pytest.mark.parametrize("type_uri", [[], {}, 123, None])
def test_malformed_cadf_actor_type_does_not_poison_other_event_fields(type_uri):
    row = notifications.normalize_notification(
        encode(
            "identity.authenticate",
            _context_user_id=None,
            payload={
                "eventType": "activity",
                "outcome": "failure",
                "id": "audit-event-id",
                "initiator": {"typeURI": type_uri, "id": "not-a-confirmed-user"},
                "target": {"id": "affected-target"},
            },
        ),
        "keystone",
    )
    assert row["user_id"] == ""
    assert row["resource_id"] == "affected-target"
    assert row["status"] == "failed"


def test_request_id_prefers_local_correlation_across_sources_then_global_fallback():
    body = encode(_context_request_id=None, global_request_id="req-global", context={"request_id": "req-local"})
    assert notifications.normalize_notification(body, "nova")["request_id"] == "req-local"
    body = encode(_context_request_id=None, context={"global_request_id": "req-global"})
    assert notifications.normalize_notification(body, "nova")["request_id"] == "req-global"
