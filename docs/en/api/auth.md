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
The GitLab OIDC (federated) login callback is also mounted on the same router.

---

## Authentication Method

Afterglow uses **JWT (access + refresh) pair**-based authentication.
On login, the server stores the Keystone token in a Redis session and issues an
access JWT and a refresh JWT to the client. Thereafter, every request that requires
authentication must include the headers below.

| Header | Required | Description |
|------|------|------|
| `Authorization` | Yes | `Bearer <access_jwt>` form. The `token` value from the login response |
| `X-Project-Id` | No | Project UUID to process the request. If omitted, processed with the project embedded in the JWT. If a value different from the JWT's project is given, the server performs a Keystone rescope (project switch) |

> The access JWT internally points to a refresh session (`rjti`), and on every request the server
> live-validates the Keystone token stored in the Redis session (60s cache). Permissions (roles,
> is_system_admin) always use the Keystone validation result, not the JWT payload.

### Session/Token Lifetime Model

- **access JWT** — Short-lived token. The expiry time is the response's `expires_at`.
- **refresh JWT** — Corresponds to a Redis session (`session_store`). The Keystone token, project,
  login origin IP/device fingerprint, and authentication method are stored together.
- **Session timeout** — Independent of the Keystone token lifetime, the session start time is recorded in Redis, and
  if it exceeds `session_timeout_seconds`, it is expired with a 401.
- **Token rotation** — `POST /refresh` immediately deletes the existing refresh session and issues a new pair.
  Using the same refresh token twice makes the second call a 401.

### Security Restrictions (reference)

- **Login failure account lockout** — Temporarily locks on repeated failures (`login_guard`). On Redis failure,
  it **skips the lock (fail-open)** prioritizing availability (intended behavior, see `CLAUDE.md` §3).
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
| `GET` | `/api/v1/auth/gitlab/enabled` | None | Whether GitLab OIDC is enabled |
| `GET` | `/api/v1/auth/gitlab/authorize` | None | GitLab OAuth2 authorization URL |
| `POST` | `/api/v1/auth/gitlab/callback` | None | GitLab callback: issue JWT from code (10/min) |

---

## Common Schemas

### TokenResponse

The common schema returned by login, refresh, project switch, and GitLab callback.

```json
{
  "token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "user_id": "uuid-string",
  "username": "user-name",
  "expires_at": "2026-01-01T00:00:00+00:00",
  "roles": ["member", "reader"],
  "default_project_id": "uuid-string",
  "is_system_admin": false,
  "auth_method": "password"
}
```

| Field | Type | Description |
|------|------|------|
| `token` | string | access JWT. Used in the `Authorization: Bearer` header |
| `refresh_token` | string\|null | refresh JWT. Used in `POST /refresh` |
| `project_id` | string | Scoped project UUID |
| `project_name` | string | Project name |
| `user_id` | string | User UUID |
| `username` | string | Username |
| `expires_at` | string | access JWT expiry time (ISO 8601) |
| `roles` | array[string] | List of roles in the current project |
| `default_project_id` | string | User's default project UUID (`""` if none) |
| `is_system_admin` | boolean | Whether the user is a system admin |
| `auth_method` | string | `password` or `federated` |

### UserInfo

```json
{
  "user_id": "uuid-string",
  "username": "user-name",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "roles": ["member", "reader"],
  "is_system_admin": false,
  "auth_method": "password"
}
```

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

Authenticates user credentials against Keystone and issues a JWT pair. Right after a successful login,
it pre-warms the dashboard cache in the background and records the recent project access.
Rate limit: **10/min**.

### Request body

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "project_name": "string (optional)",
  "domain_name": "string (optional, default: Default)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `username` | string | Yes | OpenStack username |
| `password` | string | Yes | OpenStack password |
| `project_name` | string | No | Project name to scope to. If omitted, the default project |
| `domain_name` | string | No | User domain name (default `Default`) |

### Response (200 OK)

[TokenResponse](#tokenresponse) — `auth_method` is `password`.

### Error responses

| Status code | Description |
|-----------|------|
| `401` | Authentication failed (invalid credentials) |
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
    { "jti": "...", "origin_ip": "...", "device_type": "...", "os": "...", "last_seen_at": "..." }
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

## GitLab OIDC (federated)

Works only when GitLab OIDC is enabled in `config`. When disabled, `authorize`/
`callback` return 404.

| Method | Path | Description |
|--------|------|------|
| `GET` | `/api/v1/auth/gitlab/enabled` | `{ "enabled": bool }` — decides whether to show the frontend button |
| `GET` | `/api/v1/auth/gitlab/authorize` | `{ "authorize_url": "..." }` — OAuth2 authorization URL |
| `POST` | `/api/v1/auth/gitlab/callback` | Issue JWT from authorization code (10/min) |

### POST /api/v1/auth/gitlab/callback request body

```json
{ "code": "string (required)", "state": "string (required)" }
```

The response is [TokenResponse](#tokenresponse) (`auth_method` is `federated`). On authentication failure, 401.

### Browser and MCP security patch compatibility

The original browser session start is retained across refresh and project rescope. Expired sessions stay rejected on retries, and Redis atomically consumes rotation so concurrent requests have one winner. GitLab login records request origin/device; legacy sessions missing origin require a new login under strict/subnet policies. Logout reports revocation failures instead of claiming success.

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
