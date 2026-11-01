"""Only the configured service identity can request native admin policy checks."""
import http.client

from keystone import exception
from keystone.common import provider_api, rbac_enforcer, sql
from keystone.server import flask as ks_flask

from . import API_REVISION, IdentityChanged, InvalidPassword, configured, create, guarded_cluster, identity, reset

PROVIDERS = provider_api.ProviderAPIs
ENFORCER = rbac_enforcer.RBACEnforcer


def service(resource):
    options = configured()
    context = resource.oslo_context
    if context is None or not getattr(context, "authenticated", False):
        raise exception.Unauthorized(message="Native service token required")
    token = getattr(context, "token_reference", {}).get("token")
    if (context.user_id != options.service_user_id or not isinstance(token, dict) or
            token.get("methods") != ["password"] or
            not any(isinstance(role, dict) and role.get("name") == "admin" for role in token.get("roles", [])) or
            getattr(context, "is_delegated_auth", False) or
            getattr(context, "trust_id", None) or
            getattr(context, "oauth_access_token_id", None)):
        raise exception.Forbidden(message="Configured nondelegated native service password token required")


def target(user_id):
    return {"user": PROVIDERS.identity_api.get_user(user_id)}


def unavailable():
    # Return a sanitized error directly rather than sending an underlying DB
    # exception through Keystone's exception logger (which logs tracebacks).
    return {"error": {"code": 503, "title": "Service Unavailable",
                      "message": "Conditional password prerequisites unavailable; reconcile any uncertain write before retrying"}}, 503


class InitialPasswordCapability(ks_flask.ResourceBase):
    def get(self):
        try:
            ENFORCER.enforce_call(action="identity:update_user", build_target=lambda: target(self.oslo_context.user_id))
            service(self)
            with sql.session_for_write() as session, guarded_cluster(session) as check:
                check()
            return {"revision": API_REVISION, "supported": True}
        except exception.Error:
            raise
        except Exception:
            return unavailable()


class ConditionalPassword(ks_flask.ResourceBase):
    operation = None

    def post(self, user_id):
        try:
            ENFORCER.enforce_call(action="identity:update_user", build_target=lambda: target(user_id))
            service(self)
            data = self.request_body_json
            if (not isinstance(data, dict) or set(data) != {"user"} or
                    not isinstance(data["user"], dict) or
                    set(data["user"]) != {"password", "domain_id", "email", "identity_revision"} or
                    not isinstance(data["user"]["domain_id"], str) or
                    not data["user"]["domain_id"]):
                raise exception.ValidationError(message="Exactly password, domain_id, email and identity_revision are required")
            if self.operation == "create":
                dispatch = create
            elif self.operation == "reset":
                dispatch = reset
            else:
                raise RuntimeError("Unknown conditional password operation")
            dispatch(user_id, data["user"]["domain_id"], data["user"]["password"], data["user"]["email"], data["user"]["identity_revision"], self.audit_initiator)
            return None, http.client.NO_CONTENT
        except InvalidPassword:
            return {"error": {"code": 422, "title": "Unprocessable Entity", "reason": "invalid_password", "message": "Password does not satisfy the native password policy and byte limit"}}, 422
        except IdentityChanged:
            return {"error": {"code": 412, "title": "Precondition Failed", "reason": "identity_changed", "message": "Native identity changed; obtain a new email proof"}}, 412
        except exception.Error:
            raise
        except Exception:
            return unavailable()


class InitialPassword(ConditionalPassword):
    operation = "create"


class PasswordReset(ConditionalPassword):
    operation = "reset"


class InitialPasswordIdentity(ks_flask.ResourceBase):
    def get(self, user_id):
        try:
            ENFORCER.enforce_call(action="identity:update_user", build_target=lambda: target(user_id))
            service(self)
            return identity(user_id)
        except exception.Error:
            raise
        except Exception:
            return unavailable()
