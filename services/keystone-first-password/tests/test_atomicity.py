from keystone.common import sql
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from test_native import password_rows


def test_native_insert_failure_rolls_back_marker_without_retry(native, subject, post, caplog):
    with sql.session_for_write() as session:
        engine = session.get_bind()
    attempts = []
    def lose_transaction(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO PASSWORD"):
            attempts.append(1)
            # Fault after REAL native INSERT+trigger execution, before commit.
            # The conditional branch must bypass Keystone's retry decorator.
            raise OperationalError("synthetic certification fault", None, RuntimeError("1213"))
    event.listen(engine, "after_cursor_execute", lose_transaction)
    secret = "No-retry-plaintext-password-924!"
    try:
        assert post(subject, password=secret).status_code == 503
    finally:
        event.remove(engine, "after_cursor_execute", lose_transaction)
    assert attempts == [1]
    assert password_rows(subject["id"]) == []
    fresh = native["providers"].identity_api.get_user(subject["id"])
    assert fresh.get("afterglow_local_password") is not True
    assert fresh["nested_metadata"] == {"preserve": [1, 2]}
    assert secret not in caplog.text


def test_stale_manager_snapshot_cannot_hide_native_password(native, subject, post):
    manager = native["providers"].identity_api
    manager.get_user(subject["id"])
    # Native driver write does not perform manager cache invalidation, just as
    # a different loaded writer can commit independently of this process.
    _, driver, entity_id = manager._get_domain_driver_and_entity_id(subject["id"])
    driver.update_user(entity_id, {"password": "Independent-native-password-338!"})
    before = password_rows(subject["id"])
    assert post(subject).status_code == 409
    assert password_rows(subject["id"]) == before
