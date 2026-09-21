## Why

Lumen's immutable message graph is the audit record, but normal resume/history reads should follow only the selected branch. Reconstructing that path recursively for every read makes pagination and branch changes expensive and leaves Afterglow without a safe bounded-window contract. Lumen also needs protocol-native OpenAI Responses and Anthropic Messages surfaces plus an independent Claude Code device authorization flow without moving credentials into Afterglow.

## What Changes

- Add an authoritative, transactionally maintained active-path projection while preserving every historical message and run.
- Replace recent/numeric message paging with revision-fenced opaque cursors and explicit `latest`/`first` anchors. **BREAKING**
- Make Afterglow retain at most three 40-message pages with explicit first/previous/next/latest actions, stable prepend position, stale-response fences, and live-edge recovery.
- Expose OpenAI-native `POST /v1/responses` plus Anthropic-native Messages and token-counting contracts. Preserve caller-supplied positive token/thinking budgets and exact protocol stream shapes.
- Add an independent Claude Gateway base with public OAuth device issue/poll, Keystone-authenticated approve/deny through Afterglow, fixed compatibility scopes, and one-time issuance of a hashed 24-hour API key.
- Add an Afterglow public authorization shell, post-login return handling, discovery-owned Claude Code connection guidance, and responsive browser behavior.
- Update migration, deployment, API, integration, security, design, and architecture documentation in both repositories.

## Capabilities

### New Capabilities

- `conversation-active-path`: indexed selected-branch projection, transactional writers, immutable history, migration/backfill, and integrity repair.
- `conversation-keyset-history`: signed revision-fenced paging in both directions and server-provided sibling branch metadata.
- `native-compatibility-protocols`: OpenAI Responses and Anthropic Messages/count-tokens request, response, error, and streaming contracts.
- `claude-gateway-device-auth`: public device authorization, protected approval, poll throttling, one-time consumption, and expiring fixed-scope credentials.
- `afterglow-history-and-gateway-ux`: bounded transcript navigation plus login-safe Claude authorization and discovery-based setup guidance.

### Modified Capabilities

None. This repository keeps no promoted `openspec/specs` layer; current contracts are documented in the root architecture and `docs/`.

## Impact

Implementation spans the `dev` branches of Lumen and Afterglow. Lumen owns MariaDB migrations/models, active-path writers/readers, cursor signing, protocol adapters, device grants, issued key hashes, discovery, configuration, and deployment assets. Afterglow owns the authenticated BFF, bounded browser window, branch controls, public verification shell, login return marker, and settings guidance. Afterglow does not store provider or Gateway credentials. Existing unrelated staged Afterglow work remains untouched.
