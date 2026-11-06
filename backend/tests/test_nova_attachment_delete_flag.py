"""Unknown Nova attachment policy must not be presented as retained storage."""

from types import SimpleNamespace

from app.services import nova


def test_missing_delete_policy_remains_unknown():
    attachment = SimpleNamespace(id="attachment", volume_id="volume", device="/dev/vda", server_id="server")
    conn = SimpleNamespace(compute=SimpleNamespace(volume_attachments=lambda _server: [attachment]))
    result = nova.list_volume_attachments(conn, "server")
    assert result[0]["delete_on_termination"] is None
