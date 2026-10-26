# Repair administrator group user lookup

## Why
Administrator groups can load existing members while the domain membership-candidate request fails with `Keystone role operation rejected`; the search then incorrectly announces no matching users. Name-only search/results and members without full UUID cannot disambiguate identical usernames from different home domains.

## What Changes
- Trace and reproduce the failing native domain-directory candidate path; retain fresh, enabled home-or-proven-joined authority and strict selected-domain/group ownership.
- A specifically confirmed absent candidate user may not poison unrelated display candidates, but absent identity is never assignable. Provider denials, unavailable authority, malformed metadata and unknown domain errors remain errors. No global directory fallback, permission grant, or production/native mutation.
- Independently publish member/candidate lookup states. Loading/error is not empty; expose deliberate candidate retry and block stale candidate mutations.
- Search by trimmed case-insensitive name/email/full UUID; show name, email, full UUID and home domain for existing members and candidate results. UUID remains identity and mutation target. Reuse existing tokens/primitives and every supported locale.

## Verification and preservation
Meaningful failing-before/passing-after backend and component/controller regressions; actual Uvicorn/SDK or actual service HTTP smoke with synthetic native boundaries; compiled browser duplicate-user, search/error/retry, exact UUID and responsive verification. Focused selectors then related identity target, i18n and isolated canonical gate. Preserve shared index/review marker, concurrent work, private configuration, datastore/native IAM/resources and existing services. No commit/push/deployment. Update architecture, API/testing/design details and archive with evidence boundaries.
