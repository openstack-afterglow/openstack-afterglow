## Context

The reported localhost3080→8000 BFF calls authenticate first-party identity but downstream Lumen action gates return403. A real running-container/Keystone probe found a direct system:all admin grant for the affected owner while Lumen's effective=True lookup returns false. Drover and an occasional preflight denial must be investigated independently. Shared worktrees are dirty/conflicted; isolated dev clones and unchanged private runtime configuration are mandatory.

## Goals / Non-Goals

**Goals:** Accurate native system grant verification, distinct401/403 feedback, settled chat permissions, valid DEFAULT debug configuration and useful secret-safe logs, actual local runtime/browser proof, followed by the owner-authorized immutable release and canonical Kolla production verification.

**Non-Goals:** Granting roles, relaxing tenant/service action policies, credential/key rotation, broad retry/fallback behavior, unrelated shared UI/IAM changes, schema/storage migration, HTTP debug traceback exposure or raw transport logging.

## Decisions

- Read direct system assignments without Keystone effective expansion and expand the already validated current role-ID DAG locally. Current effective project membership reads remain unchanged. Native raw project/domain admin labels and API keys never become global administrators. This repairs evidence-backed discovery rather than granting authority.
- Treat downstream403 as service authorization denial, not browser-session expiry. Existing first-party401 recovery stays authoritative. Permission promises must transition to success or explicit error and be fenced against project changes.
- Parse only valid TOML DEFAULT.debug booleans and preserve environment precedence. Lowercase true is the required TOML syntax. Debug increases existing application logger verbosity/source context, retains credential filtering and suppresses dangerous third-party wire logging; it does not set FastAPI debug exception responses.
- Reuse existing config rendering, redaction, request IDs and locale patterns. Parent integrates root architecture/changelog/OpenSpec and final qualification after independent edits. No shared worktree changes.

## Risks / Trade-offs

- Current granular service policies intentionally deny unverified project/domain admin and missing service leaves → preserve those denials; distinguish them from the confirmed direct-system lookup defect.
- Debug can expose credentials via exception text or transport libraries → keep wire loggers quiet, sanitize structured/exception data and prove sentinel secrets remain absent.
- Local source/runtime drift and persisted encryption keys → identify actual source/image and private config paths before rebuilding only affected services; retain named volumes and keys.
- CORS rejection may be a distinct origin mismatch → prove origin metadata before changing any allowlist. Do not add wildcard credentials.
