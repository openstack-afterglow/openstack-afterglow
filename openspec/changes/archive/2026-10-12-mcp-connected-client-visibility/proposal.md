## Why

The account's External AI access screen exposes delegated OAuth/PAT grants but not the MCP software that actually initializes them. Users cannot distinguish a recognized client from unauthorized reuse of a key. The supplied screen also shows an access-list error; failed or unrelated-method lookups must never look like verified zero connections.

## What Changes

- Capture a bounded, durable set of observations from authenticated, valid, successful MCP `initialize` requests: sanitized self-reported client name/version, deterministic browser/agent/bot/SDK inference from clientInfo and User-Agent, and first/last observation times.
- Persist at most ten distinct recent observation signatures on each existing grant with additive nullable JSON migration 087. Store no raw Authorization, bearer, User-Agent, IP, full HTTP body, OAuth secret, or client capabilities. Old grants have no invented identity until observed.
- Expose secret-free observations through the existing owner-user + anchor-project personal-key/OAuth grant endpoints, with no-store response headers.
- Show each grant's observed client identities and timestamps in the existing selected-method account UI. Label all identity as self-reported/inferred, not verified or continuously online. Unknown clients remain unknown; information is never authorization evidence.
- Reuse existing grant/key revocation, credential epoch, OAuth family invalidation, cleanup and audit. A removal revokes the entire credential/grant, including every client sharing it; filtering by spoofable software identity is not an access-control boundary.
- Isolate OAuth/PAT list failures so one unavailable method cannot suppress a successfully fetched other method; failed counts stay unknown and retry remains visible. Keep creation and stale-scope/method confirmation fences fail-closed.
- Preserve the previous instance/storage/Windows work, user's shared index and private configuration. No commit/push, production mutation/migration/deployment, new provider authority, remote fingerprint service, LLM classifier, IP geolocation, or shared Compose/datastore changes.

## Capabilities

### New Capabilities

- `mcp-connected-client-visibility`: user-owned, bounded initialization observations and transparent deterministic software inference for browser/agent/bot/SDK/unknown clients.

### Modified Capabilities

- Account external AI access: accurate independent method loading/error states, connection inspection, and clearly explained credential-wide removal with existing authoritative revocation.
- MCP grant schema/public projection: additive bounded JSON observations; no change to approved permissions, project binding, authentication or resource audience.

## Impact

Backend MCP transport, authority model/projection and browser management response models; migration manifest; account component/tutorial fixtures and four locale catalogs; existing architecture/design/API/security/public-guide/testing/changelog documentation. Pytest covers identity precedence, malformed/secret-bearing metadata, caps/deduplication, authenticated-only observation, revoked/epoch races, owner/project isolation and credential rejection after revocation. Native local MCP SDK/HTTP/SQL and compiled responsive UI prove changed paths without claiming production IAM/client authenticity or continuous liveness.
