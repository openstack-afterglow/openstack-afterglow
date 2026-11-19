## Why

Users must call Lumen directly from the official OpenAI, Anthropic and Google GenAI SDKs. The dashboard shows Codex and Claude Code setup but has no copyable SDK examples, and the docs have no runnable tutorial covering all three SDKs, billing and key limits.

## What Changes

- Add `docs/lumen-sdk.md` (Korean) and `docs/en/lumen-sdk.md` (English) with key issuance, environment variables, OpenAI/Anthropic/Google GenAI examples in Python, JavaScript and curl, provider selection with `X-Lumen-Provider`, billing, model-only key limits, error codes and the separate legacy `/v1/claude-gateway` path.
- Ship runnable examples in `docs/examples/lumen-sdk/{python,node}/`, `curl.sh`, a README and `smoke.py`, which reads `LUMEN_API_KEY`/`LUMEN_BASE_URL` and runs every configured example.
- Expose the already validated public `[services] lumen_external_url` in public site config and add an SDK examples panel (OpenAI/Anthropic/Gemini × Python/JavaScript/curl) to the API keys area. The panel is hidden when the URL is unconfigured.
- Align Gemini list/generate/stream examples with the Lumen Gemini compatibility routes (`v1beta`, `x-goog-api-key`, `countTokens` 501).

## Capabilities

### New Capabilities

SDK tutorial, runnable examples and the dashboard SDK examples panel.

### Modified Capabilities

Public site config adds `lumen_external_url` (the same credential-free value embedded in the installers).

## Impact

Backend site config response and installer test, `ChatApiKeysManager`, new `ChatSdkExamples` component and tests, nine `chat-settings` locales, Jekyll docs, `ARCHITECTURE.md`, `docs/api/chat.md`, `docs/user-guide.md`, changelog. No new endpoint, schema, dependency or configuration key.
