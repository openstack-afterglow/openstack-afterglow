"""Explicit, digest-pinned native federation; Keystone owns users and grants.

Only operator registry providers with native_mapping opt-in use this path. Native
configuration is read back, never rewritten, and normal account entry is unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from string import Formatter
from types import SimpleNamespace
from urllib.parse import quote

MODE = "ephemeral"


def _field(value, name, default=None):
    from app.services.identity_roles import _field as field

    return field(value, name, default)


def _require(value, message):
    from app.services.domain_auth import DomainAuthUnavailable

    if not value:
        raise DomainAuthUnavailable(message, code="native_mapping_unsafe")


@dataclass(frozen=True)
class NativeMapping:
    provider_id: str
    issuer: str
    client_id: str
    idp_id: str
    protocol_id: str
    mapping_id: str
    sha256: str
    account_domain_id: str
    personal_domain_id: str
    project_template: str = ""


def _configured():
    """Trusted registry only, without discovery or implicit provider enrollment."""
    from app.services import domain_auth as svc

    auth = getattr(svc.get_settings(), "auth", None)
    for key, provider in getattr(auth, "providers", {}).items():
        pin = getattr(provider, "native_mapping", None)
        if (
            not provider.enabled
            or pin is None
            or pin.mode != MODE
            or provider.kind != "oidc"
            or provider.federation_token_type != "id_token"
            or getattr(provider, "organization", None) is not None
        ):
            continue
        yield NativeMapping(
            provider_id=svc._CONFIG_PROVIDER_PREFIX + key,
            issuer=provider.issuer_url,
            client_id=provider.client_id,
            idp_id=provider.keystone_idp_id,
            protocol_id=provider.keystone_protocol_id,
            mapping_id=pin.mapping_id,
            sha256=pin.sha256,
            account_domain_id=pin.account_domain_id,
            personal_domain_id=pin.personal_domain_id,
        )


def configured(row):
    """Return this exact opted-in registry descriptor, never a SQL provider."""
    pin = getattr(row, "_native_mapping", None)
    if pin is None:
        return None
    for descriptor in _configured():
        if (
            row.id == descriptor.provider_id
            and row.kind == "oidc"
            and row.issuer_url == descriptor.issuer
            and row.client_id == descriptor.client_id
            and row.keystone_idp_id == descriptor.idp_id
            and row.keystone_protocol_id == descriptor.protocol_id
            and row.federation_token_type == "id_token"
            and getattr(row, "_organization", None) is None
            and pin.mode == MODE
            and pin.mapping_id == descriptor.mapping_id
            and pin.sha256 == descriptor.sha256
            and pin.account_domain_id == descriptor.account_domain_id
            and pin.personal_domain_id == descriptor.personal_domain_id
        ):
            return descriptor
    _require(False, "Native provider configuration changed")


def mapping_matches(mapping, descriptor):
    document = {key: _field(mapping, key) for key in ("schema_version", "rules")}
    try:
        digest = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    except (TypeError, ValueError):
        return False
    return (
        _field(mapping, "id") == descriptor.mapping_id
        and document["schema_version"] == "2.0"
        and digest == descriptor.sha256
    )


def _project_template(mapping, descriptor):
    """Extract the single Personal template from the already pinned full mapping."""
    templates = []
    for rule in _field(mapping, "rules", []):
        for local in rule.get("local", []):
            projects = [
                p for p in local.get("projects", []) if p.get("domain", {}).get("id") == descriptor.personal_domain_id
            ]
            if not projects:
                continue
            user = local.get("user", {})
            _require(
                len(projects) == 1
                and user.get("type") == "ephemeral"
                and user.get("domain", {}).get("id") == descriptor.account_domain_id,
                "Native Personal mapping is unavailable",
            )
            template = projects[0].get("name")
            try:
                fields = [
                    (name, spec, conversion)
                    for _, name, spec, conversion in Formatter().parse(template)
                    if name is not None
                ]
            except (TypeError, ValueError):
                fields = []
            _require(
                len(fields) == 1 and fields[0][0].isdigit() and not fields[0][1] and fields[0][2] is None,
                "Native Personal project template is invalid",
            )
            position = int(fields[0][0])
            placeholder = "{" + str(position) + "}"
            literals = template.replace(placeholder, "", 1)
            _require(
                "{" not in literals and "}" not in literals,
                "Native Personal project template contains extra placeholders",
            )
            remote = rule.get("remote", [])
            _require(
                position < len(remote)
                and all(isinstance(value, dict) and set(value) == {"type"} for value in remote[:position])
                and remote[position] == {"type": "OIDC-preferred_username"}
                and user.get("name") == "{" + str(position) + "}"
                and projects[0].get("roles") == [{"name": "member"}],
                "Native Personal mapping must use the signed username and member role",
            )
            # Normalize the mapping's numbered username placeholder for safe formatting.
            templates.append(template.replace("{" + str(position) + "}", "{0}"))
    _require(len(templates) == 1, "Native Personal project template is ambiguous")
    return templates[0]


def _protocol_rows(ks, descriptor):
    protocols = ks.federation.protocols.list(descriptor.idp_id)
    links = getattr(protocols, "links", {})
    _require(
        not getattr(protocols, "next", None)
        and not getattr(protocols, "truncated", False)
        and not getattr(protocols, "limited", False)
        and not (isinstance(links, dict) and links.get("next")),
        "Incomplete native protocol inventory",
    )
    return list(protocols)


def accepts(ks, row, idp, protocol, mapping):
    descriptor = configured(row)
    if descriptor is None:
        return None
    _require(
        _field(idp, "id") == descriptor.idp_id
        and _field(idp, "enabled") is True
        and _field(idp, "remote_ids") == [descriptor.issuer]
        and _field(protocol, "id") == descriptor.protocol_id
        and _field(protocol, "mapping_id") == descriptor.mapping_id
        and mapping_matches(mapping, descriptor),
        "Native federation configuration changed",
    )
    remote_id_attribute = _field(protocol, "remote_id_attribute")
    if remote_id_attribute is None:
        # Some Keystone versions expose this extension only on protocol LIST.
        protocols = _protocol_rows(ks, descriptor)
        matches = [p for p in protocols if _field(p, "id") == descriptor.protocol_id]
        _require(
            len(matches) == 1 and _field(matches[0], "mapping_id") == descriptor.mapping_id,
            "Native protocol readbacks disagree",
        )
        remote_id_attribute = _field(matches[0], "remote_id_attribute")
    _require(remote_id_attribute == "HTTP_OIDC_ISS", "Native issuer transport changed")
    from app.services import account_spaces

    _require(
        _field(account_spaces.shared_domain("account", ks=ks), "id") == descriptor.account_domain_id
        and _field(account_spaces.shared_domain("personal", ks=ks), "id") == descriptor.personal_domain_id,
        "Native shared domains changed",
    )
    from dataclasses import replace

    return replace(descriptor, project_template=_project_template(mapping, descriptor))


def _read_mapping(ks, descriptor):
    from app.services import domain_auth as svc

    row = SimpleNamespace(
        id=descriptor.provider_id,
        kind="oidc",
        issuer_url=descriptor.issuer,
        client_id=descriptor.client_id,
        keystone_idp_id=descriptor.idp_id,
        keystone_protocol_id=descriptor.protocol_id,
        federation_token_type="id_token",
        _organization=None,
        _native_mapping=SimpleNamespace(
            mode=MODE,
            mapping_id=descriptor.mapping_id,
            sha256=descriptor.sha256,
            account_domain_id=descriptor.account_domain_id,
            personal_domain_id=descriptor.personal_domain_id,
        ),
    )
    return svc._require_native_mapping(ks, row)


def _native_user(user, descriptor=None, *, ks=None):
    """Recognize configured associations or aliases proven by current native pins."""
    name = _field(user, "name")
    if (
        _field(user, "enabled") is not True
        or not isinstance(name, str)
        or not name
        or _field(user, "afterglow_service_identity")
        or _field(user, "afterglow_identity_kind") == "service"
    ):
        return False
    federated = _field(user, "federated", []) or []
    if not isinstance(federated, list):
        return False
    for config in (descriptor,) if descriptor is not None else _configured():
        if _field(user, "domain_id") != config.account_domain_id:
            continue
        protocols = {
            protocol["protocol_id"]
            for idp in federated
            if isinstance(idp, dict) and idp.get("idp_id") == config.idp_id and isinstance(idp.get("protocols"), list)
            for protocol in idp["protocols"]
            if isinstance(protocol, dict)
            and isinstance(protocol.get("protocol_id"), str)
            and protocol["protocol_id"]
            and protocol.get("unique_id") == quote(name)
        }
        if config.protocol_id in protocols:
            return True
        if not protocols or ks is None:
            continue
        try:
            # An alias is not an implicit registry provider. Its native transport
            # must prove the same complete mapping and exact issuer association.
            _read_mapping(ks, config)
            rows = _protocol_rows(ks, config)
            for protocol_id in protocols:
                matches = [row for row in rows if _field(row, "id") == protocol_id]
                if (
                    len(matches) == 1
                    and _field(matches[0], "mapping_id") == config.mapping_id
                    and _field(matches[0], "remote_id_attribute") == "HTTP_OIDC_ISS"
                ):
                    return True
        except Exception:
            # Unproven shadows stay in the normal candidate set. In particular,
            # an unavailable native read must not resolve a password ambiguity.
            continue
    return False


def _email_user(user, identity, descriptor):
    """Preserve existing password names and stable external-subject bindings."""
    from app.services import domain_auth as svc

    identities = _field(user, "afterglow_external_identities", [])
    try:
        email = svc.normalize_email(_field(user, "email"))
    except svc.DomainAuthError:
        return False
    return (
        _field(user, "domain_id") == descriptor.account_domain_id
        and _field(user, "enabled") is True
        and isinstance(_field(user, "name"), str)
        and bool(_field(user, "name"))
        and not _field(user, "afterglow_service_identity")
        and _field(user, "afterglow_identity_kind") != "service"
        and email.casefold() == identity.email.casefold()
        and isinstance(identities, list)
        and all(
            isinstance(i, dict) and (i.get("issuer") != descriptor.issuer or i.get("subject") == identity.subject)
            for i in identities
        )
    )


def personal_project(user_id, *, ks, operation=None):
    configs = list(_configured())
    if not configs:
        return None
    user = operation.get("users", user_id) if operation is not None else ks.users.get(user_id)
    matches = [config for config in configs if _native_user(user, config, ks=ks)]
    if not matches:
        return None
    # Multiple configured protocols may describe the same mapping, but conflicting
    # mapping authorities for one user must never pick the first provider.
    authorities = {(c.mapping_id, c.sha256, c.account_domain_id, c.personal_domain_id) for c in matches}
    _require(len(authorities) == 1, "Native Personal mapping is ambiguous")
    for config in matches:
        _read_mapping(ks, config)
    return _mapped_personal_project(user_id, _field(user, "name"), ks=ks, operation=operation, descriptor=matches[0])


def _mapped_personal_project(user_id, mapped_username, *, ks, descriptor, operation=None):
    from fastapi import HTTPException

    from app.services import account_spaces, identity_roles

    descriptor = _read_mapping(ks, descriptor)
    domain = account_spaces.shared_domain("personal", ks=ks, operation=operation)
    _require(_field(domain, "id") == descriptor.personal_domain_id, "Native Personal domain changed")
    name = descriptor.project_template.format(mapped_username)
    rows = account_spaces._rows(ks.projects, domain=descriptor.personal_domain_id)
    _require(
        all(_field(p, "domain_id") == descriptor.personal_domain_id for p in rows),
        "Native Personal inventory has foreign scope",
    )
    matches = [p for p in rows if _field(p, "name") == name]
    if len(matches) != 1:
        raise HTTPException(503, "Native federation personal project is missing or ambiguous")
    pid = _field(matches[0], "id")
    _require(isinstance(pid, str) and bool(pid), "Native personal project identity is unavailable")
    project = operation.get("projects", pid) if operation is not None else ks.projects.get(pid)
    _require(
        _field(project, "id") == pid
        and _field(project, "enabled") is True
        and _field(project, "domain_id") == descriptor.personal_domain_id
        and _field(project, "name") == name,
        "Native personal project changed",
    )
    owner, primary = _field(project, "afterglow_personal_user_id"), _field(project, "afterglow_personal_primary")
    _require(
        (owner is None and primary is None) or (owner == user_id and primary is True),
        "Personal project already has different provenance",
    )
    catalog = operation.catalog() if operation is not None else identity_roles._trusted_catalog()
    account_spaces._verify_personal_member(ks, catalog, project, user_id, operation=operation)
    return {key: _field(project, key) for key in ("id", "name", "domain_id", "enabled")}


def adopt_personal_project(user_id, project, *, ks, descriptor):
    """Record provenance under the caller's IAM lease; never create native grants."""
    from app.services import account_spaces, identity_roles

    pid = project["id"]
    current = ks.projects.get(pid)
    owner, primary = _field(current, "afterglow_personal_user_id"), _field(current, "afterglow_personal_primary")
    _require(
        _field(current, "id") == pid
        and _field(current, "name") == project["name"]
        and _field(current, "enabled") is True
        and _field(current, "domain_id") == descriptor.personal_domain_id,
        "Native personal project changed",
    )
    _require(
        (owner is None and primary is None) or (owner == user_id and primary is True),
        "Personal project already has different provenance",
    )
    for row in account_spaces._rows(ks.projects, domain=descriptor.personal_domain_id):
        _require(
            not (
                _field(row, "afterglow_personal_user_id") == user_id
                and _field(row, "afterglow_personal_primary") is True
                and _field(row, "id") != pid
            ),
            "Another personal primary already exists",
        )
    catalog = identity_roles._trusted_catalog()
    account_spaces._verify_personal_member(ks, catalog, current, user_id)
    if owner is None:
        ks.projects.update(pid, afterglow_personal_user_id=user_id, afterglow_personal_primary=True)
    checked = ks.projects.get(pid)
    _require(
        _field(checked, "id") == pid
        and _field(checked, "domain_id") == descriptor.personal_domain_id
        and _field(checked, "enabled") is True
        and _field(checked, "name") == project["name"]
        and _field(checked, "afterglow_personal_user_id") == user_id
        and _field(checked, "afterglow_personal_primary") is True,
        "Personal project provenance readback failed",
    )
    account_spaces._verify_personal_member(ks, catalog, checked, user_id)


async def federate(row, identity, domain, *, ks, lease, catalog, descriptor):
    from app.services import account_spaces, organization_provisioning
    from app.services import domain_auth as svc

    username = identity.username
    _require(
        identity.issuer == descriptor.issuer
        and isinstance(username, str)
        and 0 < len(username) <= 255
        and not any(ord(c) < 32 for c in username),
        "Verified OIDC username is required",
    )
    await lease.assert_owned()
    await svc.require_provider(domain["id"], row.id, int(row.revision), identity.email)
    token, native = await svc.keystone_federate(row, identity.bearer)
    try:
        federation = native.get("OS-FEDERATION", {})
        _require(
            isinstance(federation, dict)
            and isinstance(federation.get("identity_provider"), dict)
            and federation["identity_provider"].get("id") == descriptor.idp_id
            and isinstance(federation.get("protocol"), dict)
            and federation["protocol"].get("id") == descriptor.protocol_id
            and isinstance(native.get("domain"), dict)
            and native["domain"].get("id") == descriptor.account_domain_id
            and isinstance(native.get("name"), str)
            and isinstance(native.get("id"), str)
            and bool(native["id"]),
            "Native federation returned an unexpected identity",
        )
        user = await asyncio.to_thread(ks.users.get, native["id"])
        _require(
            _field(user, "id") == native["id"]
            and _email_user(user, identity, descriptor)
            and _field(user, "name") == native["name"],
            "Native federation identity readback failed",
        )
        _require(
            await asyncio.to_thread(svc._require_native_mapping, ks, row) == descriptor,
            "Native mapping changed during login",
        )
        project = await asyncio.to_thread(
            account_spaces.personal_project,
            native["id"],
            ks=ks,
            native_mapping=descriptor,
            mapped_username=username,
        )
        _require(project is not None, "Native personal project is unavailable")
        await lease.assert_owned()
        current = await asyncio.to_thread(ks.projects.get, project["id"])
        if _field(current, "afterglow_personal_user_id") is None:
            await asyncio.to_thread(adopt_personal_project, native["id"], project, ks=ks, descriptor=descriptor)
        else:
            _require(
                _field(current, "afterglow_personal_user_id") == native["id"]
                and _field(current, "afterglow_personal_primary") is True,
                "Personal project already has different provenance",
            )
        await svc.require_provider(domain["id"], row.id, int(row.revision), identity.email)
        await organization_provisioning.require_current(row, ks=ks, user_id=native["id"], subject=identity.subject)
        return svc.FederatedLogin(
            unscoped_token=token,
            user_id=native["id"],
            username=native["name"],
            domain_id=domain["id"],
            domain_name=domain["name"],
            provider_id=row.id,
            provider_revision=int(row.revision),
            provider_kind=row.kind,
            login_email=identity.email,
        )
    except BaseException:
        await svc._revoke_quietly(token)
        raise


async def retire_deleted_primary_intent(intent, project, *, ks, lease, session):
    """Retain historical receipt fields; release only a proven deleted primary fence."""
    from fastapi import HTTPException
    from keystoneclient.exceptions import NotFound

    from app.services import account_spaces, identity_roles

    configs = [
        c
        for c in _configured()
        if c.account_domain_id == intent.identity_domain_id and c.personal_domain_id == intent.personal_domain_id
    ]
    if (
        not configs
        or intent.status != "accepted"
        or intent.primary is not True
        or intent.primary_user_id != intent.user_id
        or intent.project_creation_uncertain
        or not intent.personal_project_id
        or project.get("enabled") is not True
        or project.get("domain_id") != intent.personal_domain_id
        or project.get("id") == intent.personal_project_id
    ):
        return False
    authorities = {(c.mapping_id, c.sha256) for c in configs}
    _require(len(authorities) == 1, "Native Personal mapping is ambiguous")
    descriptor = await asyncio.to_thread(_read_mapping, ks, configs[0])
    prefix, suffix = descriptor.project_template.split("{0}")
    name = project.get("name", "")
    if not name.startswith(prefix) or not name.endswith(suffix) or len(name) <= len(prefix) + len(suffix):
        return False
    username = name[len(prefix) : len(name) - len(suffix) if suffix else None]
    candidate = await asyncio.to_thread(
        _mapped_personal_project, intent.user_id, username, ks=ks, descriptor=descriptor
    )
    if candidate != project:
        return False
    current = await asyncio.to_thread(ks.projects.get, project["id"])
    if (
        _field(current, "afterglow_personal_user_id") != intent.user_id
        or _field(current, "afterglow_personal_primary") is not True
    ):
        return False
    try:
        await asyncio.to_thread(ks.projects.get, intent.personal_project_id)
    except NotFound:
        pass
    except Exception as exc:
        raise HTTPException(503, "Old personal project deletion could not be verified") from exc
    else:
        return False
    catalog = await asyncio.to_thread(identity_roles._trusted_catalog)
    await asyncio.to_thread(account_spaces._verify_personal_member, ks, catalog, current, intent.user_id)
    await lease.assert_owned()
    intent.status = "cancelled"
    intent.primary_user_id = None
    await session.commit()
    return True
