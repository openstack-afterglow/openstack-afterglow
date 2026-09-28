## Implementation Tasks

- [x] 1. Extend activity storage and migration with source/service/request correlation, safe detail and external-event deduplication.
- [x] 2. Capture authenticated Afterglow mutation failures/success and successful login without duplicate explicit records; keep errors and secrets isolated.
- [x] 3. Add opt-in OpenStack notification collector, safe normalization, durable consumer and configuration with clear coverage limits.
- [x] 4. Add system-admin-only global listing, detail and filtered aggregate endpoints with behavioral tests.
- [x] 5. Add responsive admin event viewer navigation, filters, details and service/project failure analysis.
- [x] 6. Exercise changed API/UI paths, update architecture, API/operator docs and changelog; record unverified live/broker coverage.

## Verification

- Focused backend activity/admin-events/native-notification regressions: 96 passed. Auth target: backend 157 and frontend 55 passed. Access target: backend 136 passed.
- Event viewer/navigation regressions: 14 passed. Frontend `npm run check`: 0 errors, 0 warnings. Changed Python files: Ruff lint passed.
- Direct smoke: normalized native failure → SQLite persistence → real FastAPI admin list/stats/detail returned 200, failed count 1, preserved resource ID, no injected secret.
- Chromium visual smoke with disposable HTTP fixtures: desktop 1440×900, tablet 820×900, mobile 390×844; list, analytics, filter submission, native error type/request IDs, detail drawer and rolling-window refresh exercised. No document horizontal overflow at mobile/tablet widths. Fixtures are not live OpenStack evidence; stopped and removed after checks.
- Not exercised: live RabbitMQ delivery/reconnect, real OpenStack event emission, MariaDB migration 083 application, production deployment, full test:gate. Existing Pydantic/FastAPI deprecation warnings and activity test AsyncMock warning remain. No commit/push/archive/deploy.
