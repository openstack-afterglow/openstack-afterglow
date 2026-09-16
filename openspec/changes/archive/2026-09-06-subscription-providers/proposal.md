## Why

Afterglow administrators need to connect shared ChatGPT and Claude subscriptions to Lumen's existing provider catalog so registered models work through the web chat and compatibility APIs. The integration must remain explicit and experimental because provider terms, account entitlements, and credential lifetimes do not establish official third-party support.

## What Changes

- Add Lumen provider authentication modes for ChatGPT device authorization and administrator-supplied Claude subscription tokens.
- Encrypt subscription credentials in Lumen's database, track connection generation/status, and add single-attempt device authorization state.
- Add fail-closed administrator authentication APIs with initiator binding, no-store responses, safe validation errors, refresh rotation, and stale-request protection.
- Add request-local LiteLLM logging and ChatGPT Responses transport boundaries that never use host credential files, environment fallbacks, or process-global logger mutations.
- Canonicalize subscription model IDs, preserve static discovery/pricing/capability behavior, and propagate only secret-free provider references through durable execution.
- Extend Afterglow's provider administration UI with explicit experimental/shared warnings, responsive connect/reconnect/disconnect flows, and opaque model ID handling.
- Preserve Afterglow as authenticated UI/BFF only; Lumen continues to own authentication, encrypted storage, execution, refresh, and provider failure handling.

## Capabilities

### New Capabilities

- Shared ChatGPT subscription providers using bounded OAuth device authorization.
- Shared Claude subscription providers using validated `claude setup-token` credentials.
- Secret-safe subscription execution through Lumen's native completion, streaming, durable-run, title, memory, advisor, and compaction paths.

### Modified Capabilities

- Provider and model administration expose authentication mode and subscription status without exposing credentials.
- Provider discovery, model canonicalization, pricing, capability gates, and runtime routing distinguish API-key and subscription providers.
- Afterglow provider administration supports subscription setup and lifecycle actions across mobile, tablet, and desktop.

## Impact

Lumen gains an additive migration, provider-authentication service, administrator endpoints, transport adapter, and execution-path parameters. Afterglow gains frontend composition and BFF contract coverage only. Existing API-key providers and model IDs remain compatible. No deployment flag, provider account login, production rollout, secret-volume change, Kolla setting, or automatic entitlement claim is included.
