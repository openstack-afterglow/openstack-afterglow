from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "layer-block-smoke.py"


def _smoke(monkeypatch, *, project="project-a", marker=None):
    spec = importlib.util.spec_from_file_location("layer_block_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    events = []
    conn = MagicMock()
    conn.session.get_project_id.side_effect = lambda: events.append("scope") or project
    conn.authorize.side_effect = lambda: events.append("authenticate")
    conn._afterglow_project_id = marker
    client = MagicMock()
    client.__enter__.return_value = client
    monkeypatch.setattr(module.openstack, "connect", MagicMock(return_value=conn))
    monkeypatch.setattr(module.httpx, "Client", MagicMock(return_value=client))
    monkeypatch.setenv("AFTERGLOW_TOKEN", "private-api-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--url",
            "https://afterglow.example",
            "--expected-project",
            "project-a",
            "--exercise",
            "--import-id",
            "9",
            "--flavor",
            "flavor-a",
            "--name",
            "smoke",
        ],
    )
    return module, conn, client, events


@pytest.mark.parametrize(
    "project,marker", [("project-b", None), ("project-b", "project-a"), ("project-a", "project-b")]
)
def test_scope_mismatch_emits_no_consume_post(monkeypatch, project, marker):
    module, conn, client, events = _smoke(monkeypatch, project=project, marker=marker)
    with pytest.raises(RuntimeError, match="project|scope"):
        module.main()
    assert events == ["authenticate", "scope"]
    client.post.assert_not_called()
    client.delete.assert_not_called()
    conn.close.assert_called_once()


def test_authentication_failure_emits_no_consume_post(monkeypatch):
    module, conn, client, _events = _smoke(monkeypatch)
    conn.authorize.side_effect = RuntimeError("private-sdk-token")
    with pytest.raises(RuntimeError):
        module.main()
    conn.session.get_project_id.assert_not_called()
    client.post.assert_not_called()
    conn.close.assert_called_once()


def test_consume_post_carries_expected_project_after_authentication(monkeypatch):
    module, conn, client, events = _smoke(monkeypatch)
    metadata = {"readonly": "true", "afterglow_volume_type_name": "layers", "afterglow_size_bytes": "8"}
    consume = {
        "transport": "block",
        "project_id": "project-a",
        "run_id": "run-a",
        "status": "active",
        "server_id": "server-a",
        "cleanup_state": "active",
        "resources": [{"kind": "layer", "state": "active", "id": "volume-a", "metadata": metadata}],
    }
    response = MagicMock()
    response.json.return_value = {"consume_id": 7, "server_id": "server-a"}

    def post(*_args, **_kwargs):
        assert events == ["authenticate", "scope"]
        events.append("post")
        return response

    client.post.side_effect = post
    client.get.return_value.json.return_value = consume
    conn.block_storage.get_volume.return_value = SimpleNamespace(
        id="volume-a",
        project_id="project-a",
        metadata=metadata,
        volume_type="layers",
        size=1,
        is_multiattach=False,
        status="in-use",
        attachments=[{"server_id": "server-a"}],
    )
    module.main()
    assert events == ["authenticate", "scope", "post"]
    client.post.assert_called_once_with(
        "https://afterglow.example/api/v1/admin/libraries/consume",
        json={
            "transport": "block",
            "flavor_id": "flavor-a",
            "server_name": "smoke",
            "expected_project_id": "project-a",
            "import_id": 9,
        },
    )
    conn.close.assert_called_once()


def test_smoke_auth_failure_does_not_log_credentials(monkeypatch, capsys):
    _module, conn, client, _events = _smoke(monkeypatch)
    conn.authorize.side_effect = RuntimeError("private-sdk-token private-api-token")
    with pytest.raises(SystemExit) as failure:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert failure.value.code == 1
    output = capsys.readouterr()
    assert "Block smoke failed" in output.err
    assert "private-sdk-token" not in output.err
    assert "private-api-token" not in output.err
    client.post.assert_not_called()
