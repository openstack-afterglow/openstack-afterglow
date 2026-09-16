## Why

Remove docker-compose.test.yml and make docker-compose.dev.yml the sole definition for local development and disposable functional datastores. Its existing test profile currently differs from the functional runner in ports/schema and lacks isolated Redis.

## What Changes

- Align the existing dev test-profile MariaDB/PostgreSQL with the functional contract and add isolated test Redis on loopback 3307/5434/6380.
- Store test data on tmpfs so scoped container teardown needs no volume deletion.
- Run functional lifecycle directly against the dev manifest with explicit test service selection, no dependencies, and scoped teardown; never remove app services, named volumes or orphans.
- Permit credential-free Compose parsing for test-only service selection using empty (not fake/insecure) app inputs. Normal services:up retains its existing private configuration/credential/key validation.
- Remove the standalone test manifest and update commands, tests, rules and documentation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Functional datastore lifecycle shares the canonical dev manifest while preserving separate database/cache and process ownership boundaries. --no-start, --keep, external URLs and failure propagation remain supported.

## Impact

Changes are limited to development/test configuration, runner and its consumers/documentation. Base/prod composition, application APIs, persistent development volumes, existing private secrets and remote OpenStack remain unchanged. Verify clean credential-free test startup, successful and failing test teardown, real datastore tests and current dev startup. Existing upstream Nova 503 is not a local test-profile failure.
