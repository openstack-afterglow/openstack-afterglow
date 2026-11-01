"""Races use native Keystone ORM writes on real node B, never fake SQL tables.

AFTERGLOW_KEYSTONE_TEST_CONFIG_B points to the same native config except the
restricted database writer URL selects Galera node B. SQL metadata and triggers
must already be installed on both nodes. Each child imports real Keystone.
"""
import multiprocessing
import os
import sys
import threading
import uuid

import pytest
from keystone.common import password_hashing, sql
from sqlalchemy import event, text
from test_identity_revision import proof
from test_native import password_rows


def federate(native, subject):
    providers = native["providers"]
    idp, mapping = "race-idp-" + uuid.uuid4().hex, "race-map-" + uuid.uuid4().hex
    providers.federation_api.create_mapping(mapping, {"rules": []})
    providers.federation_api.create_idp(idp, {"id": idp, "domain_id": native["domain"], "enabled": True, "remote_ids": []})
    providers.federation_api.create_protocol(idp, "openid", {"mapping_id": mapping})
    providers.shadow_users_api.create_federated_object({"user_id": subject["id"], "idp_id": idp, "protocol_id": "openid", "unique_id": uuid.uuid4().hex, "display_name": subject["name"]})


def mysql_error_code(error):
    current, seen = error, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "args", ()) and isinstance(current.args[0], int):
            return current.args[0]
        current = getattr(current, "orig", None) or getattr(current, "inner_exception", None) or current.__cause__ or current.__context__
    return None


def serialized_retry(trace):
    targets = [(index, entry["transaction"]) for index, entry in enumerate(trace) if entry["phase"] == "target_enter"]
    if len({transaction for _, transaction in targets}) < 2:
        return False
    _, first = targets[0]
    last_target, last = targets[-1]
    failures = [index for index, entry in enumerate(trace) if entry["transaction"] == first and entry["phase"] in ("dbapi_commit_failed", "sql_error") and entry.get("errno") == 1213]
    rollbacks = [index for index, entry in enumerate(trace) if entry["transaction"] == first and entry["phase"] == "dbapi_rollback"]
    commits = [index for index, entry in enumerate(trace) if entry["transaction"] == last and entry["phase"] == "dbapi_commit_succeeded"]
    returned = [index for index, entry in enumerate(trace) if entry["phase"] == "native_return_succeeded"]
    first_committed = any(entry["transaction"] == first and entry["phase"] == "dbapi_commit_succeeded" for entry in trace)
    return (not first_committed and bool(failures and rollbacks and commits and returned) and
            failures[0] < rollbacks[-1] < last_target < commits[-1] < returned[-1])


def native_writer(config, user_id, operation, attempted, applied, release, finished, result):
    # Side-effect import: registers the extension's config group before server.configure() parses it.
    import afterglow_keystone_first_password  # noqa: F401
    from keystone import server
    from keystone.common import provider_api, sql
    argv = sys.argv
    try:
        sys.argv = argv[:1]
        server.configure(config_files=[config])
    finally:
        sys.argv = argv
    server.setup_backends()
    with sql.session_for_write() as session:
        engine = session.get_bind()
    trace, sequence = [], [0]
    def record(phase, transaction, error=None):
        import time
        trace.append({"phase": phase, "transaction": transaction, "errno": mysql_error_code(error) if error is not None else None, "at_ns": time.monotonic_ns()})
    def begin(connection):
        sequence[0] += 1
        connection.info["afterglow_test_transaction"] = sequence[0]
        record("begin", sequence[0])
    def checkout(dbapi, connection_record, proxy):
        if connection_record.info.get("afterglow_test_commit_wrapped"):
            return
        connection_record.info["afterglow_test_commit_wrapped"] = True
        commit, rollback = dbapi.commit, dbapi.rollback
        def commit_observed():
            transaction = connection_record.info.get("afterglow_test_transaction")
            record("dbapi_commit_attempt", transaction)
            try:
                answer = commit()
            except Exception as error:
                record("dbapi_commit_failed", transaction, error)
                raise
            record("dbapi_commit_succeeded", transaction)
            return answer
        def rollback_observed():
            record("dbapi_rollback", connection_record.info.get("afterglow_test_transaction"))
            return rollback()
        dbapi.commit, dbapi.rollback = commit_observed, rollback_observed
    def failed(context):
        transaction = context.connection.info.get("afterglow_test_transaction") if context.connection is not None else None
        record("sql_error", transaction, context.original_exception)
    event.listen(engine, "begin", begin)
    event.listen(engine, "checkout", checkout)
    event.listen(engine, "handle_error", failed)
    paused = False
    relevant = {"password": r"INSERT INTO PASSWORD\b", "delete": r"DELETE FROM USER\b(?!_)", "delete_once": r"DELETE FROM USER\b(?!_)", "disable": r"UPDATE USER\b(?!_)", "email": r"UPDATE USER\b(?!_)", "protocol": r"UPDATE FEDERATION_PROTOCOL\b"}[operation]
    def matches(statement):
        # Exact guarded table only; user_option/user_group_membership rows do not certify the user guard.
        import re
        return re.match(relevant, statement.lstrip().upper().replace("`", "")) is not None
    def enter(connection, cursor, statement, parameters, context, many):
        if matches(statement):
            record("target_enter", connection.info.get("afterglow_test_transaction"))
            attempted.set()
    def pause(connection, cursor, statement, parameters, context, many):
        nonlocal paused
        if matches(statement):
            record("target_applied", connection.info.get("afterglow_test_transaction"))
            if not paused:
                paused = True
                applied.set()
                if not release.wait(30):
                    raise RuntimeError("Native race release timeout")
    event.listen(engine, "before_cursor_execute", enter)
    event.listen(engine, "after_cursor_execute", pause)
    manager = provider_api.ProviderAPIs.identity_api
    try:
        if operation == "password":
            manager.update_user(user_id, {"password": "Competing-native-password-602!"})
        elif operation == "delete":
            manager.delete_user(user_id)
        elif operation == "delete_once":
            _, driver, entity_id = manager._get_domain_driver_and_entity_id(user_id)
            driver.delete_user.__wrapped__(driver, entity_id)
        elif operation == "disable":
            manager.update_user(user_id, {"enabled": False})
        elif operation == "email":
            manager.update_user(user_id, {"email": "changed-during-proof@example.invalid"})
        else:
            with sql.session_for_read() as session:
                link = session.execute(text("SELECT f.idp_id,f.protocol_id,p.mapping_id FROM federated_user f JOIN federation_protocol p ON p.idp_id=f.idp_id AND p.id=f.protocol_id WHERE f.user_id=:id"), {"id": user_id}).one()
            provider_api.ProviderAPIs.federation_api.update_protocol(link.idp_id, link.protocol_id, {"mapping_id": link.mapping_id, "remote_id_attribute": "changed-during-proof"})
        record("native_return_succeeded", None)
        result.put(("committed", None, list(trace)))
    except Exception as error:
        result.put(("aborted", mysql_error_code(error), list(trace)))
    finally:
        # Never set attempted/applied here. Early child failure is NOT a race.
        finished.set()


@pytest.mark.parametrize("operation", ["password", "delete", "delete_once", "disable", "email", "protocol"])
def test_native_uncommitted_first_cannot_escape_certification(native, subject, post, operation):
    if operation == "protocol":
        federate(native, subject)
    context = multiprocessing.get_context("spawn")
    attempted, applied, release, finished = (context.Event() for _ in range(4))
    result = context.Queue()
    binding = proof(native, subject)
    child = context.Process(target=native_writer, args=(os.environ["AFTERGLOW_KEYSTONE_TEST_CONFIG_B"], subject["id"], operation, attempted, applied, release, finished, result))
    with sql.session_for_write() as session:
        engine = session.get_bind()
    conditional_attempts, local_deadlocks = [], []
    def enter(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("UPDATE AFTERGLOW_PASSWORD_GUARD"):
            conditional_attempts.append(1)
    def failed(context):
        if context.original_exception.args[0] == 1213:
            local_deadlocks.append(1)
    event.listen(engine, "before_cursor_execute", enter)
    event.listen(engine, "handle_error", failed)
    child.start()
    try:
        assert applied.wait(30), "Node B never executed its target SQL/guard trigger"
        assert attempted.is_set() and not finished.is_set()
        response = post(subject, proof=binding)
    finally:
        release.set()
        child.join(35)
        event.remove(engine, "before_cursor_execute", enter)
        event.remove(engine, "handle_error", failed)
        if child.is_alive():
            child.terminate()
            child.join()
    assert child.exitcode == 0 and finished.is_set()
    assert conditional_attempts == [1], "Conditional transaction never attempted the shared guard"
    outcome, error_code, trace = result.get(timeout=5)
    import json
    print("native-first-race " + json.dumps({"operation": operation, "response": response.status_code, "outcome": outcome, "trace": trace}, sort_keys=True))
    rows = password_rows(subject["id"])
    if response.status_code == 204:
        first = next(entry["transaction"] for entry in trace if entry["phase"] == "target_enter")
        assert any(entry["transaction"] == first and entry["phase"] in ("dbapi_commit_failed", "sql_error") and entry.get("errno") == 1213 for entry in trace), trace
        assert not any(entry["transaction"] == first and entry["phase"] == "dbapi_commit_succeeded" for entry in trace), trace
        if outcome == "committed":
            assert serialized_retry(trace), "Both API outcomes succeeded without observed failed first transaction and separately committed retry: " + repr(trace)
            if operation in ("delete", "delete_once"):
                assert rows == []
            elif operation == "password":
                assert any(password_hashing.check_password("Competing-native-password-602!", row.password_hash) for row in rows)
            else:
                assert len(rows) == 1
                assert password_hashing.check_password("Synthetic-first-password-482!", rows[0].password_hash)
        else:
            assert error_code == 1213
            assert len(rows) == 1
            assert password_hashing.check_password("Synthetic-first-password-482!", rows[0].password_hash)
            if operation == "delete_once":
                targets = [entry for entry in trace if entry["phase"] == "target_enter"]
                assert len(targets) == 1, trace
                with sql.session_for_write() as session:
                    assert session.execute(text("SELECT id FROM `user` WHERE id=:id"), {"id": subject["id"]}).scalar_one() == subject["id"]
    else:
        assert response.status_code == 503 and local_deadlocks
        assert outcome == "committed", trace
        if operation == "password":
            assert len(rows) == 1
            assert password_hashing.check_password("Competing-native-password-602!", rows[0].password_hash)
        else:
            assert rows == []


@pytest.mark.parametrize("operation", ["password", "email", "protocol"])
def test_creator_uncommitted_first_native_writer_certifies(native, subject, post, monkeypatch, operation):
    if operation == "protocol":
        federate(native, subject)
    import afterglow_keystone_first_password as extension
    ready, release = threading.Event(), threading.Event()
    real_check = extension.membership
    first_flush = threading.Event()
    with sql.session_for_write() as session:
        engine = session.get_bind()
    def mark_flush(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO PASSWORD"):
            first_flush.set()
    import sys as _sys

    from afterglow_keystone_first_password import api as extension_api
    swallowed = []
    real_unavailable = extension_api.unavailable
    def recording_unavailable():
        error = _sys.exc_info()[1]
        chain, current = [], error
        while current is not None and len(chain) < 6:
            chain.append((type(current).__name__, mysql_error_code(current), str(current)[:120] if type(current).__module__.startswith("afterglow") else None))
            current = getattr(current, "orig", None) or current.__cause__ or current.__context__
        swallowed.append(chain)
        return real_unavailable()
    monkeypatch.setattr(extension_api, "unavailable", recording_unavailable)
    creator_errors, peer_errors = [], []
    def failed(context):
        creator_errors.append(mysql_error_code(context.original_exception))
    def peer_failed(context):
        peer_errors.append(mysql_error_code(context.original_exception))
    # guarded_cluster uses separate peer engines. Listen there too so the source of errno 1213 is recorded;
    # observed runs only ever saw it in the exception swallowed by unavailable(), not on these hooks.
    real_peer_engine = extension.peer_engine
    watched_peers = set()
    def watching_peer_engine(url):
        peer = real_peer_engine(url)
        if id(peer) not in watched_peers:
            watched_peers.add(id(peer))
            event.listen(peer, "handle_error", peer_failed)
        return peer
    monkeypatch.setattr(extension, "peer_engine", watching_peer_engine)
    event.listen(engine, "after_cursor_execute", mark_flush)
    event.listen(engine, "handle_error", failed)
    def pause_check(connection):
        if first_flush.is_set() and not ready.is_set():
            ready.set()
            assert release.wait(30)
        return real_check(connection)
    monkeypatch.setattr(extension, "membership", pause_check)
    response = []
    binding = proof(native, subject)
    creator = threading.Thread(target=lambda: response.append(post(subject, proof=binding)))
    context = multiprocessing.get_context("spawn")
    attempted, applied, other_release, finished = (context.Event() for _ in range(4))
    result = context.Queue()
    child = context.Process(target=native_writer, args=(os.environ["AFTERGLOW_KEYSTONE_TEST_CONFIG_B"], subject["id"], operation, attempted, applied, other_release, finished, result))
    creator.start()
    try:
        assert ready.wait(30), "Conditional creator never executed its real INSERT and shared guard"
        child.start()
        assert attempted.wait(30), "Native node B never attempted its target SQL"
        other_release.set()
        assert finished.wait(35), "Native overlapping transaction did not finish"
        child.join(5)
    finally:
        release.set()
        creator.join(35)
        event.remove(engine, "after_cursor_execute", mark_flush)
        event.remove(engine, "handle_error", failed)
        for peer_url in list(extension.CONF[extension.GROUP].peer_connections):
            try:
                event.remove(real_peer_engine(peer_url), "handle_error", peer_failed)
            except Exception:
                pass
        if child.pid is not None and child.is_alive():
            child.terminate()
            child.join()
    assert not creator.is_alive() and child.exitcode == 0
    outcome, error_code, trace = result.get(timeout=5)
    import json
    print("creator-first-race " + json.dumps({"operation": operation, "response": response[0].status_code if response else None, "outcome": outcome, "trace": trace}, sort_keys=True))
    assert response
    both_success = response[0].status_code == 204 and outcome == "committed"
    if both_success:
        assert serialized_retry(trace), "Both API outcomes succeeded without an observed failed first transaction and committed retry: " + repr(trace)
    else:
        assert (response[0].status_code == 204) != (outcome == "committed"), trace
    rows = password_rows(subject["id"])
    if outcome == "committed":
        assert applied.is_set()
        if not both_success:
            assert response[0].status_code == 503, response[0].status_code
            # Positive evidence only: a 503 from a precondition failure (census, membership,
            # federation) is not a Galera abort. Record WHICH source supplied errno 1213.
            sources = {
                "swallowed_chain": any(entry[1] == 1213 for chain in swallowed for entry in chain),
                "creator_engine": 1213 in creator_errors,
                "peer_engine": 1213 in peer_errors,
            }
            print("errno1213-source " + json.dumps({"operation": operation, **sources}, sort_keys=True))
            assert any(sources.values()), "no errno 1213 evidence; creator " + repr(creator_errors) + "; peer " + repr(peer_errors) + "; swallowed " + repr(swallowed)
        if operation == "password":
            assert len(rows) == 1
            assert password_hashing.check_password("Competing-native-password-602!", rows[0].password_hash)
        elif both_success:
            assert len(rows) == 1
            assert password_hashing.check_password("Synthetic-first-password-482!", rows[0].password_hash)
        else:
            assert rows == []
    else:
        assert error_code == 1213
        assert response[0].status_code == 204
        assert len(rows) == 1
        assert password_hashing.check_password("Synthetic-first-password-482!", rows[0].password_hash)


def test_native_password_update_delete_and_local_delete_touch_same_guard(native, subject):
    def revision():
        with sql.session_for_write() as session:
            return session.execute(text("SELECT revision FROM afterglow_password_guard WHERE user_id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one()
    before = revision()
    native["providers"].identity_api.update_user(subject["id"], {"password": "Native-password-287!"})
    after_insert = revision()
    assert after_insert > before
    with sql.session_for_write() as session:
        session.execute(text("UPDATE password p JOIN local_user l ON l.id=p.local_user_id SET p.expires_at_int=1 WHERE l.user_id=:id"), {"id": subject["id"]})
    after_update = revision()
    assert after_update > after_insert
    with sql.session_for_write() as session:
        session.execute(text("DELETE p FROM password p JOIN local_user l ON l.id=p.local_user_id WHERE l.user_id=:id"), {"id": subject["id"]})
    assert revision() > after_update
    before_delete = revision()
    native["providers"].identity_api.delete_user(subject["id"])
    assert revision() > before_delete


def test_failed_auth_counter_does_not_touch_guard(native, subject):
    with sql.session_for_write() as session:
        before = session.execute(text("SELECT revision FROM afterglow_password_guard WHERE user_id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one()
        session.execute(text("UPDATE local_user SET failed_auth_count=COALESCE(failed_auth_count,0)+1 WHERE user_id=:id"), {"id": subject["id"]})
        after = session.execute(text("SELECT revision FROM afterglow_password_guard WHERE user_id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one()
    assert before == after
