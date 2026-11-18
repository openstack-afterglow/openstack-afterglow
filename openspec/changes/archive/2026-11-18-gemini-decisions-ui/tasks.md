# Gemini Decisions implementation checklist

Base `dev`: `4f22730fbd01bf368e20a43509cb5e8389d1dab4`.

- [x] Add provider-specific editor, response rendering, validation and input sizing without changing OpenAI behavior.
- [x] Accept `decision` in the native model catalog and registry with input-only prices.
- [x] Bound Decisions BFF requests and preserve native response errors and no-store behavior.
- [x] Cover both providers, Gemini questions/media/limits and the BFF wire contract in tests.
- [x] Localize all added copy; update reference docs and architecture review.
- [x] Run the project gate and collect synthetic desktop and mobile browser proof.

## Verification

- `npm run test:gate` passed with copied local settings withheld: 15,515 backend unit tests, 8,489 Vitest tests, 279 backend contract tests and 301 functional tests. Orchestration: 274 passed, one existing TODO. Kolla: 29 Node and 16 Python tests. CLI: 20 passed (36 skipped). Frontend log runner: 9 passed. Architecture guard, generated catalog freshness and Ruff passed.
- Focused Vitest: 218 tests across six files. Lumen BFF contract: 75 tests; scoped Ruff check and format passed.
- Localization check: nine locales, 59 namespaces, 13,858 source messages, no errors or warnings. Hard-coded Korean scan: zero.
- Chromium against a mocked BFF: 1,440 px desktop and 390 px mobile; verified inline PNG and resolution, all three Gemini answer types, seven probability bars, usage and estimated cost. Nine locale editors fit at 390 px. Screenshots and JSON receipts are under `~/.local/share/afterglow-proofs/gemini-decisions-ui-2026-11-18/`.
- Loopback HTTP: real Afterglow and Lumen source routes forwarded text and an inline image to synthetic Gemini; observed 200 success, 400 safety, 422 unsupported modality and pre-dispatch 413. All were no-store. No live identity, wallet, provider, deployment or charges.
