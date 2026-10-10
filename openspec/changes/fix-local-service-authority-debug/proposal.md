## Why

Local Lumen rejects native history/models/extensions and administrator reads with403 despite a valid Afterglow browser session, causing an authentication-failure redirect and chat permission loading that never resolves. Running Lumen/real Keystone evidence confirms a direct system:all admin assignment exists while the current effective=True system lookup reports false; the user also needs explicit, credential-safe debug diagnostics from TOML.

## What Changes

- Correct Lumen's verified native system assignment discovery without granting roles, weakening service action gates, trusting caller role headers, or promoting project/domain admin labels.
- Trace Drover stats403 and the isolated CORS preflight403 separately; repair only confirmed defects and retain genuine entitlement/origin denials.
- Distinguish service authorization403 from first-party authentication401 in administrator/chat UI; settle permission loading with an actionable bounded failure instead of a redirect or permanent spinner.
- Support valid `[DEFAULT]\ndebug = true` in Afterglow TOML with defaultfalse, normal environment precedence and richer safe application/source/decision diagnostics. TOML requires lowercase booleans; invalid `True` is not rewritten. Existing logging settings and secret filters remain.
- Synchronize affected examples/config generation/deployment surfaces, regressions, architecture and existing detailed docs. Prove actual local authenticated behavior/debug logs without changing production role grants, credentials or volumes.

## Capabilities

### New Capabilities

- `safe-default-debug`: Explicit DEFAULT debug controls safe diagnostic verbosity, config precedence and source context without exposing credentials or HTTP exception details.
- `local-service-authorization-feedback`: Valid browser sessions remain intact on downstream service403, chat permission loading resolves, and verified system administrators retain their existing service authority.

### Modified Capabilities

None. Existing authenticated resource/action and least-privilege scope policies remain authoritative.

## Impact

Afterglow config/logging, administrator/chat permission consumers and affected config-generation paths; minimal sibling Lumen authority code where current runtime evidence proves a defect. Work occurs in isolated dev clones; shared conflicted UI and unrelated sibling IAM changes remain untouched. On 2026-10-10 the owner explicitly authorized testing, committing, immutable image publication and canonical Kolla deployment of every change in this conversation, selecting this scope rather than the unrelated shared UI/IAM/migration work. The earlier MCP1.30.8/1.30.9 rollout receipts remain historical evidence, not proof of the new repair. Production cutover uses `/etc/kolla/multinode` with qualified Afterglow and Lumen images and retained rollback/preservation receipts. No schema, credential, role-assignment or storage migration.
