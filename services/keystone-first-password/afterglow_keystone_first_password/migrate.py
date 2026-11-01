"""Offline-only DDL. DSNs come from environment, never command arguments/logs.

Required environment: AFTERGLOW_PASSWORD_SCHEMA_URL (DDL principal),
AFTERGLOW_PASSWORD_WRITER_URL (restricted native principal),
AFTERGLOW_PASSWORD_AUDIT_URLS (JSON list, one restricted auditor per member),
AFTERGLOW_PASSWORD_CLUSTER_MEMBERS (JSON list of exact wsrep_node_name values).
All native writers MUST remain stopped until this command exits successfully.
DDL is not transactional: a failed application needs explicit offline recovery;
never resume a partially installed cluster or rerun blindly.
"""
import argparse
import json
import os
from contextlib import ExitStack

from sqlalchemy import create_engine, text

from . import CONF, GROUP, guarded_cluster, membership, prepare, schema, verify_build
from .schema import statements


def preflight(database, ddl_url, writer_url, audit_urls, members):
    """Read-only validation of every known prerequisite before first DDL.

    Writers and competing schema administrators must remain stopped throughout
    preflight, application and postflight. DDL failures after preflight are
    still nontransactional and require explicit offline recovery.
    """
    verify_build()
    if (not isinstance(audit_urls, list) or not isinstance(members, list) or
            not members or len(audit_urls) != len(members) or
            len(set(members)) != len(members) or
            any(not isinstance(member, str) or not member for member in members)):
        raise schema.Unsupported("Exact per-member audit endpoints and names required")
    with ExitStack() as stack:
        def connect(url):
            engine = create_engine(url, hide_parameters=True)
            stack.callback(engine.dispose)
            connection = stack.enter_context(engine.connect())
            stack.enter_context(connection.begin())
            prepare(connection)
            if connection.execute(text("SELECT DATABASE()")).scalar_one() != database:
                raise schema.Unsupported("Preflight endpoint does not select the explicit database")
            schema.validate_environment(connection)
            schema.validate_native_schema(connection)
            return connection
        writer = connect(writer_url)
        schema.validate_privileges(writer)
        ddl = connect(ddl_url)
        schema.validate_ddl_privileges(ddl)
        schema.validate_uninstalled(ddl)
        writer_identity = writer.execute(text("SELECT CURRENT_USER()")).scalar_one()
        audits = []
        for url in audit_urls:
            auditor = connect(url)
            schema.validate_privileges(auditor, auditor=True)
            schema.validate_uninstalled(auditor)
            if auditor.execute(text("SELECT CURRENT_USER()")).scalar_one() == writer_identity:
                raise schema.Unsupported("Audit and native credential writer identities must differ")
            audits.append(auditor)
        census = [membership(connection) for connection in audits]
        local = [membership(writer), membership(ddl)]
        if ({entry[0] for entry in census} != set(members) or
                any(entry[0] not in members for entry in local) or
                len({entry[1:] for entry in census + local}) != 1 or
                census[0][3] != len(members) or not census[0][1]):
            raise schema.Unsupported("Preflight Galera membership census is incomplete")
        # Detect membership movement during the potentially long reflection.
        if [membership(connection) for connection in audits] != census:
            raise schema.Unsupported("Galera membership changed during preflight")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-writers-stopped", required=True, action="store_true")
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply", action="store_true", help="Without this flag, validate only")
    args = parser.parse_args()
    audits = json.loads(os.environ["AFTERGLOW_PASSWORD_AUDIT_URLS"])
    members = json.loads(os.environ["AFTERGLOW_PASSWORD_CLUSTER_MEMBERS"])
    # No hidden production discovery or automatic credentials/grants.
    if args.apply:
        preflight(args.database, os.environ["AFTERGLOW_PASSWORD_SCHEMA_URL"],
                  os.environ["AFTERGLOW_PASSWORD_WRITER_URL"], audits, members)
        engine = create_engine(os.environ["AFTERGLOW_PASSWORD_SCHEMA_URL"], hide_parameters=True)
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                prepare(connection)
                if connection.execute(text("SELECT DATABASE()")).scalar_one() != args.database:
                    raise RuntimeError("Explicit database does not match schema connection")
                if connection.execute(text("SELECT @@session.wsrep_on")).scalar_one() != 1:
                    raise RuntimeError("Galera must be enabled during TOI installation")
                if connection.execute(text("SELECT @@session.wsrep_OSU_method")).scalar_one() != "TOI":
                    raise RuntimeError("Only TOI schema installation is permitted")
                for statement in statements():
                    connection.exec_driver_sql(statement)
        finally:
            engine.dispose()
    CONF.set_override("enabled", True, group=GROUP)
    CONF.set_override("service_user_id", "offline-schema-validation", group=GROUP)
    CONF.set_override("peer_connections", audits, group=GROUP)
    CONF.set_override("cluster_members", members, group=GROUP)
    engine = create_engine(os.environ["AFTERGLOW_PASSWORD_WRITER_URL"], hide_parameters=True)
    try:
        with engine.connect() as connection, connection.begin():
            if connection.execute(text("SELECT DATABASE()")).scalar_one() != args.database:
                raise RuntimeError("Explicit database does not match writer connection")

            # Adapter keeps the same connection for all local validation.
            class Session:
                def connection(self):
                    return connection

            with guarded_cluster(Session()) as check:
                check()
    finally:
        engine.dispose()
    print("Exact native schema and configured Galera membership validated; no credential written")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Schema installation/validation failed; keep every writer stopped and inspect offline without exposing DSNs") from None
