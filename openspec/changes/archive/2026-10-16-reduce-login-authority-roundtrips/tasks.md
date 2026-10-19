## Implementation

- [x] Reduce repeated native service authentication and reads within one login, preserving fresh mutation and authorization boundaries.
- [x] Select the final project once and preserve Default reader/projection, legacy, projectless, provider and rescope contracts.
- [x] Eliminate immediate fresh-login /me readiness delay while requiring verification after persistence restore and unverified transitions.
- [x] Add behavior regressions for changed security and session transitions.

## Qualification

- [x] Compare actual SDK/native HTTP before/after calls and latency; exercise full app HTTP with real isolated SQL/Redis.
- [x] Verify compiled browser login, reload validation, invalid/revoked restored session and stale response boundaries.
- [x] Build and run all declared architectures of affected canonical images; deploy isolated canonical Compose and verify readiness/smoke.
- [x] Run exact regressions, auth/access and affected checks; record failures and verification limits truthfully.
- [x] Update architecture/details/changelog and archive with evidence, preserving shared state.
