## Why

`/admin/database-instances` currently embeds the generic `mysqld_exporter` Grafana dashboard. That dashboard observes the MySQL servers operating the OpenStack control plane, not tenant databases provisioned by Trove, so the resource screen presents unrelated infrastructure metrics. Separately, the admin all-project Trove helper converts every management API failure into an empty list, making an unavailable or malformed management request indistinguishable from a cloud with no tenant databases.

## What Changes

- Fetch the admin inventory from Trove's authenticated `/mgmt/instances` API through the database service proxy and preserve each instance's owning project ID.
- Propagate Trove management-list failures to the API boundary instead of returning a false empty inventory.
- Render an explicit load error on the admin page and display the owning project for each tenant-created Trove instance.
- Remove the infrastructure `mysqld_exporter` dashboard from the Trove resource page; keep it only under the dedicated administrator monitoring surface.
- Add backend/frontend regressions and update architecture, database API, and release documentation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `admin-trove-instance-inventory`: the administrator database resource page represents tenant-created Trove instances only, including project ownership, and distinguishes lookup failure from an empty inventory.

## Impact

- Backend: `backend/app/services/trove.py` and existing database API tests.
- Frontend: `/admin/database-instances`, its observable rendering tests, and the `DbInstance` project field.
- Documentation: `ARCHITECTURE.md`, `DESIGN.md`, `docs/api/database.md`, and `CHANGELOG.md`.
- No database schema, dependency, deployment, or OpenStack service configuration change. The standalone `/admin/monitoring/mysql` infrastructure dashboard remains unchanged.
