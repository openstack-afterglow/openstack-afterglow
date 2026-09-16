## 1. Credit Presentation

- [x] 1.1 Add a typed provider-credit view that distinguishes account balance, API-key limit, unavailable lookup, and official-API unsupported states.
- [x] 1.2 Render a separate responsive `계정 크레딧` group with exact DeepSeek and OpenRouter scope labels and trusted billing actions.
- [x] 1.3 Render explicit non-numeric credit states for OpenAI, Anthropic, Gemini, and other providers without documented balance data.

## 2. Behavioral Coverage

- [x] 2.1 Extend focused provider-page tests for provider-reported balances, key-limit provenance, unsupported balance APIs, lookup failure, and HTTPS-only actions.
- [x] 2.2 Verify the actual provider surface at mobile, tablet, and desktop cutovers in light and dark themes.

## 3. Documentation and Verification

- [x] 3.1 Update architecture, chat billing documentation, and changelog with the account-credit scope and official API limitations.
- [x] 3.2 Run focused frontend checks, the architecture guard, and the project gate.
