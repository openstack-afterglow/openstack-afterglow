## Why

The administrator provider page only renders billing details for OpenRouter and DeepSeek. OpenAI, Anthropic, Gemini, and Perplexity rows therefore show no usage or credit-management path even though Lumen can account for their local spend and their official consoles are required to inspect or purchase credits.

## What Changes

- Consume Lumen's bulk administrator provider-billing endpoint through the existing authenticated `/api/v1/chat` BFF.
- Show Lumen-attributed current-month usage, request count, and token volume for every configured provider.
- Continue showing live provider-reported quota or balance where supported, and clearly label unavailable or unsupported automatic balance checks.
- Add a safe external action to the provider's official billing/credit page and an optional usage-console action.
- Keep provider CRUD usable when billing status fails, and preserve all credential, activation, model, and subscription behavior.

## Capabilities

### New Capabilities
- Unified provider usage, quota/balance status, and credit-purchase navigation in administrator settings.

### Modified Capabilities
- The chat BFF contract moves from one provider billing path to one bulk provider billing path.

## Impact

Changes the admin chat provider UI, its focused tests, the Lumen BFF contract test, `docs/api/chat.md`, `ARCHITECTURE.md`, and `CHANGELOG.md`. No Afterglow database, authentication, or provider-secret ownership changes; Lumen remains the accounting and provider-credential authority.
