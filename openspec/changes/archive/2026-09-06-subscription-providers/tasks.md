## Implementation Tasks

- [x] Add Lumen provider subscription columns, auth-attempt model, additive migration, and manifest checksum.
- [x] Add secret-free provider auth references, subscription credential resolution, and canonical model helpers.
- [x] Implement ChatGPT device authorization and Claude setup-token subscription service with row locking and generation checks.
- [x] Expose administrator subscription auth start, poll, cancel, token, and disconnect endpoints with no-store responses.
- [x] Add subscription-specific safe errors and sanitize provider validation responses without leaking submitted secrets.
- [x] Implement request-scoped subscription logging that cannot retain prompts, tokens, account identifiers, headers, raw responses, exception text, callback payloads, or error-log payloads.
- [x] Implement request-local ChatGPT Responses transport with guarded completion and streaming semantics.
- [x] Propagate provider auth references through completion, durable execution, graph, title, memory, advisor, and compaction paths.
- [x] Reject subscription credentials from embedding and managed-search provider paths.
- [x] Enforce subscription model canonicalization, duplicate locking, discovery, pricing, and capability rules.
- [x] Extend Afterglow provider administration with experimental shared-subscription warnings and lifecycle modals.
- [x] Extend Afterglow Lumen proxy contract coverage for subscription auth methods, bodies, errors, and no-store headers.
- [x] Add focused Lumen tests for subscription auth, transport, concurrency, secret boundaries, routing, and execution propagation.
- [x] Run focused and cross-cutting Lumen unit, contract, integration, and migration verification.
- [x] Add Afterglow UI tests for form switching, polling lifecycle, late responses, errors, and opaque model IDs.
- [x] Run focused Afterglow frontend and BFF tests, Lumen target, design guardrail, and full test gate.
- [x] Smoke-test the responsive administrator flow at 390×844, 900×900, and 1440×900 without claiming fixture auth as live OAuth.
- [x] Document any unavailable live subscription-account prerequisites, then archive the completed OpenSpec change.

## Verification Notes

- Responsive browser smoke verification used a local API fixture with synthetic administrator and provider records. It did not authenticate against OpenAI or Anthropic.
- Live ChatGPT device authorization and Claude subscription-token validation remain unexercised because no dedicated, non-personal subscription accounts were available. No workstation or user credentials were read.
