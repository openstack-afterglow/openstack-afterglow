## Why

Administrators need to distinguish the system monthly default from personal quota overrides, restore users to defaults, understand the credit-to-cost calculation, inspect individual usage, and see account balances only where Lumen can query a documented provider endpoint. The user chat settings route also still embeds the full chat surface instead of completing the approved dedicated settings-page cutover.

## What Changes

- Extend the user quota page with a global monthly-default editor, inherited-state badges, per-user reset, explicit monthly-bounded weekly wording, and credit conversion/cost formula guidance.
- Make each user's usage cells/actions open a responsive detail modal with period selection, model/source aggregates, timestamped ledger rows, and token/cost fields.
- Show OpenRouter and DeepSeek billing snapshots in provider settings; unsupported providers issue no billing request.
- Complete the approved dedicated `/dashboard/chat/settings` page and replace overlay opening with route navigation.
- Update the Lumen proxy contract tests and chat documentation.

## Capabilities

### New Capabilities
- Operator quota-policy controls and usage drill-down in the dashboard.
- Supported-provider balance and usage visibility.
- Dedicated user chat settings route.

### Modified Capabilities
- Quota display differentiates inherited defaults, explicit unlimited overrides, and weekly usage bounded by monthly admission.
- Chat settings navigation no longer mounts a modal over the chat workspace.

## Impact

Changes Svelte components, typed API contracts, route tests, Lumen proxy contracts, and architecture/detail documentation. The generic BFF remains a pass-through and keeps all quota, accounting, and provider logic in Lumen. Responsive behavior is required at mobile, tablet, and desktop widths.
