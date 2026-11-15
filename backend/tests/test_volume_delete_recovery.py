"""Fail-closed Cinder/Ceph volume delete diagnosis and recovery contracts."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from openstack.exceptions import ResourceNotFound

from app.models.storage import VolumeDeleteBackendInspection, VolumeDeleteDiagnostic
from app.services import ceph_rbd, volume_delete_recovery
from tests.conftest import make_mock_conn

VOLUME_ID = "676cc4e2-0000-0000-0000-000000000000"
IMAGE_NAME = f"volume-{VOLUME_ID}"
IMAGE_ID = "aa11bb22cc33"


def _volume(
    status: str = "error_deleting",
    *,
    attachments: list[dict] | None = None,
    updated_at: str = "2026-01-01T00:00:00Z",
):
    return SimpleNamespace(
        id=VOLUME_ID,
        status=status,
        attachments=attachments or [],
        project_id="project-1",
        name="critical-volume",
        size=30,
        host="controller@ceph#ceph",
        updated_at=updated_at,
        migration_status=None,
        group_id=None,
    )


def _settings(*, enabled: bool = False):
    return SimpleNamespace(
        ceph_rbd_enabled=enabled,
        ceph_rbd_cluster_fsid="cluster-fsid",
        ceph_rbd_volume_pools={"ceph": "volumes"},
    )


@contextmanager
def _safe_queries(conn, *, settings=None, client=None):
    conn.compute.servers.return_value = []
    conn.block_storage.volumes.return_value = []
    settings = settings or _settings()
    with (
        patch("app.services.volume_delete_recovery.cinder.list_volume_attachments", return_value=[]) as attachments,
        patch("app.services.volume_delete_recovery.cinder.list_snapshots", return_value=[]) as snapshots,
        patch("app.services.volume_delete_recovery.cinder.list_backups", return_value=[]) as backups,
        patch("app.services.volume_delete_recovery.cinder.list_volume_messages", return_value=[]) as messages,
        patch("app.services.volume_delete_recovery.get_settings", return_value=settings),
        patch("app.services.volume_delete_recovery.ceph_rbd.from_settings", return_value=client),
    ):
        yield SimpleNamespace(
            attachments=attachments,
            snapshots=snapshots,
            backups=backups,
            messages=messages,
        )


def _recoverable_diagnostic(
    *, backend: VolumeDeleteBackendInspection | None = None, root_cause: str = "recoverable_backend_unverified"
):
    return VolumeDeleteDiagnostic(
        volume_id=VOLUME_ID,
        status="error_deleting",
        project_id="project-1",
        name="critical-volume",
        size_gb=30,
        backend_host="controller@ceph#ceph",
        updated_at="2026-01-01T00:00:00Z",
        root_cause_code=root_cause,
        confidence="high",
        summary="recoverable",
        recommended_action="recover",
        recovery_available=True,
        backend=backend or VolumeDeleteBackendInspection(),
    )


def test_diagnosis_uses_caller_admin_connection_and_all_project_dependency_queries() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume()

    with _safe_queries(conn) as calls:
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)

    assert diagnostic.root_cause_code == "recoverable_backend_unverified"
    assert diagnostic.recovery_available is True
    calls.attachments.assert_called_once_with(conn, VOLUME_ID)
    calls.snapshots.assert_called_once_with(conn, volume_id=VOLUME_ID, all_projects=True)
    calls.backups.assert_called_once_with(conn, volume_id=VOLUME_ID, all_projects=True)
    conn.compute.servers.assert_called_once_with(details=True, all_projects=True)
    conn.block_storage.volumes.assert_called_once_with(details=True, all_projects=True)


def test_any_unknown_dependency_blocks_recovery_instead_of_assuming_absence() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume()

    with _safe_queries(conn) as calls:
        calls.snapshots.side_effect = TimeoutError("cinder timeout")
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)

    assert diagnostic.root_cause_code == "dependency_unknown"
    assert diagnostic.recovery_available is False
    assert next(check for check in diagnostic.checks if check.name == "snapshots").state == "unknown"


def test_nova_attachment_blocks_recovery_even_when_cinder_lists_none() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume()
    conn.compute.servers.return_value = [SimpleNamespace(id="server-1", attached_volumes=[{"id": VOLUME_ID}])]

    with _safe_queries(conn):
        conn.compute.servers.return_value = [SimpleNamespace(id="server-1", attached_volumes=[{"id": VOLUME_ID}])]
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)

    assert diagnostic.root_cause_code == "attached_volume_delete_blocked"
    assert next(check for check in diagnostic.checks if check.name == "nova_attachments").detail == "server:server-1"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(401, "authentication_scope_failed"), (403, "authorization_denied")],
)
def test_nested_http_status_is_preserved_for_auth_failures(status_code: int, expected: str) -> None:
    conn = make_mock_conn()
    inner = RuntimeError("keystone rejected")
    inner.response = SimpleNamespace(status_code=status_code)
    outer = RuntimeError("adapter failure")
    outer.__cause__ = inner
    conn.block_storage.get_volume.side_effect = outer

    diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)

    assert diagnostic.root_cause_code == expected
    assert diagnostic.recovery_available is False


def test_fresh_deleting_volume_is_not_mutated() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume("deleting", updated_at=datetime.now(UTC).isoformat())

    with _safe_queries(conn):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)

    assert diagnostic.root_cause_code == "deleting_in_progress"
    assert diagnostic.recovery_available is False


def test_missing_name_mapping_is_recoverable_only_with_safe_rbd_evidence() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume()
    info = ceph_rbd.RbdImageInfo(id=IMAGE_ID, size=30 * 1024**3, order=22)
    client = MagicMock()
    client.cluster_fsid.return_value = ("present", "cluster-fsid")
    client.image_info_by_name.return_value = ("absent", None)
    client.directory_lookup.return_value = ("present", IMAGE_ID)
    client.stat_object.side_effect = [("absent", None), ("present", None)]
    client.image_info_by_id.return_value = ("present", info)
    client.object_map_present.return_value = ("present", None)
    client.watchers.return_value = ("absent", "watchers=0")
    client.snapshots_by_id.return_value = ("absent", "snapshots=0")
    client.trash_contains.return_value = ("absent", "trash_clear")

    with _safe_queries(conn, settings=_settings(enabled=True), client=client):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)

    assert diagnostic.root_cause_code == "rbd_name_mapping_missing"
    assert diagnostic.recovery_available is True
    assert diagnostic.backend == VolumeDeleteBackendInspection(
        mode="inspected",
        classification="name_mapping_missing",
        pool="volumes",
        image_name=IMAGE_NAME,
        image_id=IMAGE_ID,
        size_bytes=30 * 1024**3,
        order=22,
    )


def test_missing_cinder_record_requires_matching_fsid_and_reports_backend_residue() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = ResourceNotFound()
    client = MagicMock()
    client.cluster_fsid.return_value = ("present", "cluster-fsid")
    client.directory_lookup.return_value = ("present", IMAGE_ID)
    client.stat_object.return_value = ("present", None)
    client.trash_contains.return_value = ("absent", "trash_clear")

    with _safe_queries(conn, settings=_settings(enabled=True), client=client):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID)

    assert result.status == "backend_residue"
    assert result.verified_deleted is False
    assert result.backend_verification == "residue"


def test_missing_cinder_record_with_backend_lookup_unknown_is_not_false_success() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = ResourceNotFound()
    client = MagicMock()
    client.cluster_fsid.return_value = ("present", "wrong-cluster")

    with _safe_queries(conn, settings=_settings(enabled=True), client=client):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID)

    assert result.status == "backend_unverified"
    assert result.verified_deleted is False
    assert result.backend_verification == "unknown"
    assert result.diagnostic.backend.mode == "unknown"


def test_missing_cinder_record_when_ceph_unavailable_is_backend_unverified() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = ResourceNotFound()

    with _safe_queries(conn, settings=_settings(enabled=False), client=None):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID)

    assert result.status == "backend_unverified"
    assert result.verified_deleted is False
    assert result.backend_verification == "unavailable"
    assert result.diagnostic.backend.mode == "unavailable"
    assert result.diagnostic.recovery_available is False


def test_missing_cinder_record_with_inspected_backend_absent_is_already_deleted() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = ResourceNotFound()
    client = MagicMock()
    client.cluster_fsid.return_value = ("present", "cluster-fsid")
    client.directory_lookup.return_value = ("absent", None)
    client.stat_object.return_value = ("absent", None)
    client.image_info_by_name.return_value = ("absent", None)
    client.trash_contains.return_value = ("absent", "trash_clear")

    with _safe_queries(conn, settings=_settings(enabled=True), client=client):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID)

    assert result.status == "already_deleted"
    assert result.verified_deleted is True
    assert result.backend_verification == "verified"
    assert result.diagnostic.backend.mode == "inspected"
    assert result.diagnostic.backend.classification == "absent"
    assert result.diagnostic.recovery_available is False


def test_missing_cinder_record_with_unknown_pool_lookup_is_backend_unverified() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = ResourceNotFound()
    client = MagicMock()
    client.cluster_fsid.return_value = ("present", "cluster-fsid")
    client.directory_lookup.return_value = ("unknown", "rados_timeout")
    client.stat_object.return_value = ("absent", None)
    client.trash_contains.return_value = ("absent", "trash_clear")

    with _safe_queries(conn, settings=_settings(enabled=True), client=client):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID)

    assert result.status == "backend_unverified"
    assert result.verified_deleted is False
    assert result.backend_verification == "unknown"
    assert result.diagnostic.root_cause_code == "backend_lookup_unknown"
    assert result.diagnostic.recovery_available is False


def test_missing_cinder_record_with_trash_entry_reports_backend_residue() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = ResourceNotFound()
    client = MagicMock()
    client.cluster_fsid.return_value = ("present", "cluster-fsid")
    client.directory_lookup.return_value = ("absent", None)
    client.stat_object.return_value = ("absent", None)
    client.trash_contains.return_value = ("present", "trash_match")

    with _safe_queries(conn, settings=_settings(enabled=True), client=client):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID)

    assert result.status == "backend_residue"
    assert result.verified_deleted is False
    assert result.backend_verification == "residue"
    assert result.diagnostic.root_cause_code == "api_absent_backend_present"
    assert any(check.name == "rbd_trash" and check.state == "present" for check in result.diagnostic.checks)
    client.trash_contains.assert_called_once_with("volumes", IMAGE_NAME, None)


def test_incident_recovery_restores_mapping_force_deletes_verifies_backend_and_quota() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = [_volume(), ResourceNotFound()]
    conn.block_storage.volumes.return_value = []
    backend = VolumeDeleteBackendInspection(
        mode="inspected",
        classification="name_mapping_missing",
        pool="volumes",
        image_name=IMAGE_NAME,
        image_id=IMAGE_ID,
        size_bytes=30 * 1024**3,
        order=22,
    )
    diagnostic = _recoverable_diagnostic(backend=backend, root_cause="rbd_name_mapping_missing")
    info = ceph_rbd.RbdImageInfo(id=IMAGE_ID, size=30 * 1024**3, order=22)
    client = MagicMock()
    client.name_mapping_payload.side_effect = ceph_rbd.RbdClient.name_mapping_payload
    client.image_info_by_name.return_value = ("present", info)
    client.stat_object.return_value = ("absent", None)
    client.object_map_present.return_value = ("absent", None)
    client.directory_lookup.return_value = ("absent", None)
    client.directory_lookup_by_id.return_value = ("absent", None)
    client.trash_contains.return_value = ("absent", None)
    client.sampled_data_objects.return_value = ("absent", "sampled=32/7680")
    client.read_name_mapping.return_value = (
        "present",
        ceph_rbd.RbdClient.name_mapping_payload(IMAGE_ID),
    )
    quota_values = iter(
        [
            {"volumes": {"in_use": 10}, "gigabytes": {"in_use": 300}},
            {"volumes": {"in_use": 9}, "gigabytes": {"in_use": 270}},
        ]
    )

    with (
        patch("app.services.volume_delete_recovery.diagnose_volume_delete_issue", return_value=diagnostic),
        patch("app.services.volume_delete_recovery.get_settings", return_value=_settings(enabled=True)),
        patch("app.services.volume_delete_recovery.ceph_rbd.from_settings", return_value=client),
        patch("app.services.volume_delete_recovery.cinder.list_volume_attachments", return_value=[]),
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as force_delete,
        patch(
            "app.services.volume_delete_recovery.cinder.get_volume_quota",
            side_effect=lambda *_args, **_kwargs: next(quota_values),
        ),
    ):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID, verify_timeout_seconds=0)

    assert result.status == "deleted"
    assert result.verified_deleted is True
    assert result.backend_verification == "verified"
    assert result.quota_verification == "verified"
    assert [step.action for step in result.steps] == [
        "diagnose",
        "restore_name_mapping",
        "verify_name_mapping",
        "recheck_state",
        "force_delete",
        "verify_after_force_delete",
        "backend_verify",
        "cleanup_stale_name_mapping",
        "quota_verify",
    ]
    client.restore_name_mapping.assert_called_once_with("volumes", IMAGE_NAME, IMAGE_ID)
    client.cleanup_stale_name_mapping.assert_called_once_with("volumes", IMAGE_NAME, IMAGE_ID)
    force_delete.assert_called_once_with(conn, VOLUME_ID)


@pytest.mark.parametrize(
    ("backend_verification", "expected_status"),
    [("residue", "backend_residue"), ("unknown", "backend_unverified")],
)
def test_cinder_absence_does_not_hide_backend_residue_or_unknown(
    backend_verification: str, expected_status: str
) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = [_volume(), ResourceNotFound()]
    conn.block_storage.volumes.return_value = []
    diagnostic = _recoverable_diagnostic(
        backend=VolumeDeleteBackendInspection(
            mode="inspected",
            classification="consistent",
            pool="volumes",
            image_name=IMAGE_NAME,
            image_id=IMAGE_ID,
            size_bytes=30 * 1024**3,
            order=22,
        ),
        root_cause="backend_present_consistent",
    )
    client = MagicMock()

    with (
        patch("app.services.volume_delete_recovery.diagnose_volume_delete_issue", return_value=diagnostic),
        patch("app.services.volume_delete_recovery.get_settings", return_value=_settings(enabled=True)),
        patch("app.services.volume_delete_recovery.ceph_rbd.from_settings", return_value=client),
        patch("app.services.volume_delete_recovery.cinder.list_volume_attachments", return_value=[]),
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume"),
        patch("app.services.volume_delete_recovery.cinder.get_volume_quota", side_effect=RuntimeError("unavailable")),
        patch("app.services.volume_delete_recovery._verify_backend_after_delete", return_value=backend_verification),
    ):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID, verify_timeout_seconds=0)

    assert result.status == expected_status
    assert result.verified_deleted is False
    assert result.backend_verification == backend_verification


class _HttpError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


@pytest.mark.parametrize(
    ("error", "expected_calls", "expected_status"),
    [
        (_HttpError(400, "volume is still attached"), 2, "backend_unverified"),
        (_HttpError(400, "quota exceeded"), 1, "failed"),
        (_HttpError(403, "forbidden"), 1, "failed"),
    ],
)
def test_force_delete_retries_only_once_for_exact_400_attached(
    error: Exception, expected_calls: int, expected_status: str
) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = [_volume(), ResourceNotFound()]
    conn.block_storage.volumes.return_value = []
    diagnostic = _recoverable_diagnostic()
    effects = [error, None] if expected_calls == 2 else [error]

    with (
        patch("app.services.volume_delete_recovery.diagnose_volume_delete_issue", return_value=diagnostic),
        patch("app.services.volume_delete_recovery.get_settings", return_value=_settings()),
        patch("app.services.volume_delete_recovery.ceph_rbd.from_settings", return_value=None),
        patch("app.services.volume_delete_recovery.cinder.list_volume_attachments", return_value=[]),
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume", side_effect=effects) as force_delete,
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status") as reset_status,
        patch("app.services.volume_delete_recovery.cinder.get_volume_quota", side_effect=RuntimeError("unavailable")),
    ):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID, verify_timeout_seconds=0)

    assert result.status == expected_status
    assert force_delete.call_count == expected_calls
    assert reset_status.call_count == (1 if expected_calls == 2 else 0)


def test_cinder_dependency_lists_forward_volume_and_all_project_filters() -> None:
    from app.services import cinder

    conn = make_mock_conn()
    snapshot = SimpleNamespace(
        id="snap-1",
        name="snapshot",
        status="available",
        volume_id=VOLUME_ID,
        size=30,
        description="",
        created_at=None,
        project_id="project-1",
    )
    backup = SimpleNamespace(
        id="backup-1",
        name="backup",
        status="available",
        volume_id=VOLUME_ID,
        size=30,
        is_incremental=False,
        has_dependent_backups=False,
        created_at=None,
        description="",
    )
    conn.block_storage.snapshots.return_value = [snapshot]
    conn.block_storage.backups.return_value = [backup]

    assert cinder.list_snapshots(conn, volume_id=VOLUME_ID, all_projects=True)[0]["id"] == "snap-1"
    assert cinder.list_backups(conn, volume_id=VOLUME_ID, all_projects=True)[0]["id"] == "backup-1"
    conn.block_storage.snapshots.assert_called_once_with(details=True, volume_id=VOLUME_ID, all_projects=True)
    conn.block_storage.backups.assert_called_once_with(details=True, volume_id=VOLUME_ID, all_projects=True)


def test_cinder_attachment_and_message_requests_use_admin_scope_and_microversion() -> None:
    from app.services import cinder

    conn = make_mock_conn()
    conn.block_storage.get_endpoint.return_value = "https://cinder.example/v3/project/"
    attachments_response = MagicMock()
    attachments_response.json.return_value = {"attachments": [{"id": "attachment-1"}]}
    messages_response = MagicMock()
    messages_response.json.return_value = {"messages": [{"id": "message-1"}]}
    conn.session.get.side_effect = [attachments_response, messages_response]

    assert cinder.list_volume_attachments(conn, VOLUME_ID) == [{"id": "attachment-1"}]
    assert cinder.list_volume_messages(conn, VOLUME_ID) == [{"id": "message-1"}]
    assert conn.session.get.call_args_list == [
        call(
            "https://cinder.example/v3/project/attachments",
            params={"all_tenants": "1", "volume_id": VOLUME_ID},
            headers={"OpenStack-API-Version": "volume 3.70"},
        ),
        call(
            "https://cinder.example/v3/project/messages",
            params={
                "all_tenants": "1",
                "resource_uuid": VOLUME_ID,
                "limit": "50",
                "sort": "created_at:desc",
            },
            headers={"OpenStack-API-Version": "volume 3.70"},
        ),
    ]
    attachments_response.raise_for_status.assert_called_once_with()
    messages_response.raise_for_status.assert_called_once_with()


@pytest.mark.parametrize("status", ["creating", "downloading"])
def test_fresh_creation_is_blocked_with_readonly_evidence(status: str) -> None:
    conn = make_mock_conn()
    volume = _volume(status, updated_at=datetime.now(UTC).isoformat())
    volume.metadata = {"palimpsest_instance_id": "private-build-id"}
    conn.block_storage.get_volume.return_value = volume
    with _safe_queries(conn):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)
    assert diagnostic.root_cause_code == "creation_in_progress"
    assert not diagnostic.recovery_available
    assert diagnostic.owner_service_hint == "palimpsest"
    assert diagnostic.creation_age_seconds is not None
    assert {"backend_host=present", "cinder_messages=absent", "owner_service=palimpsest"} <= set(diagnostic.evidence)
    assert "private-build-id" not in diagnostic.model_dump_json()


@pytest.mark.parametrize(
    ("classification", "watchers", "root", "available"),
    [
        ("absent", None, "creation_stalled", True),
        ("consistent", "absent", "creation_stalled", True),
        ("name_mapping_missing", "absent", "creation_stalled", True),
        ("consistent", "present", "creation_active_watcher", False),
        ("consistent", "unknown", "backend_lookup_unknown", False),
        ("unknown", None, "backend_lookup_unknown", False),
        ("inconsistent", "absent", "backend_inconsistent", False),
    ],
)
@pytest.mark.parametrize("status", ["creating", "downloading"])
def test_stalled_creation_reuses_backend_classification(
    classification: str, watchers: str | None, root: str, available: bool, status: str
) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume(status)

    def inspect(_client, _settings, _id, _host, checks):
        if watchers is not None:
            volume_delete_recovery._add_check(checks, "rbd_watchers", watchers, "sensitive-client-address")
        volume_delete_recovery._add_check(checks, "rbd_snapshots", "absent")
        return VolumeDeleteBackendInspection(
            mode="unknown" if classification == "unknown" else "inspected",
            classification=classification,
        )

    with (
        _safe_queries(conn, client=MagicMock()),
        patch("app.services.volume_delete_recovery._inspect_backend", side_effect=inspect),
    ):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)
    assert diagnostic.root_cause_code == root
    assert diagnostic.recovery_available is available
    assert diagnostic.backend.classification == classification
    assert "sensitive-client-address" not in diagnostic.model_dump_json()


@pytest.mark.parametrize("dependency", ["attachment", "snapshot", "backup", "clone", "group", "migration", "unknown"])
def test_stalled_creation_keeps_dependency_gates_first(dependency: str) -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    conn.block_storage.get_volume.return_value = volume
    with _safe_queries(conn) as queries:
        if dependency == "attachment":
            volume.attachments = [{"server_id": "server-1"}]
        elif dependency == "snapshot":
            queries.snapshots.return_value = [{"id": "snap-1", "status": "available"}]
        elif dependency == "backup":
            queries.backups.return_value = [{"id": "backup-1", "status": "available"}]
        elif dependency == "clone":
            conn.block_storage.volumes.return_value = [SimpleNamespace(id="clone-1", source_volume_id=VOLUME_ID)]
        elif dependency == "group":
            volume.group_id = "group-1"
        elif dependency == "migration":
            volume.migration_status = "migrating"
        else:
            queries.snapshots.side_effect = TimeoutError()
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)
    assert not diagnostic.recovery_available
    assert diagnostic.root_cause_code == (
        "attached_volume_delete_blocked"
        if dependency == "attachment"
        else "dependency_unknown"
        if dependency == "unknown"
        else "dependent_resource_present"
    )


@pytest.mark.parametrize(
    ("status", "age_hours", "expected"),
    [
        ("creating", 1, "creation_stalled"),
        ("downloading", 1, "creation_in_progress"),
        ("downloading", 7, "creation_stalled"),
    ],
)
def test_creation_age_falls_back_to_created_at_and_download_has_longer_gate(
    status: str, age_hours: int, expected: str
) -> None:
    from datetime import timedelta

    conn = make_mock_conn()
    volume = _volume(status, updated_at="")
    volume.created_at = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat()
    conn.block_storage.get_volume.return_value = volume
    with _safe_queries(conn):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)
    assert diagnostic.root_cause_code == expected


@pytest.mark.parametrize("timestamp", ["", "invalid", "2999-01-01T00:00:00Z"])
def test_unprovable_creation_age_never_enables_reset(timestamp: str) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume("creating", updated_at=timestamp)
    with _safe_queries(conn):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)
    assert diagnostic.root_cause_code == "creation_in_progress"
    assert not diagnostic.recovery_available


@pytest.mark.parametrize("mode", ["recover", "force_delete"])
@pytest.mark.parametrize("initial_status", ["creating", "downloading"])
def test_creation_modes_use_reset_then_optional_force_delete(mode: str, initial_status: str) -> None:
    conn = make_mock_conn()
    volume = _volume(initial_status)
    deleted = False
    writes = []

    def get_volume(_id):
        if deleted:
            raise ResourceNotFound()
        return volume

    def reset(_conn, _id, status):
        writes.append(("reset", status))
        volume.status = status

    def force(_conn, _id):
        nonlocal deleted
        assert volume.status == "error", "native Cinder rejects deletion of creating"
        writes.append(("force_delete",))
        deleted = True

    conn.block_storage.get_volume.side_effect = get_volume
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status", side_effect=reset),
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume", side_effect=force),
        patch("app.services.volume_delete_recovery.cinder.delete_volume") as normal_delete,
        patch("app.services.volume_delete_recovery.cinder.get_volume_quota", side_effect=RuntimeError()),
    ):
        result = volume_delete_recovery.recover_delete_volume(
            conn,
            VOLUME_ID,
            verify_timeout_seconds=0,
            mode=mode,
            confirm_volume_id=VOLUME_ID,
            expected_status=initial_status,
        )
    assert writes == ([("reset", "error")] if mode == "recover" else [("reset", "error"), ("force_delete",)])
    assert result.status == ("state_reset" if mode == "recover" else "backend_unverified")
    assert result.previous_status == initial_status
    assert not result.verified_deleted  # Ceph unconfigured, never claim physical deletion.
    assert any(step.action == "reset_state" and step.status == "success" for step in result.steps)
    if mode == "recover":
        assert result.final_status == result.diagnostic.status == "error"
    normal_delete.assert_not_called()


def test_recover_already_error_is_idempotent_without_native_writes() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume("error")
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status") as reset,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        result = volume_delete_recovery.recover_delete_volume(conn, VOLUME_ID, mode="recover")
    assert result.status == "state_reset"
    reset.assert_not_called()
    delete.assert_not_called()


@pytest.mark.parametrize("mode", ["recover", "force_delete"])
@pytest.mark.parametrize("watcher_at", [0, 1, 2, 3])
def test_creation_watcher_blocks_initial_reset_and_destructive_rechecks(mode: str, watcher_at: int) -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    conn.block_storage.get_volume.return_value = volume
    observations = 0

    def inspect(_client, _settings, _id, _host, checks):
        nonlocal observations
        watcher = "present" if observations >= watcher_at else "absent"
        observations += 1
        volume_delete_recovery._add_check(checks, "rbd_watchers", watcher)
        return VolumeDeleteBackendInspection(mode="inspected", classification="consistent")

    def reset(_conn, _id, status):
        volume.status = status

    with (
        _safe_queries(conn, client=MagicMock()),
        patch("app.services.volume_delete_recovery._inspect_backend", side_effect=inspect),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status", side_effect=reset) as reset_call,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
        patch("app.services.volume_delete_recovery.cinder.get_volume_quota", side_effect=RuntimeError()),
    ):
        result = volume_delete_recovery.recover_delete_volume(
            conn, VOLUME_ID, mode=mode, confirm_volume_id=VOLUME_ID, expected_status="creating"
        )
    assert reset_call.call_count == (0 if watcher_at <= 1 else 1)
    delete.assert_not_called()
    assert result.status == (
        "state_reset" if mode == "recover" and watcher_at == 3 else "blocked" if watcher_at == 0 else "failed"
    )


def test_creation_reset_success_delete_failure_reports_error_retry_state() -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    conn.block_storage.get_volume.return_value = volume

    def reset(_conn, _id, status):
        volume.status = status

    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status", side_effect=reset),
        patch(
            "app.services.volume_delete_recovery.cinder.force_delete_volume", side_effect=_HttpError(400, "attached")
        ),
        patch("app.services.volume_delete_recovery.cinder.get_volume_quota", side_effect=RuntimeError()),
    ):
        result = volume_delete_recovery.recover_delete_volume(
            conn, VOLUME_ID, mode="force_delete", confirm_volume_id=VOLUME_ID, expected_status="creating"
        )
    assert result.status == "failed"
    assert result.final_status == volume.status == "error"
    assert result.previous_status == "creating"
    assert [step.action for step in result.steps if step.status == "failed"] == ["force_delete"]
    assert not any(step.action == "reset_attach_status" for step in result.steps)


@pytest.mark.parametrize("mode", ["recover", "force_delete"])
@pytest.mark.parametrize(
    ("confirmed_id", "confirmed_status"),
    [(None, None), ("other-volume", "creating"), (VOLUME_ID, "available")],
)
def test_creation_confirmation_conflict_has_zero_native_writes(
    mode: str, confirmed_id: str | None, confirmed_status: str | None
) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume("creating")
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status") as reset,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        with pytest.raises(volume_delete_recovery.VolumeRecoveryConflict):
            volume_delete_recovery.recover_delete_volume(
                conn,
                VOLUME_ID,
                mode=mode,
                confirm_volume_id=confirmed_id,
                expected_status=confirmed_status,
            )
    reset.assert_not_called()
    delete.assert_not_called()


@pytest.mark.parametrize("mode", ["recover", "force_delete"])
@pytest.mark.parametrize("dependency_at", [1, 2])
def test_creation_dependency_appearing_during_recheck_stops_pipeline(mode: str, dependency_at: int) -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    conn.block_storage.get_volume.return_value = volume

    def reset(_conn, _id, status):
        volume.status = status

    with (
        _safe_queries(conn) as queries,
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status", side_effect=reset) as reset_call,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        queries.snapshots.side_effect = [[]] * dependency_at + [[{"id": "new-snapshot", "status": "creating"}]]
        result = volume_delete_recovery.recover_delete_volume(
            conn, VOLUME_ID, mode=mode, confirm_volume_id=VOLUME_ID, expected_status="creating"
        )
    assert result.status == "failed"
    assert reset_call.call_count == (0 if dependency_at == 1 else 1)
    assert result.diagnostic.root_cause_code == "dependent_resource_present"
    delete.assert_not_called()


def test_live_status_change_after_full_diagnosis_refuses_reset() -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    calls = 0

    def get_volume(_id):
        nonlocal calls
        calls += 1
        if calls == 3:
            return _volume("available")
        return volume

    conn.block_storage.get_volume.side_effect = get_volume
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status") as reset,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        with pytest.raises(volume_delete_recovery.VolumeRecoveryConflict):
            volume_delete_recovery.recover_delete_volume(
                conn, VOLUME_ID, mode="recover", confirm_volume_id=VOLUME_ID, expected_status="creating"
            )
    reset.assert_not_called()
    delete.assert_not_called()


def test_reset_that_does_not_reach_error_never_deletes() -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume("creating")
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status"),
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        result = volume_delete_recovery.recover_delete_volume(
            conn, VOLUME_ID, mode="force_delete", confirm_volume_id=VOLUME_ID, expected_status="creating"
        )
    assert result.status == "failed"
    assert result.final_status == "creating"
    assert any(step.action == "reset_state" and step.status == "failed" for step in result.steps)
    delete.assert_not_called()


def test_creation_force_delete_busy_return_to_available_is_failed_with_refreshed_diagnostic() -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    conn.block_storage.get_volume.return_value = volume

    def reset(_conn, _id, status):
        volume.status = status

    def force(_conn, _id):
        volume.status = "available"  # Cinder VolumeIsBusy manager branch.

    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status", side_effect=reset) as reset_call,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume", side_effect=force) as force_call,
        patch("app.services.volume_delete_recovery.cinder.get_volume_quota", side_effect=RuntimeError()),
    ):
        result = volume_delete_recovery.recover_delete_volume(
            conn,
            VOLUME_ID,
            verify_timeout_seconds=0,
            mode="force_delete",
            confirm_volume_id=VOLUME_ID,
            expected_status="creating",
        )
    assert result.status == "failed"
    assert result.final_status == result.diagnostic.status == "available"
    assert result.diagnostic.root_cause_code == "normal_delete_possible"
    assert result.previous_status == "creating"
    assert not result.verified_deleted
    reset_call.assert_called_once_with(conn, VOLUME_ID, "error")
    force_call.assert_called_once_with(conn, VOLUME_ID)
    assert result.steps[-1].action == "verify_after_force_delete"
    assert result.steps[-1].detail == "creation_delete_state_changed:available"


@pytest.mark.parametrize(
    "metadata",
    [
        {"afterglow_managed_by": "afterglow", "afterglow_purpose": "cloud-shell-home"},
        {"afterglow_layer_artifact_id": "artifact-private"},
        {"afterglow_consume_id": "consume-private"},
    ],
)
def test_creation_owner_hints_cover_existing_afterglow_managed_volumes(metadata: dict) -> None:
    conn = make_mock_conn()
    volume = _volume("creating")
    volume.metadata = metadata
    conn.block_storage.get_volume.return_value = volume
    with _safe_queries(conn):
        diagnostic = volume_delete_recovery.diagnose_volume_delete_issue(conn, VOLUME_ID)
    assert diagnostic.owner_service_hint == "afterglow"
    assert "owner_service=afterglow" in diagnostic.evidence
    assert "artifact-private" not in diagnostic.model_dump_json()
    assert "consume-private" not in diagnostic.model_dump_json()


@pytest.mark.parametrize("mode", ["recover", "force_delete"])
def test_stale_creation_confirmation_conflicts_when_initial_live_state_is_already_available(mode: str) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.return_value = _volume("available")
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status") as reset,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        with pytest.raises(volume_delete_recovery.VolumeRecoveryConflict):
            volume_delete_recovery.recover_delete_volume(
                conn, VOLUME_ID, mode=mode, confirm_volume_id=VOLUME_ID, expected_status="creating"
            )
    reset.assert_not_called()
    delete.assert_not_called()


@pytest.mark.parametrize("mode", ["recover", "force_delete"])
@pytest.mark.parametrize(
    ("status_code", "root"),
    [(401, "authentication_scope_failed"), (403, "authorization_denied")],
)
def test_confirmation_does_not_turn_native_auth_failure_into_state_conflict(
    mode: str, status_code: int, root: str
) -> None:
    conn = make_mock_conn()
    conn.block_storage.get_volume.side_effect = _HttpError(status_code, "native lookup denied")
    with (
        _safe_queries(conn),
        patch("app.services.volume_delete_recovery.cinder.reset_volume_status") as reset,
        patch("app.services.volume_delete_recovery.cinder.force_delete_volume") as delete,
    ):
        result = volume_delete_recovery.recover_delete_volume(
            conn, VOLUME_ID, mode=mode, confirm_volume_id=VOLUME_ID, expected_status="creating"
        )
    assert result.status == "blocked"
    assert result.diagnostic.root_cause_code == root
    reset.assert_not_called()
    delete.assert_not_called()
