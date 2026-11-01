from keystone.common import sql
from sqlalchemy import event, text


def test_causal_barrier_does_not_escape_native_pool_request(native, subject, post):
    with sql.session_for_write() as session:
        before = int(session.execute(text("SELECT @@session.wsrep_sync_wait")).scalar_one())
        engine = session.get_bind()
    restored = []
    def checkout(dbapi_connection, record, proxy):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT @@session.wsrep_sync_wait")
            restored.append(int(cursor.fetchone()[0]))
        finally:
            cursor.close()
    assert post(subject).status_code == 204
    event.listen(engine, "checkout", checkout)
    try:
        with sql.session_for_write() as session:
            after = int(session.execute(text("SELECT @@session.wsrep_sync_wait")).scalar_one())
    finally:
        event.remove(engine, "checkout", checkout)
    assert restored and restored[-1] == before
    assert after == before


def test_post_dispatch_password_error_never_becomes_prewrite_422(native, subject, post):
    from keystone import exception
    with sql.session_for_write() as session:
        engine = session.get_bind()
    inserted = []
    def fail_after_real_insert(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO PASSWORD"):
            inserted.append(1)
            raise exception.PasswordValidationError(detail="Synthetic late-stage failure")
    event.listen(engine, "after_cursor_execute", fail_after_real_insert)
    try:
        response = post(subject)
    finally:
        event.remove(engine, "after_cursor_execute", fail_after_real_insert)
    assert inserted == [1]
    assert response.status_code != 422
