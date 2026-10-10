## Why

The administrator project list currently deletes a Keystone project after a simple confirmation without checking its allocated OpenStack resources. Keystone deletion is not a resource teardown and can orphan instances, volumes, networks and service data.

## What Changes

- Add an admin-only fresh resource inspection at `GET /api/v1/admin/projects/{project_id}/deletion-check`, using the validated caller connection and exact target-project ownership. Do not use quota limits or cached dashboard usage as deletion proof.
- Cover Nova servers (including stopped/error/shelved states), server groups, Cinder volumes/snapshots/backups, Neutron networks/subnets/routers/ports/floating IPs/non-default security groups, owned Glance images, and project-bound resources of catalog-present optional OpenStack services supported by Afterglow. Default automatic security groups do not alone block an otherwise empty project; external/shared resources owned by another project do not count.
- Treat denied, failed, malformed or incomplete resource reads as unknown, never zero. Confirmed absent optional services are disclosed as skipped, not silently converted to successful reads.
- Require native admin context (`admin` role and admin-project scope) in the actual request token before any provider read, because Afterglow's administrator flag comes from a separate Keystone assignment and non-admin provider lists can shrink with HTTP 200. Use owner-filtered native administrator APIs for cross-project Trove backups/configurations, Magnum and Heat (ordinary admin index, not default-denied `global_tenant`). Swift/Barbican account/project-scoped inventory requires a verified target-scoped caller token, not a logical project header; provide actionable authority/scope/ownership refusal instead of claiming zero. Trove configuration responses without owners remain unknown.
- The existing DELETE endpoint always repeats the same inspection immediately before Keystone deletion. Resources produce 409; unknown reads produce 503; neither deletes the project. No force bypass or automatic resource teardown.
- In the existing deletion modal, automatically check on open, show progress and resource counts/limited identifying samples, support explicit recheck, and enable the destructive action only after a fully successful empty result. Show final-check failures and refresh the report. Fence responses against changes to selected project/auth scope and modal closure.
- Reuse current UI primitives/semantic styles and update all four existing locales.

## Impact

Afterglow backend project deletion and frontend administrator project-list confirmation only. Preserve the dirty shared tree and unresolved index; no staging, commits, deployment or live cloud mutations. No schema migration required.

Final inspection reduces stale-confirmation races but does not atomically freeze independent OpenStack services: a concurrent creation after the last read remains possible. The UI/docs must not promise a cloud-wide transaction or guaranteed zero-resource teardown.
