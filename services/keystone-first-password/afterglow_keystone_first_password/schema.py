"""Strict, transaction-local prerequisites. This module never logs DB exceptions."""
import re
from importlib.resources import files

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

REVISION = "first-password-galera-v1"
TABLES = ("user", "local_user", "password", "federated_user", "identity_provider", "federation_protocol", "mapping", "idp_remote_ids", "afterglow_password_guard")
NATIVE_TABLES = TABLES[:-1]


class Unsupported(RuntimeError):
    pass


def statements():
    source = files(__package__).joinpath("schema.sql").read_text()
    chunks = source.split("-- afterglow-statement")
    first = re.sub(r"--[^\n]*", "", chunks.pop(0))
    return [s.strip() for s in first.split(";") if s.strip()] + [
        s.strip().rstrip(";") for s in chunks
    ]


def canonical(body):
    # Whitespace alone is insignificant; quoted contents, operators and case
    # are deliberately not normalized. Unexpected server rewrites fail closed.
    return re.sub(r"('(?:''|[^'])*')|(\s+)", lambda match: match[1] if match[1] is not None else " ", body.strip().rstrip(";")).strip()


def expected_objects():
    objects = {}
    for statement in statements():
        if statement.startswith("CREATE TRIGGER"):
            head, body = statement.split("\n", 1)
            words = head.split()
            objects[words[2]] = ("TRIGGER", words[6].strip("`"), words[4], canonical(body))
    return objects


def validate_environment(connection):
    if connection.dialect.name != "mysql":
        raise Unsupported("Only pinned MariaDB InnoDB is supported")
    version = connection.execute(text("SELECT VERSION()")).scalar_one()
    if not re.match(r"10\.11\.19-MariaDB(?:-|$)", version):
        raise Unsupported("Unqualified MariaDB version")
    variables = dict(connection.execute(text(
        "SHOW SESSION VARIABLES WHERE Variable_name IN "
        "('tx_isolation','wsrep_on','wsrep_sync_wait','wsrep_OSU_method','wsrep_retry_autocommit','foreign_key_checks')"
    )).all())
    variables = {k.lower(): str(v) for k, v in variables.items()}
    if variables.get("tx_isolation") != "REPEATABLE-READ":
        raise Unsupported("Unexpected transaction isolation")
    if variables.get("wsrep_on") != "ON" or variables.get("wsrep_sync_wait") != "15":
        raise Unsupported("Galera with a causal read barrier is required")
    if variables.get("foreign_key_checks") != "ON":
        raise Unsupported("Native foreign key checks must be enabled")
    if variables.get("wsrep_osu_method") != "TOI" or variables.get("wsrep_retry_autocommit") != "0":
        raise Unsupported("Galera requires TOI and no autocommit replay")
    status = dict(connection.execute(text("SHOW GLOBAL STATUS LIKE 'wsrep_%'")).all())
    if (status.get("wsrep_cluster_status") != "Primary" or
            status.get("wsrep_ready") != "ON" or
            status.get("wsrep_connected") != "ON" or
            status.get("wsrep_local_state_comment") != "Synced"):
        raise Unsupported("Galera is not writable and synchronized")
    return variables


def validate_native_schema(connection):
    for table in NATIVE_TABLES:
        connection.execute(text(f"SELECT * FROM `{table}` LIMIT 0"))
    engines = dict(connection.execute(text(
        "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
        "('user','local_user','password','federated_user','identity_provider','federation_protocol','mapping','idp_remote_ids')"
    )).all())
    if engines != dict.fromkeys(NATIVE_TABLES, "InnoDB"):
        raise Unsupported("Native tables must all be InnoDB")
    inspector = inspect(connection)
    from keystone.federation.backends import sql as federation
    from keystone.identity.backends import sql_model as model
    tables = (model.User.__table__, model.LocalUser.__table__, model.Password.__table__, model.FederatedUser.__table__, federation.IdentityProviderModel.__table__, federation.FederationProtocolModel.__table__, federation.MappingModel.__table__, federation.IdPRemoteIdsModel.__table__)
    for table in tables:
        actual = {c["name"]: c for c in inspector.get_columns(table.name)}
        if set(actual) != set(table.columns.keys()):
            raise Unsupported("Unexpected native schema columns")
        for column in table.columns:
            current = actual[column.name]
            if current["nullable"] != column.nullable:
                raise Unsupported("Unexpected native column nullability")
            # Compile through the same MariaDB dialect; accept BOOLEAN's
            # native TINYINT(1) representation, never an arbitrary type.
            def native_type(value):
                value = value.compile(dialect=connection.dialect).upper().replace("INTEGER", "INT")
                value = re.sub(r"\b(INT|BIGINT)\(\d+\)", r"\1", value)
                return "TINYINT(1)" if value in ("BOOL", "BOOLEAN") else value
            wanted = native_type(column.type)
            found = native_type(current["type"])
            if wanted != found:
                raise Unsupported("Unexpected native column type")
            if current.get("computed") or current.get("identity"):
                raise Unsupported("Unexpected native generated column")
        if inspector.get_pk_constraint(table.name)["constrained_columns"] != [c.name for c in table.primary_key.columns]:
            raise Unsupported("Unexpected native primary key")
    for table, unique in (("local_user", {("user_id",), ("domain_id", "name")}), ("user", {("id", "domain_id")})):
        actual_unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(table)}
        if actual_unique != unique:
            raise Unsupported("Unexpected native unique constraints")
    database = connection.execute(text("SELECT DATABASE()")).scalar_one()
    for table in tables:
        expected_fks = set()
        for fk in table.foreign_key_constraints:
            expected_fks.add((tuple(e.parent.name for e in fk.elements), tuple(e.column.name for e in fk.elements), fk.referred_table.name, fk.ondelete or "RESTRICT", fk.onupdate or "RESTRICT"))
        actual_fks = set()
        for fk in inspector.get_foreign_keys(table.name):
            if fk.get("referred_schema") not in (None, database):
                raise Unsupported("Native foreign key points outside the identity database")
            actual_fks.add((tuple(fk["constrained_columns"]), tuple(fk["referred_columns"]), fk["referred_table"], fk["options"].get("ondelete", "RESTRICT"), fk["options"].get("onupdate", "RESTRICT")))
        if actual_fks != expected_fks:
            raise Unsupported("Native cascade relationships differ from the pin")


def validate(session, auditor=False):
    connection = session if isinstance(session, Connection) else session.connection()
    variables = validate_environment(connection)
    validate_native_schema(connection)
    validate_privileges(connection, auditor=auditor)
    connection.execute(text("SELECT * FROM afterglow_password_guard LIMIT 0"))
    engine = connection.execute(text("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='afterglow_password_guard'")).scalar_one_or_none()
    if engine != "InnoDB":
        raise Unsupported("Certification guard must be InnoDB")
    inspector = inspect(connection)
    guard = inspector.get_columns("afterglow_password_guard")
    if [(c["name"], re.sub(r"\(\d+\)", "", str(c["type"]).upper()) if c["name"] == "revision" else str(c["type"]).upper(), c["nullable"]) for c in guard] != [("user_id", "VARCHAR(64)", False), ("revision", "BIGINT", False)] or not getattr(guard[1]["type"], "unsigned", False):
        raise Unsupported("Unexpected certification guard schema")
    if any(c.get("computed") or c.get("identity") for c in guard) or str(guard[1].get("default")).strip("'") != "0":
        raise Unsupported("Unexpected guard generation/default")
    if (inspector.get_pk_constraint("afterglow_password_guard")["constrained_columns"] != ["user_id"] or inspector.get_foreign_keys("afterglow_password_guard")):
        raise Unsupported("Guard must be persistent and primary-key certified")
    if auditor:
        actual = connection.execute(text(
            "SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT "
            "FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() "
            "AND EVENT_OBJECT_TABLE IN ('user','local_user','password','federated_user','identity_provider','federation_protocol','mapping','idp_remote_ids','afterglow_password_guard')"
        )).all()
        expected = expected_objects()
        triggers = {name: ("TRIGGER", table, event, canonical(body))
                    for name, table, event, timing, body in actual if timing == "BEFORE"}
        if len(actual) != len(triggers) or triggers != expected:
            raise Unsupported("Native password certification triggers differ")
    missing = connection.execute(text(
        "SELECT u.id FROM `user` u LEFT JOIN afterglow_password_guard g ON g.user_id=u.id "
        "WHERE g.user_id IS NULL LIMIT 1"
    )).first()
    if missing:
        raise Unsupported("Native subjects are missing certification guards")
    return variables.get("wsrep_on") == "ON"


def grants(connection, allow_grant_option=False):
    result = []
    for grant, in connection.execute(text("SHOW GRANTS FOR CURRENT_USER")):
        if " ON " not in grant or (" WITH GRANT OPTION" in grant.upper() and not allow_grant_option):
            raise Unsupported("Unqualified role or grant-option privilege")
        privileges, rest = grant.removeprefix("GRANT ").split(" ON ", 1)
        scope = rest.split(" TO ", 1)[0]
        result.append((set(privileges.upper().split(", ")), scope))
    return result


def effective_privileges(parsed, database, table):
    result = set()
    for privileges, scope in parsed:
        if scope in ("*.*", f"`{database}`.*", f"`{database}`.`{table}`"):
            result.update(privileges)
    return result


def validate_privileges(connection, auditor=False):
    parsed = grants(connection)
    allowed = {"SELECT", "TRIGGER", "USAGE"} if auditor else {"SELECT", "INSERT", "UPDATE", "DELETE", "USAGE"}
    if any(not privileges <= allowed for privileges, _ in parsed):
        raise Unsupported("DB principal exceeds its exact privilege allowlist")
    database = connection.execute(text("SELECT DATABASE()")).scalar_one()
    required = {"SELECT", "TRIGGER"} if auditor else {"SELECT", "INSERT", "UPDATE", "DELETE"}
    for table in TABLES:
        needed = required if auditor or table != "afterglow_password_guard" else {"SELECT", "UPDATE"}
        if not needed <= effective_privileges(parsed, database, table):
            raise Unsupported("DB principal lacks required explicit native table privileges")


def validate_ddl_privileges(connection):
    parsed = grants(connection, allow_grant_option=True)
    database = connection.execute(text("SELECT DATABASE()")).scalar_one()
    required = {"SELECT", "INSERT", "UPDATE", "CREATE", "TRIGGER"}
    for table in TABLES:
        actual = effective_privileges(parsed, database, table)
        if "ALL PRIVILEGES" not in actual and not required <= actual:
            raise Unsupported("Offline DDL principal lacks schema/trigger-definer privileges")
    trust = connection.execute(text("SELECT @@global.log_bin_trust_function_creators")).scalar_one()
    global_privileges = set().union(*(privileges for privileges, scope in parsed if scope == "*.*"))
    if str(trust).upper() not in ("1", "ON") and not ({"SUPER", "ALL PRIVILEGES"} & global_privileges):
        raise Unsupported("MariaDB trigger creation requires SUPER or trusted function creators")


def validate_uninstalled(connection):
    inspector = inspect(connection)
    if inspector.has_table("afterglow_password_guard"):
        raise Unsupported("A prior or partial guard installation requires offline operator recovery")
    triggers = connection.execute(text("SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE IN ('user','local_user','password','federated_user','identity_provider','federation_protocol','mapping','idp_remote_ids')")).all()
    if triggers:
        raise Unsupported("Native tables already contain triggers; offline operator review required")
