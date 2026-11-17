# Explicit managed sandbox tool selection

## Purpose
Let an authenticated user select exact approved local sandbox tools from MCP managed-profile cards and the chat composer. Sending a selected tool set automatically enters the native run-scoped sandbox lifecycle; the user never provisions a cluster or copies credentials into a Pod.

## Native contract
`ChatFeatureOptions.tool_policy.enabled_sandbox_tools` is an explicit list of at most100 unique canonical manifest tool names matching `^[A-Za-z][A-Za-z0-9_]*$`, length1..128, default[]. Profile IDs, remote MCP IDs and display labels are not tool identities. Empty selection allocates no sandbox. Native admission rechecks current authority, runtime, pinned manifests and quota, then uses existing waiting_resource/readiness/release intents. History reads never provision. OAuth/cloud credentials remain on the trusted worker path.

## UI requirements
- Per-profile and per-tool selection on managed cards and the existing chat tool menu.
- Persist only canonical selected names in the normal scoped preference-store pattern, isolated by user, credential home, working domain and project.
- Keep unavailable selected names visible; block SEND with an actionable error until explicitly removed. Never silently drop or implicitly enable all tools.
- Fresh availability preflight and exact logical owner/selection-revision fencing for new SEND, regenerate and temporary runs; failed preflight preserves the input draft. Native historical retry keeps `{}` and revalidates the source run's frozen features rather than injecting current preferences; local saved-submission retries also preserve their originating snapshot.
- Preserve separate remote enabled_mcp_ids, custom HTTP tools, skills and existing request/idempotency ownership.
- Readiness comes from actual managed metadata, never catalog presence. Runtime-unknown, unavailable and unselected remain distinct.
- All messages use the existing nine-locale catalog and incumbent form/menu primitives. No manual SSH/cluster controls or lifecycle API calls.

## Acceptance
Focused preference-store, gallery/picker, ChatPanel/ChatInput, request-contract and owner/permission-race tests; source type/i18n checks and actual desktop/mobile component proof. Native lifecycle acceptance belongs to SelectedSandboxLifecycle and exact integrated qualification belongs to the coordinator. No production or sandbox runtime enablement is authorized in this worktree.

Implementation interface: `local://selected-sandbox-ui-contract.md`. Native authority: `local://selected-sandbox-contract.md`.
