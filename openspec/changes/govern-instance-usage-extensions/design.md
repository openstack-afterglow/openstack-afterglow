## Context

Nova metadata holds schedules and a Redis instance lease coordinates expiry writers. Domain policy and review require durable authority independent of client UI. SQL and Nova cannot commit atomically. Multiple shared checkout changes are unrelated and must be preserved.

## Goals / Non-Goals

**Goals:** Future shortening, one-calendar-month-per-extension limit and reason; automatic default or exact-domain manager-configured manual review by live domain manager or exact project owner/admin; safe discoverable request and review UI.

**Non-Goals:** Enforcing policy against independent Nova metadata writers, or treating a pending request as approval or as a pause to expiry.

## Decisions

- Bind requests to exact native domain/project/server, schedule revision and policy revision. Read policy with fail-closed error handling; absent policy means automatic.
- Use durable SQL policy and request records with migrations and exact authority revalidation. Persist a non-replayable applying intent before Nova mutation, confirm exact native readback, and leave ambiguous outcomes for explicit reconciliation. Serialize policy changes, direct extension and decisions with a common lock and the existing per-instance usage lease. Never assume SQL and Nova are atomic.
- Use UTC calendar month clamping measured from the current expiry. Shortening must be in the future and after schedule start. In-flight native lifecycle remains fenced; blocked or complete cannot be shortened to reset execution.
- Preserve both PUT and extend routes without bypasses, including administrative routes. Present pending requests separately from effective Nova expiry; review UI must be reachable to both project administrators and domain managers. Localize reason follow-up notice.
- Production opt-in only after verified deployed cohort, shared coordination, complete impact inventory and recovery checks. Existing expired delete schedules can execute immediately; never infer safety from the configuration flag.

## Risks / Trade-offs

Native metadata lacks CAS and can be altered outside Afterglow; an ambiguous native write must not be retried blindly. Mixed old/new writers can bypass policy; require coordinated rollout and schema compatibility qualification. No pending request guarantees service beyond the existing deadline.
