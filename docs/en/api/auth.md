---
title: Auth
parent: API Reference
grand_parent: English
lang: en
nav_order: 10
---

# Auth API

> Tag: `auth`
> Base path: `/api/v1/auth`

Provides login, JWT token issuance/rotation, session management, and project scope switching.
Domain login policy, OIDC/GitHub provider federation and email-verified onboarding are also provided.

## Identity home, personal projects, and organizations

New human accounts are created in the operator-provisioned native `Accounts` domain, and personal projects in native `Personal`. The server resolves exact enabled native names, not display labels; absent management metadata is allowed, but explicit conflicting kinds and ambiguous case variants are rejected. Enrollment does not create or mutate shared domains. Accounts is identity-only, not a workspace or cross-user directory. Public password login searches only Accounts and uses its exact UUID for native authentication; it never falls back to legacy homes. Existing identities, credentials, grants and resources are not migrated. Explicit account-link proof retains the original canonical-home boundary. `identity_domain_id` identifies the home, while `domain_id` and `project_id` identify the active workspace. Administrator creation treats the selected directory domain only as observation context, never as automatic organization or Default-reader admission.

Personal project creation has no name or personal-domain input. The server generates `normalized_username[:47] + "-" + 8 cryptographically random lowercase letters + 8 random decimal digits` within Keystone's 64-character limit, applies the frozen per-project quota template, and verifies exactly one direct native `member` grant to the user against raw and effective native provenance. It does not grant owner, administrator or reader roles, and rejects member implications that elevate manager or owner/admin authority. Established owner-based personal projects retain their original grants and validation; no automatic migration occurs. Personal workspaces have neither domain `manager` authority nor a shared `Default`; other users' personal projects are excluded from workspace and user-directory responses.

Organizations remain separate resource domains. Explicit creation follows `organization_creation_enabled` and `max_organizations_per_user`; its creator is the initial manager. Organization admission requires acceptance of a current manager's invitation or a trusted provider admission rule. Configured OIDC organization bindings use the exact issuer and immutable external organization ID; the client ID is provenance, not organization identity. Only explicitly configured manager subjects may create the first organization. Ordinary subjects can join only an already active binding and receive reader access, not manager or owner. Sharing a provider origin alone grants no organization membership. Existing explicit email-host auto-join rules remain additive, reader-only admission to the exact configured domain.

Global signup uses `POST /registrations`, followed by `/registrations/accept`; new invitation acceptances use the same account/personal provisioning path. Generic IAM account creation is unavailable. Existing-account invitation acceptance preserves the original native user and identity home. Merely browsing organizations never changes the session; workspace selection is explicit. The reserved shared domains cannot be renamed or disabled.

Administrator creation commits an accepted Accounts identity and a same-token/name frozen-quota deferred personal intent; it returns `personal_project_deferred:true` and null project fields without creating a project or grant. The first successful password/provider proof prepares the personal member project. Confirmed/not-sent stages resume; dispatched operations with unknown outcomes remain fenced. `POST /api/v1/auth/personal-project/recovery` accepts the same `{username,password}` body as login, verifies a fresh Accounts password/subject and all existing login guards, then uses the same JWT publication path. A safe503 has `personal_project_retry_available`, `retryable:true`, `native_calls_settled_required:false`; the UI clears the password and requires re-entry. Unknown work instead returns `personal_project_recovery_required`, `retryable:false`, `native_calls_settled_required:true` until a system administrator confirms original native calls have ended and settles the recorded operation. Neither path resets the identity, home, password or existing resources. Drain older human/API/worker writers before rollout; mixed-version writers or downgrade with active deferred intents are not supported.

Personal's one direct native member cannot be removed through generic project-role management or supplemented with service-admin roles. Four services independently derive a fresh internal personal-owner policy credential from exact enabled native domain/project/user and raw/effective member provenance. Project-local actions expand, not system/global authority; explicit policy denies, original scope and reduced/key/provider ceilings remain authoritative. Hub own-project package metadata deletion is human-only and preserves shared CAS bytes, GC and build/system boundaries.

Profile-image endpoints are documented in the [canonical profile API](../../api/profile.md): Gravatar uses only the current email hash and fixed HTTPS origin; generated avatars and bounded normalized raster uploads persist in one native user extra key. A caller exact-self read plus bounded service writer preserves stock Keystone update-user policy, other metadata and session/ABA fences. Live Keystone service-writer permission/capacity and real password/OIDC acceptance remain separate deployment gates.

Apply additive migrations `099_account_topology.sql` and `100_organization_bindings.sql` before enabling these readers or writers. Uncertain native writes remain fenced; do not retry or delete native objects speculatively. Fresh system administrators inspect `/api/v1/admin/account-topology/operations` or `/api/v1/admin/organization-bindings` and settle the recorded intent only after native calls have stopped. See the [canonical authentication API](../../api/auth.md) and [IAM API](../../api/iam.md) for exact settlement payloads and operator prerequisites. Source and synthetic acceptance do not authorize a shared schema or native configuration rollout.

---

## Authentication Method

Afterglow uses **JWT (access + refresh) pair**-based authentication.
On login, the server stores the caller-owned unscoped Keystone login proof in a Redis session and issues an
access JWT and a refresh JWT to the client. Thereafter, every request that requires
authentication must include the headers below.

| Header | Required | Description |
|------|------|------|
| `Authorization` | Yes | `Bearer <access_jwt>` form. The `token` value from the login response |
| `X-Project-Id` | No | Project UUID to process the request. If omitted, processed with the project embedded in the JWT. If a value different from the JWT's project is given, the server performs a Keystone rescope (project switch) |

> The access JWT internally points to a refresh session (`rjti`), and on every request the server
> validates that proof and exchanges a derived native project token using current authority. Role-bearing validation results are not reused across requests in a 60-second cache. Authority comes from current native identity/domain/membership/role assignments, not JWT claims. `require_admin` rechecks native `domain_context` and exact `system:all` authority. Derived project tokens are neither stored as the login proof nor exposed to the browser.

### Session/Token Lifetime Model

- **access JWT** — Short-lived token. The expiry time is the response's `expires_at`.
- **refresh JWT** — Corresponds to a Redis session (`session_store`). The unscoped login proof, active native project and logical workspace, original login IP/device fingerprint, authentication method, immutable `identity_domain_id`, and active `domain_id` are stored together. Federated sessions also retain `provider_id`, `provider_revision`, original `provider_domain_id`, and verified `login_email`. Missing required identity/working/provider-origin context requires a fresh login.
- **Session timeout** — Independent of the Keystone token lifetime, the session start time is recorded in Redis, and
  if it exceeds `session_timeout_seconds`, it is expired with a 401.
- **Token rotation** — `POST /refresh` immediately deletes the existing refresh session and issues a new pair.
  Using the same refresh token twice makes the second call a 401.

### Security Restrictions (reference)

- **Login failure lockout** — Isolated by domain ID and username. Only native `v3.Password` credential rejection increments failures; directory outages return 503 without counting as a bad password. Redis failure skips lockout (fail-open).
- **Token origin binding** — If the access token's origin IP/device fingerprint does not match the initial login,
  it may be blocked. If the binding check itself fails (Redis failure, etc.), it **rejects the request
  (fail-closed, 401)**.

---

## Endpoint List

| Method | Path | Auth | Description |
|--------|------|------|------|
| `POST` | `/api/v1/auth/login` | None | Issue JWT with username/password (10/min) |
| `GET` | `/api/v1/auth/me` | Required | User/project info of the current token |
| `POST` | `/api/v1/auth/logout` | Required | Log out the current session (delete refresh session + Keystone revoke) |
| `POST` | `/api/v1/auth/refresh` | refresh token | Reissue access/refresh JWT (rotation, 30/min) |
| `POST` | `/api/v1/auth/token/project` | Required | Switch scope to another project (new token pair) |
| `POST` | `/api/v1/auth/logout-all` | Required | Revoke all sessions of the current user |
| `GET` | `/api/v1/auth/sessions` | Required | List active sessions of the current user |
| `DELETE` | `/api/v1/auth/sessions/{jti}` | Required | Delete an individual session (ownership check) |
| `GET` | `/api/v1/auth/groups` | Required | List Keystone groups the current user belongs to |
| `GET` | `/api/v1/auth/projects` | Required | List accessible projects |
| `GET` | `/api/v1/auth/projects/recent` | Required | List projects by most recent access |
| `GET` | `/api/v1/auth/domains/resolve` | None | Resolve domain and login methods (30/min) |
| `POST` | `/api/v1/auth/domains/{domain_id}/providers/{provider_id}/authorize` | None, same-site | Start provider authorization (20/min) |
| `POST` | `/api/v1/auth/providers/callback` | None, state cookie | Issue JWT from code/state (10/min) |
| `GET` | `/api/v1/auth/invitations/{token}` | None | Read delivered invitation link (20/min) |
| `POST` | `/api/v1/auth/invitations/accept` | None | Create an account from invitation (5/min) |
| `POST` | `/api/v1/auth/invitations/accept-existing` | Required | Accept with own existing account (5/min) |
| `POST` | `/api/v1/auth/registrations` | None | Request a global signup verification email; no domain input (3/min) |
| `POST` | `/api/v1/auth/domains/{domain_id}/registrations` | None | Forbidden: signup cannot select an organization identity domain |
| `POST` | `/api/v1/auth/registrations/accept` | None | Create an account from verified link (5/min) |

---

## Common Schemas

### TokenResponse

The common schema returned by login, refresh, project switch and provider callback.

```json
{
  "token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "user_id": "uuid-string",
  "username": "user-name",
  "identity_domain_id": "account-domain-uuid",
  "identity_domain_name": "accounts",
  "domain_id": "personal-domain-uuid",
  "domain_name": "personal",
  "is_domain_manager": false,
  "expires_at": "2026-01-01T00:00:00+00:00",
  "roles": ["member"],
  "default_project_id": "uuid-string",
  "is_system_admin": false,
  "can_write": true,
  "auth_method": "password"
}
```

| Field | Type | Description |
|------|------|------|
| `token` | string | access JWT. Used in the `Authorization: Bearer` header |
| `refresh_token` | string\|null | refresh JWT. Used in `POST /refresh` |
| `project_id` | string | Scoped project UUID; `""` when no accessible project exists |
| `project_name` | string | Project name; `""` for domain-only login |
| `user_id` | string | User UUID |
| `username` | string | Username |
| `domain_id`, `domain_name` | string | Server-verified user identity domain ID and display name |
| `is_domain_manager` | boolean | Current authority on the domain itself, not a project `manager` role name |
| `expires_at` | string | access JWT expiry time (ISO 8601) |
| `roles` | array[string] | Display-only project roles; hides `admin`, `manager`, their custom ancestors and unclassified custom names for ordinary users |
| `default_project_id` | string | User's default project UUID (`""` if none) |
| `is_system_admin` | boolean | Whether the user is a system admin |
| `can_write` | boolean | Project write permission calculated from verified roles before name filtering; do not infer it from display names |
| `auth_method` | string | `password` or `federated` |

### UserInfo

```json
{
  "user_id": "uuid-string",
  "username": "user-name",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "domain_id": "domain-uuid",
  "domain_name": "Example",
  "is_domain_manager": false,
  "roles": ["member", "reader"],
  "is_system_admin": false,
  "can_write": true,
  "auth_method": "password"
}
```

`roles` is a public projection, not authorization input. System administrators see all names; ordinary users do not see system-only or unclassified custom names. Unknown external role metadata triggers one catalog refresh; metadata failure does not fail login or `/me`. Native validation and separate project ownership remain authoritative, and filtering names does not change `can_write`.

### ProjectInfo

```json
{
  "id": "uuid-string",
  "name": "project-name",
  "description": "Project description",
  "domain_id": "uuid-string",
  "domain_name": "Default",
  "enabled": true,
  "last_accessed_at": null
}
```

`last_accessed_at` is populated only by `/projects/recent` (otherwise `null`).

---

## POST /api/v1/auth/login

Resolves the explicit domain first, authenticates native credentials and issues a JWT pair. Dashboard pre-warming and recent-access recording run only when a project exists. Rate limit: **10/min**.

### Request body

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "project_name": "string (optional)",
  "domain_name": "Example (required)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `username` | string | Yes | OpenStack username, 1–255 characters |
| `password` | string | Yes | Password, 1–1024 characters |
| `project_name` | string | No | Up to 255 characters, default `""`; selects accessible default/first project |
| `domain_name` | string | Yes | Explicit domain name or ID, 1–255 characters; no implicit `Default` |

### Response (200 OK)

[TokenResponse](#tokenresponse) — `auth_method` is `password`.

Login succeeds even with no accessible enabled projects: `project_id` and `project_name` are `""`, `roles` is `[]`, and `can_write` is `false`. Domain managers can use IAM without a project; project-resource operations still require a real project scope. Project selection/switching stays within the user's identity domain.

### Error responses

| Status code | Description |
|-----------|------|
| `401` | Authentication failed (invalid credentials) |
| `403` | Disabled domain, password-policy denial or email allowlist violation |
| `404` | Domain not found |
| `422` | Missing explicit domain or invalid body |
| `503` | Directory, login-policy storage or authentication outage; not a password rejection |
| `429` | Account lockout (repeated failures) or rate limit exceeded |

---

## GET /api/v1/auth/me

Returns the user and project information of the current access token.

### Response (200 OK)

[UserInfo](#userinfo).

### Error responses

| Status code | Description |
|-----------|------|
| `401` | Invalid or expired token |

---

## POST /api/v1/auth/logout

Logs out the current session. Performs refresh session deletion + Keystone token revoke + validation/session
cache invalidation.

### Response (200 OK)

```json
{ "message": "로그아웃 완료" }
```

---

## POST /api/v1/auth/refresh

Issues a new access/refresh JWT pair using the refresh JWT (**token rotation**). The existing refresh
JTI is immediately deleted, so calling twice with the same refresh token makes the second a 401.
Rate limit: **30/min**. This endpoint authenticates with the refresh token in the body, not the
Authorization header.

### Request body

```json
{ "refresh_token": "string (required)" }
```

### Response (200 OK)

[TokenResponse](#tokenresponse).

### Error responses

| Status code | Description |
|-----------|------|
| `401` | Invalid refresh token / session expired / session blocked (blacklist) |
| `403` | Domain/user/project context or current login-policy denial; re-authenticate |
| `429` | Refresh rate limit; apply Retry-After cooldown |
| `503` | Redis/Keystone connection or validation outage; preserve session for retry |

Keystone token-authentication `404 Failed to validate token` and `404 Could not recognize Fernet token` map to 401; generic endpoint/resource 404 cannot establish invalid authentication and maps to 503. **Refresh 401 and context/policy 403 are terminal**: clear authentication and log in again. **429, 5xx and network failures are transient**: retain the session and retry. The browser provides retry/logout recovery; ordinary downstream resource failures do not become global authentication failures.

---

## POST /api/v1/auth/token/project

Issues a new token pair scoped to another project accessible with the current token (rescope).
Used when switching projects.

### Request body

```json
{ "project_id": "uuid-string (required)" }
```

### Response (200 OK)

[TokenResponse](#tokenresponse).

### Error responses

| Status code | Description |
|-----------|------|
| `401` | Invalid or expired token |
| `403` | No access permission to the target project |

---

## POST /api/v1/auth/logout-all

Revokes **all sessions** of the current user (including direct Keystone revocation). Includes federated users.
The current session is also revoked, so re-login is required after calling.

### Response (200 OK)

```json
{ "message": "모든 세션이 폐기되었습니다.", "revoked_count": 3 }
```

---

## GET /api/v1/auth/sessions

Returns the list of active sessions of the current user. Includes origin IP/device/last-used info,
and sensitive fields such as `keystone_token` are stripped before being returned.

### Response (200 OK)

```json
{
  "sessions": [
    { "jti": "...", "domain_id": "domain-uuid", "project_id": "", "origin_ip": "...", "device_type": "desktop", "os": "macOS", "started_at": 1790000000, "last_seen": 1790000100, "auth_method": "password" }
  ],
  "count": 1
}
```

---

## DELETE /api/v1/auth/sessions/{jti}

Deletes an individual session. **Ownership check required** — if the target `jti` is not the current user's
session, it returns 404 (other-user session hiding). The Keystone token is also revoked on a best-effort basis.

### Response (200 OK)

```json
{ "message": "세션이 삭제되었습니다." }
```

### Error responses

| Status code | Description |
|-----------|------|
| `404` | Not the current user's session, or a nonexistent session |

---

## GET /api/v1/auth/groups

Returns the list of Keystone groups the current user belongs to. If policy does not permit the query,
it returns an empty list.

### Response (200 OK)

```json
[
  { "id": "uuid-string", "name": "group-name", "description": null, "domain_id": "uuid-string" }
]
```

### Error responses

| Status code | Description |
|-----------|------|
| `500` | Failed to fetch group list |

---

## GET /api/v1/auth/projects

Returns the list of all projects accessible to the current user (2-min cache).

### Response (200 OK)

[ProjectInfo](#projectinfo) array (`last_accessed_at` is `null`).

### Error responses

| Status code | Description |
|-----------|------|
| `500` | Failed to fetch project list |

---

## GET /api/v1/auth/projects/recent

Returns the project list sorted by most recent access. Sorts by the access time recorded in Redis and
populates `last_accessed_at`. Projects with no access record are appended afterward in name order.

### Response (200 OK)

[ProjectInfo](#projectinfo) array (includes `last_accessed_at`).

---

## Domain-first login and provider federation

First call `GET /api/v1/auth/domains/resolve?name=Example`. Required `name` is 1–255 characters and accepts an exact enabled domain name or ID. Response `200`:

```json
{"domain_id":"domain-uuid","domain_name":"Example","password_enabled":true,"providers":[{"id":"provider-uuid","name":"Company SSO","kind":"oidc"}],"signup_enabled":false}
```

Provider kind is `oidc` or `github`. Only enabled/configured providers are advertised; an unverified provider remains available so its first successful login can verify it. Public `signup_enabled` combines policy opt-in, a nonempty signup allowlist and SMTP configuration. Secrets, email allowlists and Keystone federation settings are not public.

`POST /api/v1/auth/domains/{domain_id}/providers/{provider_id}/authorize` takes no body and returns `200 {"authorize_url":"..."}`. Use a credential-including browser request to receive the cookie, then navigate to that URL. Redirect targets the configured frontend's `/auth/callback`. The server stores a 600-second, one-use state in Redis, bound to domain/provider/revision, browser binding, redirect URI, PKCE verifier and nonce. `afterglow_provider_auth` is HttpOnly, SameSite=Lax, Path=`/api/v1/auth/providers/callback`, Max-Age=600; Secure in production or with an HTTPS public API. Both kinds use PKCE S256; OIDC also sends and verifies a nonce.

The frontend callback makes a credential-including `POST /api/v1/auth/providers/callback` with exactly this body (extra fields forbidden):

```json
{"code":"provider-authorization-code","state":"returned-state"}
```

`code`: 1–2048 characters; `state`: 16–256. Success is `200` [TokenResponse](#tokenresponse), `auth_method="federated"`. State is atomically consumed; replay, expiry and missing/wrong browser cookies are rejected. The cookie is cleared on success and DomainAuthError callback failures. OIDC verifies signed ID-token keys, issuer/audience/time/subject/nonce and binds UserInfo to the same subject when used. OIDC verified email or GitHub's single verified primary email is checked against policy. The real Keystone OS-FEDERATION user domain and IdP/protocol are verified; no admin/service password impersonation is used.

Security-relevant provider edits increment revision, invalidating pending state and provider-bound sessions. Callback mismatch returns `409 provider_changed`; refresh rejects changed/disabled/deleted providers with `403 provider_changed`/`provider_disabled`. Display-name-only edits do not increment revision. See [Domain IAM](../../api/iam.md) for CRUD and successful-login verification.

Before disabling password login, successfully issue a real native federated session at the provider's current revision. While password is off, security edits, disabling or deletion of the last verified provider return `409 last_login_method`. A revision race between session storage and proof stamping also returns `409 provider_changed` and revokes/deletes the newly created session.

**Frontend and API must be same-site.** Same-host means the same scheme/host (ports may differ); subdomains require the exact configured frontend Origin and `Sec-Fetch-Site: same-origin|same-site`. Cross-site browsers receive `503 cross_site_callback_unsupported`. CORS alone is insufficient; SameSite=None is never used. Genuinely cross-site deployments require a first-party API proxy. Wrong Origin returns `403 origin_mismatch`.

DomainAuthError responses are `{detail: "safe message", code: "stable code"}`, with no-store/private and no-cache.

| HTTP | `code` | Meaning |
|---|---|---|
| 401 | `invalid_state` | Expired/replayed state or absent/mismatched cookie |
| 403 | `domain_disabled`, `provider_disabled`, `foreign_domain` | Disabled domain/provider or federation identity boundary violation |
| 403 | `email_not_verified`, `email_domain_not_allowed`, `federation_denied` | Verified-email, policy or Keystone federation rejection |
| 404 | `domain_not_found`, `provider_not_found` | Selected domain/provider absent |
| 409 | `provider_changed` | Revision or discovery token endpoint changed; restart login |
| 422 | `identity_invalid_input` | Query/body validation failure without secret reflection |
| 429 | — | Resolve 30/min, authorize 20/min or callback 10/min limit exceeded |
| 502 | `provider_error`, `invalid_id_token` | Provider response/code exchange/ID-token verification failed |
| 503 | `unavailable`, `redirect_not_configured`, `cross_site_callback_unsupported` | Storage/Keystone outage or unusable frontend/API configuration |

## Public email-verified onboarding

Invitation creation/list/revocation uses manager-only [Domain IAM](../../api/iam.md). Paths below are relative to `/api/v1/auth`; only accept-existing requires an access bearer. Acceptance bodies cannot choose an email or target user ID.

| Method/path | Exact body | Success | Limit |
|---|---|---|---|
| `GET /invitations/{token}` | None | 200 `{domain_id,domain_name,email,expires_at,project_name}` | 20/min |
| `POST /invitations/accept` | `{token,name,password}` | 200 `{user_id,domain_id,domain_name}` | 5/min |
| `POST /invitations/accept-existing` | `{token}` | 200 `{user_id,domain_id,domain_name}` | 5/min |
| `POST /domains/{domain_id}/registrations` | `{email}` | 202 `{accepted:true}` | 3/min |
| `POST /registrations/accept` | `{token,name,password}` | 200 `{user_id,domain_id,domain_name}` | 5/min |

POST token: 32–256 characters; name: 1–255 without leading/trailing whitespace; password: 12–1024; email: 3–255, subject to exact email-host policy. All bodies forbid extra fields. Signup requires enabled password login, signup opt-in and allowlists; registration links expire after one hour. Existing emails use the same verification-request flow, but redemption never overwrites an existing account/password. Invitations are delivered one-use secrets stored only as SHA-256 hashes. Acceptance does not issue JWTs; log in afterward.

Principal failures: `403` domain/email mismatch, policy or revoked inviter authority; `404` missing link; `409` existing account, role hierarchy or concurrent mutation; `410` expired/revoked/used/nonredeemable link; `422` invalid input; `429` rate limit; `503` SMTP/identity/storage outage. SMTP failures are not reported as successful delivery. Existing-account acceptance requires the same domain, an enabled authenticated account and matching link email. See [Domain IAM](../../api/iam.md) for lifecycle and partial failures. Responses use no-store and no-referrer.

Invitation acceptance **adds** the requested safe roles without replacing existing direct grants. A failure after native execution intent returns503 with the operation ID and compensated/recovery-required disposition. Failed/recovery or crash-intent links reject reuse with410. A domain manager inspects `/api/v1/iam/operations` and invitation history and performs any required compensation.


### Browser and MCP security patch compatibility

The original browser session start is retained across refresh and project rescope. Expired sessions stay rejected on retries, and Redis atomically consumes rotation so concurrent requests have one winner. Provider login records request origin/device; legacy sessions missing origin require a new login under strict/subnet policies. Logout reports revocation failures instead of claiming success.

JWT credentials persist only in tab sessionStorage. Legacy localStorage credentials are discarded, requiring one login after upgrade; new tabs authenticate independently. Browser tab duplication can copy sessionStorage. SvelteKit nonce/hash CSP removes script unsafe-inline but does not make JavaScript-readable credentials HttpOnly. MCP refresh requires the issuing client_id even when omitted previously. One-time PAT issuance responses use no-store/no-cache.

MCP timeout/cancellation fences new provider mutations after final ownership reads and retains the SDK worker, connection and concurrency slot until completion. Already-sent cloud requests cannot be rolled back. UUID-owned concurrency members do not auto-expire: crashed worker/release failures retain capacity until an operator verifies all related workers are drained/dead before clearing stale state. Poll/cleanup marks expired mutation leases unknown without resending, and a fresh key cannot duplicate identical unresolved arguments within the same grant/source/tool.

## MCP project provisioning tools

Personal MCP and delegated Lumen calls share canonical registry `2026-10-11.2`. The following tools require an explicitly approved `manage` grant with `mcp:write`; read-only grants cannot discover or dispatch them. Optional `project_id` must be approved and selects that project's restricted application credential. Default Lumen cloud access remains read-only.

| Tool | Required inputs | Optional inputs and bounds | Accepted result |
|---|---|---|---|
| `afterglow_vm_create` | `name`, `image_id`, `flavor_id`, `network_id` | Name: 1–63 characters, alphanumeric first, then alphanumeric/`_`/`-`. `boot_volume_size_gb`: default50, integer1–16384. Optional owned `key_name` and `availability_zone` without a host override. `delete_boot_volume_on_termination`: defaultfalse | Safe server ID/name/current status/timestamps and `requested_action: "create"`; not ACTIVE or guest readiness |
| `afterglow_volume_create` | `name`, integer `size_gb` | Nonblank name1–255 characters, size1–16384GiB, optional `availability_zone` | Empty Cinder volume ID/name/current status/size/timestamp and `requested_action: "create"`; `creating` is not ready |
| `afterglow_vm_network_attach` | `server_id`, `network_id` | Exact-project ACTIVE/SHUTOFF server and owned or explicitly shared network. No existing `port_id`, fixed IP or security-group overrides | Verified server/network/new port IDs, MAC and `requested_action: "attach_network"`; not guest configuration or data-plane proof |

MCP mutation calls require `idempotency_key`. Completed identical requests replay the stored result. Lumen `/api/v1/mcp/lumen/preview` does not create resources; `/execute` uses a separate key through the same ledger. Grant, target, resource state and SDK deadline are revalidated immediately before dispatch. An uncertain outcome stays `unknown`; a fresh key cannot resend identical unresolved arguments within the same grant/source/tool. Inspect the actual provider outcome instead of retrying blindly.

VM creation reuses project flavor quota, host-capacity and GPU admission plus name uniqueness. It validates active image visibility/minimum disk/RAM, network eligibility and optional keypair ownership from the Nova response. Image-to-volume boot mapping supports zero-disk flavors. Boot volumes are retained unless `delete_boot_volume_on_termination=true` is explicitly requested. Inputs exclude user data, passwords and arbitrary provider attributes; outputs exclude application credentials, private keys and `adminPass`.

These are local-source additions. MCP handshake/discovery, live cloud provisioning and production deployment are separate evidence boundaries.

## MCP observed clients and credential-wide removal

`GET /api/v1/auth/mcp-tokens` and `/api/v1/auth/mcp-oauth/grants` return owner-user/anchor-project grant metadata with `Cache-Control: no-store` and `Pragma: no-cache`. Each record includes `client_observations`, empty for a new or legacy grant until authenticated successful MCP initialization is observed.

Each observation contains exactly `client_name`, `client_version`, `product`, `kind` (browser/agent/bot/sdk/unknown), `identity_source` (client_info/user_agent/unknown), `browser`, `os`, `first_seen_at`, and `last_seen_at`. Names/versions are sanitized self-reports; product/browser/OS are fixed inferred labels or null. UTC timestamps describe first/last successful initialization of that sanitized signature, not continuous presence. Keep at most ten recent distinct signatures and preserve first-seen on repeat initialization. Never expose raw UA/IP, tokens/hashes, Authorization, capabilities or upstream credentials.

Self-reported names and User-Agent can be forged and are not authorization identity or proof of a physical device/session. **Remove connection** uses the existing owner-scoped personal-key/OAuth-grant DELETE to revoke the entire credential, including every client sharing it and a selected Lumen default. Keep tombstone/audit, credential epoch and OAuth family/refresh invalidation, and durable upstream cleanup. Do not treat deletion of observation data or User-Agent blocking as access revocation.

OAuth/PAT list readiness and errors are independent. A failed count stays unknown with retry, never a verified zero; failed/stale selected records cannot authorize an action. Actor/project/method/refresh changes fence pending confirmations. Apply additive migration087 before readers/writers and synchronize existing084–086 prerequisites. Missing `project_scope` SQL1054 is a schema mismatch, not an empty inventory. Shared/production schema rollout requires separate operator authorization.
