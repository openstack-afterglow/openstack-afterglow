## Implementation Tasks

- [x] Trace default titles through generation, persistence and history reconciliation.
- [x] Inspect Perplexity citation payloads through installed LiteLLM and durable storage.
- [x] Diagnose unavailable context metadata, token counting and preview failures.
- [x] Repair title generation and late history metadata updates.
- [x] Preserve actual citations and show message-local source details.
- [x] Provide accessible header history and conversation-source lists at all breakpoints.
- [x] Report remaining context or explicit unavailable reasons without inventing capacity.
- [x] Verify focused regressions, browser interactions and complete relevant gates.
- [x] Update architecture/design/API documentation and prepare completed artifacts for archive.

## Verification Evidence

- Installed LiteLLM 1.93 bridge reproduced three lost Perplexity search-result shapes; all four metadata/annotation variants pass after the Lumen fix.
- Vite-served chat components were exercised with synthetic API data at 298, 390, 767, 768, 1023, 1024 and 1440px. Header actions are 44px, source panels stay inside viewport boundaries, and Escape restores trigger focus. Light/dark and reduced-motion source panels were visually inspected.
- Browser context details distinguish unknown input limit, uncountable attachments and HTTP 503 without leaking provider response text; token-counter fallback displays an estimate and remaining tokens rather than fabricated capacity. Debounce immediately enters loading, avoiding a false unavailable state.
- Browser smoke fixtures and their Vite/Chromium processes were removed/stopped after verification.
- Lumen contract, DB integration and all seven process-stack scenarios passed; details are recorded in Lumen's matching archive.
- `npm run test:target -- frontend:src/lib/components/chat/__tests__/ChatPanel.test.ts`: 18 passed. `npm run test:lumen`: 33 backend contracts and 106 frontend tests passed.
- `npm run check`: 0 errors and 0 warnings after removing the throwaway browser module.
- `npm run test:gate`: passed, including architecture freshness, unit/contract/disposable functional suites and backend lint. Working-tree and staged-baseline architecture guards passed; no files were staged or committed by this task.
- No production deployment or live paid-provider call was performed.
