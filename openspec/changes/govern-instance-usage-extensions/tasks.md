## 1. Governance

- [x] 1.1 Implement future shortening and calendar-month extension limit across all paths.
- [x] 1.2 Implement durable domain policy and safe authorized request/review lifecycle.
- [x] 1.3 Implement localized schedule, policy and review surfaces with scope fences.
- [x] 1.4 Implement optional common adoption reference with exact UTC calendar-month expiry, unset per-enrollment fallback, fail-closed invalid/elapsed handling, deployment configuration parity and behavior regressions.

## 2. Qualification and operations

- [x] 2.1 Exercise targeted backend and UI behavior and actual runtime smoke.
- [ ] 2.4 Run common-reference adoption behavior/configuration/Helm regressions and direct scheduler acceptance, including no-write rejection and unchanged existing schedules (source tests added; not run by implementation worker).
- [ ] 2.2 Verify deployment safety prerequisites and activate only if safe.
- [ ] 2.3 Update affected architecture and operational documentation and archive change once complete.

## 3. Automatic migration and release

- [ ] 3.1 Package and run canonical schema bootstrap on supported deployment paths before SQL writers.
- [ ] 3.2 Qualify MariaDB and MySQL compatibility, DB-less behavior, and fail-closed verification.
- [ ] 3.3 Qualify and publish version 1.32.7 without including unrelated work.
