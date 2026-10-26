## Why

GitLab documents different group claims in the signed ID token (`groups_direct`) and UserInfo (`groups` plus role-specific names). The operator needs to observe actual claims with a separate newly issued client before deciding Keystone group mappings. Discovery proves advertised capabilities, not per-user membership or Apache/native transport.

## What Changes

- Add a standalone operator CLI with a loopback-only GET `/callback` and a one-use browser-bound start URL. Register `http://127.0.0.1:8765/callback` in a separate Confidential GitLab OAuth application with `openid profile email`.
- Use authorization code + PKCE S256, random state/nonce, HttpOnly SameSite=Lax browser binding, exact issuer/same-origin HTTPS endpoints, no redirects, bounded responses, and verified RS256 ID tokens. Fetch UserInfo separately and require identical `sub`.
- Keep ID-token/UserInfo group claim presence, JSON type, and exact values separate. Never merge missing/empty claims or promote diagnostic observations into authority. Build only explicitly labelled candidate Keystone mapping input from a selected source; reject ambiguous delimiter/control characters.
- Read the client secret through getpass or a private file. Write exclusive 0600 diagnostic artifacts in an operator-selected directory or a newly created private directory outside the repository; never save tokens, authorization codes, nonce/state, client secret, or arbitrary claims. Do not serve reports over HTTP.
- Document the new client setup, actual CLI invocation, report interpretation, current `OIDC-` source mapping versus possible Apache `HTTP_...` transport, and read-only offline `mapping_engine` checks.

## Capabilities

### New Capabilities

- Local, single-run GitLab group-claim diagnosis independent of application login, SQL, Redis, native identity provisioning, and production listeners.

### Modified Capabilities

- None. Existing `/api/v1` routes, authentication, provider registry, native mapping digest, groups/roles/projects, schema, and deployment remain unchanged.

## Impact

New operator script, focused backend pytest coverage, and operator documentation. Reuse installed httpx/PyJWT/cryptography dependencies without importing application configuration. Validate a signed synthetic provider over real loopback HTTP and report live-human acceptance separately. The new client/secret and a human authorization are intentionally provided after delivery; no existing secret is read or renewed. Preserve all concurrent worktree/index/private configuration state; no commit/push/deploy/IAM mutation.
