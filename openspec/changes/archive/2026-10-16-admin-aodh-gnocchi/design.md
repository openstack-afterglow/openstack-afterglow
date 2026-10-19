## Context

Existing native_telemetry reads caller-scoped measurements for resource monitoring; it does not own alarm definitions or service administration. The existing system-admin guard and caller SDK session remain authoritative. Standard console primitives and four locales are required.

## Goals / Non-Goals

**Goals:** Aodh alarm dashboard/history, native definition/action settings and lifecycle; independent read-only Gnocchi diagnostics, archive configuration inspection, resource/metric browsing and bounded measures.

**Non-Goals:** Deploying or configuring native daemons, direct webhook sending, force-state notification tests, SMTP/Slack-specific adapters, new credentials/database/collector, production changes.

## Decisions

- New administrator BFF router under `/api/v1/admin/telemetry`, fresh `require_admin` plus caller `get_os_conn`; catalog `alarming` v2 and `metric` v1. No service-account substitution or native shared cache. All responses/errors are no-store.
- Bounded streamed requests, no redirect/reauth/mutation replay. Each Gnocchi diagnostics section and Aodh history fails independently. Pagination exposes native markers and counts only loaded rows.
- Native rule JSON supports seven upstream types without guessing deployment plugin availability; common resource-threshold fields get guided controls. Exact time constraints/rule remain editable and preserved. Aodh policy validates native semantics.
- Notification actions support upstream HTTP(S), trust HTTP(S), log, Zaqar/trust Zaqar and trust Heat. Aodh capabilities is storage/API capability data, not plugin discovery. Save proves configuration, not delivery. Mail requires a compatible webhook relay or installed Zaqar subscription driver. Injected trust userinfo is removed on read; user-provided trust IDs rejected. No outbound destination probing.
- Gnocchi `/status` backlog and API readability are observations, not proof all metricd/ingesters are healthy. Read-only archive policies/rules/types and paged resources/metrics; bounded raw measurements retain timestamps/granularity/units and measured zero.
- Admin monitoring gets Aodh and Gnocchi siblings, Aodh settings linked from dashboard. Reuse PageShell, semantic states, form/table primitives. Clear private drafts and snapshots on synchronous auth/scope transitions; generation-fence every read/mutation. No local persistence.

## Risks / Trade-offs

- Native deployments vary in plugin/policy support → show confirmed API status independently from upstream method guidance; errors remain actionable, not fake success.
- Alarm actions can trigger delegated external effects → explicit trust warning and deletion confirmation; no automatic retry after uncertain mutation.
- Webhook URLs may embed secrets → no logging/cache/clickable links; whitelist alarm/history output and redact stored trust IDs.
- Large clouds → bounded page views and samples, truncation indicators instead of invented totals.
- Local tests/synthetic native HTTP cannot qualify production evaluator/notifier delivery → report this boundary and operator prerequisites.
