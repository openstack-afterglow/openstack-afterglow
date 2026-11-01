## Why

User screenshots show retained GPU selections, an unsearchable long GPU list containing unavailable models, expanded unpinned navigation, and operational events showing only sparse terminal results. Requested behavior is no-GPU baseline, searchable currently eligible domain/project options, fixed Hub/pinned shortcuts with other services hidden by default, and detailed monitoring of login outcomes, intermediate failures, and all button/link interactions.

## What Changes

1. Fresh direct-composition wizard initialization clears only GPU profile/count to none/0 while preserving eligible CPU/RAM draft and durable native/history/unknown-outcome fences. SearchSelect replaces the model native select; show/select only current available model/count/CPU/RAM combinations, retaining invalid current values visibly but never as selectable options. Backend save/create stays fresh.
2. Global navigation drawer displays an always-visible Hub containing incumbent overview destinations and pinned-only shortcuts immediately below it. Other services stay behind a default-collapsed All services disclosure (search can discover them); current route must not auto-expand catalog. Current-service sidebar functionality, authority/service gating, keyboard/mobile and per-user/home/mode preferences remain intact. Hub is not user-unpinnable.
3. Expand existing ActivityLog collection without new schema: source-separated browser observations, server request lifecycle including successful/failed login, diagnostic auth stages, rejected reads/mutations and intermediate errors. Keep event stages/status/correlation/time/HTTP method+route+duration and safe error class/code. Browser click/submit/navigation/client failures use bounded batches and strict structural control metadata; no input values, DOM text, raw URL/query/hash, token, credentials, stack, arbitrary error text, payload or forged actor IDs. API identity comes from existing fresh auth, anonymous observations stay explicitly unattributed; browser events are not trusted business success.
4. Extend admin event viewer filtering, correlation/detail/timeline and collection coverage copy; preserve system-admin and exact scope guards, pagination, unavailable states and existing OpenStack notification limits.

## Capabilities

### New Capabilities
Privacy-preserving platform interaction observation and request/stage correlation using existing event storage.

### Modified Capabilities
VM direct composition choices/default; global navigation Hub/favorites/disclosure; operational event monitoring.

## Impact

Frontend composer/controller/draft; common ConsoleNavigation and localized nav metadata; global interaction collector and admin events UI; backend activity ingestion/audit/diagnostics/event queries and focused tests. Existing primitives/tokens, nine languages and current auth/scope/ABA/unknown fences remain. No native quota, roles, automation opt-in, schema migration or default scheduler changes. No implicit production/shared-datastore deployment. Browser collection is best effort with bounded buffering and explicit provenance; never claim lossless collection or historical backfill. Shared dirty dev/index and runtime state are preserved.
