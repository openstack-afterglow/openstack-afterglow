import os

import afterglow_keystone_first_password as extension
import pytest
from afterglow_keystone_first_password import schema
from sqlalchemy import create_engine
from test_native import password_rows


@pytest.mark.parametrize("name", ["afterglow_password_insert", "afterglow_password_update", "afterglow_password_delete", "afterglow_local_delete", "afterglow_user_update", "afterglow_user_delete"])
def test_exact_trigger_body_required_on_every_member(native, subject, post, name):
    original = next(s for s in schema.statements() if s.startswith("CREATE TRIGGER " + name + " "))
    changed = original.replace("revision = revision + 1", "revision = revision + 2")
    assert original != changed
    engine = create_engine(os.environ["AFTERGLOW_PASSWORD_SCHEMA_URL"], hide_parameters=True)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql("DROP TRIGGER " + name)
            connection.exec_driver_sql(changed)
        assert post(subject).status_code == 503
        assert password_rows(subject["id"]) == []
    finally:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql("DROP TRIGGER " + name)
            connection.exec_driver_sql(original)
        engine.dispose()


def test_disabled_native_prerequisite_has_no_success(native, subject, post):
    extension.CONF.set_override("enabled", False, group=extension.GROUP)
    try:
        assert post(subject).status_code == 503
        assert password_rows(subject["id"]) == []
    finally:
        extension.CONF.set_override("enabled", True, group=extension.GROUP)


def test_missing_peer_census_fails_closed(native, subject, post):
    peers = list(extension.CONF[extension.GROUP].peer_connections)
    extension.CONF.set_override("peer_connections", peers[:1], group=extension.GROUP)
    try:
        assert post(subject).status_code == 503
        assert password_rows(subject["id"]) == []
    finally:
        extension.CONF.set_override("peer_connections", peers, group=extension.GROUP)


def test_native_bypass_session_fails_inside_unmodified_writer(native, subject):
    from keystone.common import sql
    from sqlalchemy import event
    with sql.session_for_write() as session:
        engine = session.get_bind()
    def disable_checks(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO PASSWORD"):
            cursor.execute("SET SESSION foreign_key_checks=0")
    event.listen(engine, "before_cursor_execute", disable_checks)
    try:
        # The wrapper type of the trigger's SIGNAL 45000 is not part of the contract; the
        # property under test is that no credential row is written (asserted below).
        with pytest.raises(Exception):  # noqa: B017
            native["providers"].identity_api.update_user(subject["id"], {"password": "Must-not-be-written-702!"})
    finally:
        event.remove(engine, "before_cursor_execute", disable_checks)
        # Dispose poisoned session settings, not an ambiguous credential retry.
        engine.dispose()
    assert password_rows(subject["id"]) == []


def test_schema_writer_credentials_not_accepted_as_runtime(native, subject, post, monkeypatch):
    # Real grants, not a permissive mock: inject a DDL connection only into the
    # local validator and require its concrete SHOW GRANTS to be rejected.
    engine = create_engine(os.environ["AFTERGLOW_PASSWORD_SCHEMA_URL"], hide_parameters=True)
    with engine.begin() as connection:
        extension.prepare(connection)
        with pytest.raises(schema.Unsupported):
            schema.validate(connection)
    engine.dispose()
