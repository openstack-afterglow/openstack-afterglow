## Why

OAuth account cards display a generated client identifier and every project UUID in clear text, unnecessarily exposing identifiers in screenshots and shared screens. OAuth client IDs and project IDs are identifiers, not bearer tokens; avoid asserting they are secrets.

## What Changes

In OAuth connection cards and removal confirmation, display a localized generic OAuth label instead of provider-derived record.name; show approved project names without IDs. Keep status, scope, expiration and observed clients for safe connection identification, exact grant IDs for revoke, API key behavior and authorization unchanged. Never reveal the hidden values in attributes, DOM or confirmation. No credential rotation, new API, storage, schema or release/deployment changes.

## Capabilities

### Modified Capabilities
- OAuth account dashboard minimizes displayed identifiers while preserving connection distinction and revocation.

## Impact

Frontend account component, behavior regressions, design/architecture/testing/changelog. Verify actual UI with synthetic data and preserve shared work/index.
