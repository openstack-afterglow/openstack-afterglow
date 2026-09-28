# Release readiness regressions

## Why

Before the 1.28.0 release, close observed consumer-visible gaps in the integrated Glance/Dockerfile importer and usage-report UI without changing API or ownership boundaries.

## What Changes

- Preserve Glance image protection in list and admin update projections.
- Make Dockerfile lint honor the same parent base-image precondition as plan/build, keep valid rows following an invalid `FROM`, and keep inline Glance resolution off the event loop with safe upstream failure reporting.
- Publish the usage report without waiting for optional full inventory; hide normalized full compute/storage values when strict quota availability is false, compute sub-GB RAM utilization from unrounded values, and prevent late responses from a previous project from painting the current view.
- Update API/architecture/release documentation and behavior-focused regressions in the existing test modules.

## Boundaries and verification

This change does not add services, migrations, public endpoints, colors, or new feature policy. Local focused tests must fail on the pre-fix defects and pass afterward; run layers/storage/instances/design targets, frontend checks, the mandatory repository gate, and exercise the actual responsive usage-report route in a browser. Production OpenStack authentication, release image publication, and Kolla rollout are separate release acceptance boundaries; tests cannot substitute for them.
