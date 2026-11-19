## 1. Contract

- [x] 1.1 Read Lumen compatibility routes (`X-Lumen-Provider`, `model_route_ambiguous`, `model_not_allowed_for_key`, `domain_credit_insufficient`, image `b64_json`, Gemini embeddings) and the Gemini compatibility contract from LGeminiCompat.

## 2. Documentation and examples

- [x] 2.1 Korean and English tutorials with OpenAI, Anthropic and Google GenAI examples in Python, JavaScript and curl.
- [x] 2.2 Runnable `docs/examples/lumen-sdk` files, README and `smoke.py`.
- [x] 2.3 Link the tutorial from the docs index, user guide and chat API reference; update `ARCHITECTURE.md` and the changelog.

## 3. Dashboard

- [x] 3.1 Public site config returns the validated `lumen_external_url`; pytest covers configured and unconfigured values.
- [x] 3.2 SDK examples panel with provider/language tabs, copy and tutorial link; hidden without the URL.
- [x] 3.3 Nine locales and component tests.

## 4. Verification

- [x] 4.1 `py_compile`, `node --check`, `sh -n` for every example.
- [x] 4.2 Smoke runner against a synthetic local wire server with the official SDKs (not a Lumen instance).
- [x] 4.3 Focused vitest, svelte-check, i18n check/scan, backend pytest selector.
