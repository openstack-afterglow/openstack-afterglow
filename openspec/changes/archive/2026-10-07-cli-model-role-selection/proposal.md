## Why

The published installer asks for raw model IDs and maps every Claude family to one model. Users need the server's provider-grouped inventory and independent role assignments rather than remembering IDs or silently losing the distinction between Fable, Opus, Sonnet and Haiku.

## What Changes

- Fetch the authenticated Lumen `/v1/cli/models` catalog after hidden key input; show real provider groups, public names and known capability/price metadata. Reject incomplete/unavailable catalogs before any persistent change.
- Independently select Codex Sol/Luna and Claude Fable/Opus/Sonnet/Haiku targets, including cross-provider targets supported by the server's compatibility transports.
- Use native Claude family variables and honest picker labels. Let users choose the startup family without collapsing other families to it.
- Generate native Codex default/Sol/Luna profiles and a selected-model catalog so both role slots replace the built-in choices in the CLI picker. Preserve explicit model/config/profile overrides.
- Preserve private key storage, trusted TLS, safe path checks, encoding, backups, marker reruns and unrelated desktop defaults. No permission bypass, paid model calls during installation or personal-file changes during development.
- CLI profiles use an installer-owned `model_providers.lumen-cli` table so desktop provider headers are not inherited; Claude `X-Lumen-Provider` custom headers refuse setup. The terminal `codex` function applies its defaults only where Codex 0.160 accepts them.

## Capabilities

### New Capabilities

- Provider-grouped authenticated installer model selection and independent six-slot model assignments.
- Exact server-issued route tokens distinguish identical public model IDs across different provider connections.

### Modified Capabilities

- Local CLI setup uses server catalog choices instead of manual model ID prompts and a single shared Claude model.
- CLI guides, four-language UI text and setup evidence describe model-list API requests separately from paid inference.

## Impact

The isolated dev worktree is `/Users/pieroot/code/afterglow-cli-model-roles`, based on origin/dev `ec5894c`. The companion Lumen change is `cli-model-role-routing` in `/Users/pieroot/code/lumen-cli-model-roles`; Lumen must be deployed before this installer (an older Lumen returns 404 and setup stops unchanged). Existing production remains untouched. Claude Code 2.1.257+ and the tested Codex 0.160.0 native catalog/profile interface are the target. Role labels are user-selected positions, not measured model size or quality claims. Shared contract: `local://cli-model-role-selection-contract.md`.
