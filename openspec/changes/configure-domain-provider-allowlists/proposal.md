## Why

An unconfigured domain should offer every registered enabled login provider, including multiple GitLab OIDC instances. The current additive `providers` selectors instead hide unselected registrations and cannot express a domain that excludes a globally selected provider.

## What Changes

- **BREAKING** Replace selector lists at `auth.default.providers` and `auth.domain.<canonical-domain-ID>.providers` with `allow_providers`; keep `auth.providers.<key>` as the instance registry and reject the retired selector field.
- Resolve the exact domain's explicit allowlist first, otherwise the default allowlist, otherwise all enabled registered providers. An explicit empty list allows no external login provider; a domain allowlist replaces rather than appends to the default.
- Apply the effective allowlist to the public login list and every existing provider authority boundary. Existing SQL IAM providers are identified by their canonical UUID and cannot bypass an explicit allowlist; without a restriction they remain domain-local and available.
- Preserve same-kind provider instances, authored allowlist order, password/signup policy, SQL outage fail-closed behavior and native federation validation. Update configuration examples and K8s/Helm projection without introducing a migration or touching operator settings.

## Capabilities

### New Capabilities

- `domain-login-provider-allowlists`: Instance-key/canonical-SQL-ID domain allowlists, unrestricted fallback, and consistent login/session enforcement.

### Modified Capabilities

None.

## Impact

Settings auth models, domain auth selection and existing usable-provider guard, K8s/Helm auth TOML projection, consumer regressions, afterglow.conf.example and authentication/deployment/architecture documentation. No frontend response schema, component design, credential format, database schema, Keystone provisioning, live deployment or production configuration changes.

## Current local enablement follow-up

The subsequent user request authorizes enabling the existing GitLab login in the current local configuration for Default and dmslab, followed by explicit approval for required shared Keystone/GitLab authentication changes. Reuse the current native `gitlab/openid` and existing `gitlab/mapped` domain-specific mappings without native mutation, select separate registry instances per exact domain, and add only the missing local generic callback to the existing GitLab application. Preserve application source, credentials, existing callbacks, accounts and permissions. Do not substitute workspace switching, move/clone accounts, weaken domain validation or claim a completed user login from the upstream sign-in screen. User consent/code exchange and Keystone session acceptance remain unverified.

## Configuration-driven extensibility follow-up

The user explicitly requires reusable configuration-driven connections rather than Default/dmslab/GitLab-specific application branches. Retain the existing registry/allowlist schema and generic login/callback consumers: provider keys, labels, issuers, credentials and native IdP/protocol bindings are operator data. Verify one issuer/application with independent domain-specific protocol mappings, rejection of mismatched native identities, and adding another supported login option by TOML/Secret changes alone. Document the difference between adding an OIDC/GitHub instance (configuration only) and implementing a previously unsupported authentication protocol (code required). Preserve current private connections and shared infrastructure; do not invent another registry, aliases, automatic provisioning or a hot-reload mechanism.

