## Context

Lumen keeps an immutable parent-linked message graph and an `active_leaf_id`, but normal history reads previously rebuilt the selected branch. Afterglow then received only a recent slice and performed branch interpretation in the browser. Lumen's compatibility surface also lacked OpenAI Responses and a Claude Code-specific authorization boundary.

MariaDB remains authoritative. Redis remains a fail-closed rate-limit/wakeup aid, never cursor or credential storage. Existing historical messages, durable runs, and journal events remain immutable.

## Goals / Non-Goals

**Goals:**

- Make an indexed active-path projection the hot-path source for resume/history reads.
- Keep every writer transactionally consistent with that projection.
- Provide signed, revision-fenced, bidirectional cursor pages.
- Keep the browser at 40 messages per page and at most three pages, with explicit navigation on every breakpoint.
- Preserve reader position and prevent stale pages from crossing conversation, identity, or mutation boundaries.
- Add protocol-native Responses, Anthropic Messages, and Anthropic token counting.
- Add a public-client Claude Code device flow whose approval uses current Afterglow identity/project and whose issued key remains Lumen-owned.

**Non-Goals:**

- Deleting or rewriting the historical graph.
- Making Redis authoritative.
- Implementing every optional field in the upstream OpenAI/Anthropic APIs.
- Persisting Gateway credentials in Afterglow.
- Adding a separate CLI or local credential store; Claude Code is the client.

## Decisions

### Active-path projection

Migration `012_chat_history_path.sql` adds `chat_conversation_active_path` keyed by `(conversation_id, position)`, unique membership by `(conversation_id, message_id)`, and `history_revision`/readiness state on conversations. The migration/backfill walks each active leaf to its root, rejects cycles/missing/cross-conversation nodes, and produces contiguous root-to-leaf positions.

Append, assistant completion, retry, regeneration, fork, and branch selection use shared in-transaction projection helpers. Branch selection takes the conversation/run locks, rebuilds the chosen ancestry, replaces membership, increments the revision, and may descend through the server-selected child path. Normal page reads query only the projection; explicit branch edits may inspect historical parent/child relationships.

### Opaque revision-fenced paging

`GET /v1/conversations/{id}/messages` accepts `limit`, either `anchor=latest|first`, or one opaque `cursor`. Cursor payloads contain version, conversation, direction, position, and history revision and are HMAC-signed with a cursor-specific key domain. The server rejects malformed/cross-conversation cursors and returns 409 when the projection revision changed.

Responses contain root-to-leaf `messages`, `active_leaf_id`, `history_revision`, `has_before`, `has_after`, and opaque `before_cursor`/`after_cursor`. Each projected message includes position and previous/next sibling IDs so clients can request a branch change without loading the graph. `PATCH .../branch` accepts `message_id` plus `descend=true`.

### Bounded Afterglow history

Afterglow requests 40 messages and retains at most three pages/120 messages. 처음/이전/다음/최신 controls are always explicit; scrolling never starts network work. Loading a fourth page evicts the opposite edge. Prepend records the first visible message and restores its viewport position after Svelte renders.

One action owns one request. Selection generation, conversation ID, token/project identity, and local mutation epochs fence every response. Revision 409 produces an alert and exactly one latest reload. A run that completes while the reader is away from latest shows a new-response action instead of moving the viewport. Sending from an old window first resolves latest; the draft is preserved on failure. Branch arrows send the projected sibling ID with `descend=true`.

### Native compatibility protocols

`POST /v1/responses` translates the supported OpenAI Responses input/instructions/tool subset through the existing completion core and emits Responses-native non-stream and SSE events. `/v1/messages` preserves Anthropic-native content/thinking/tool blocks and errors, while `/v1/messages/count_tokens` performs provider token counting without requiring a generation budget.

Provider selection uses one validated route selector; conflicting body/header values fail rather than selecting silently. Explicit positive `max_output_tokens`, `max_tokens`, and thinking budgets are forwarded unchanged. Streaming uses protocol terminal events, periodic Anthropic ping events, no false success terminator after an error, and background draining so client disconnect does not cancel already-admitted provider work.

### Claude Gateway

Gateway routes are mounted under a configured independent base. Public OAuth metadata, `/oauth/device/code`, and `/oauth/token` accept a fixed public client/scopes and return no-store responses. Redis rate limits device admission and Keystone-authenticated approval fail closed when unavailable.

Migration `013_claude_gateway_device_auth.sql` stores only SHA-256 device/user/client hashes, lifecycle timestamps, owner IDs after approval, and the issued API-key reference. Polling enforces interval/slow-down behavior. Successful exchange creates exactly one `chat_api_keys` row with `credential_kind=claude_gateway`, fixed `models:read compat:completions:write` scopes, and 24-hour expiry; the plaintext key is returned once. A consumed grant cannot mint another key and there is no refresh token.

Gateway authentication requires the Gateway credential kind and rejects conflicting `Authorization`/`x-api-key` values. The configured model/provider route overrides the client's alias. Managed settings, models, Messages, and count-tokens live only on the Gateway base.

### Afterglow authorization shell

The public, no-store `/oauth/claude/authorize` route normalizes the eight-character user code, scrubs it from the URL, and stores only the pending code plus a return marker in session storage. Password and GitLab login/project selection use the shared post-auth destination helper. Approve/deny calls the authenticated `/api/v1/chat/claude-gateway/authorize` BFF with current bearer/project.

The settings guide reads compatibility discovery and emits connection instructions only for an advertised Gateway URL. It never invents a base URL or stores the issued key.

### Deployment

Lumen config, Compose, system Compose, Kolla defaults/template, and example config carry Gateway base URL, model, provider, frontend verification origin, and allowed host values. Production validation requires HTTPS for externally visible bases. Afterglow needs no new secret/config transport because its BFF uses existing Lumen discovery and authenticated proxy boundaries.

## Risks / Trade-offs

- Projection drift: central helpers, migration/backfill validation, and readiness fail closed.
- Stale branch cursor: history revision returns 409; Afterglow alerts and reloads latest once.
- Browser memory and viewport jumps: fixed 40×3 window and message-anchor restoration.
- Device-code brute force: short expiry, hashed codes, limited alphabet, Redis rate limits, poll backoff, and one-time consumption.
- Lost token response after consumption: fail closed and require pairing again; never mint a second key.
- Cross-repository skew: discovery is authoritative and the UI exposes unavailable guidance rather than fabricating endpoints.

## Migration Plan

1. Apply Lumen migrations 012 and 013 before starting updated API/workers.
2. Validate projection counts/positions/leaf equality and Gateway columns/indexes.
3. Deploy Lumen API/worker and exercise append, completion, retry, regeneration, fork, branch switch, protocol adapters, and device flow.
4. Deploy Afterglow's coordinated cursor client, bounded transcript, authorization shell, and settings guide.
5. Configure HTTPS Gateway/frontend bases and fixed model route, then verify discovery and a complete Claude Code pairing/inference flow.
6. Gateway can be disabled by removing its base/route configuration; active-path schema remains additive. If projection readiness fails, stop admissions, rebuild from immutable graph state, validate, and resume.

## Open Questions

None.
