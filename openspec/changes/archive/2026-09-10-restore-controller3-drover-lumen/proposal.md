# Restore controller 3 Drover and Lumen

## Why
Restore the missing Drover/Lumen deployment on dms-controller3 (172.30.0.13) using the existing Kolla operator environment at 172.30.0.50.

## What Changes
- Controller 3 has no Drover/Lumen containers, configuration directories or HAProxy service fragments; ports 18011, 18012, 8011 and 8012 refuse connections.
- Both services are enabled and inherit the control inventory group. Controller 1/2 run the same immutable image digests cached on controller 3.
- Standard scoped Kolla prechecks passed (28 ok, zero changed/failed). The Drover default-tag warning does not test the effective digest reference.
- Restore only Drover/Lumen on controller 3 using the existing role packages, credentials, images and datastore settings. Preserve unrelated services and existing user work.
- Bootstrap and bundled PostgreSQL delegate to controller 1. Its config files and Drover secret directory exist; PostgreSQL image, bind address and persistent volume match desired settings.

## Completion criteria
Scoped deployment succeeds; migrations complete; controller 3 API and worker containers remain running; readiness/dependency checks and HAProxy/VIP HTTP paths pass. Record gaps honestly. No new source build, release, commit, or main merge is part of this operational restoration.

## Independent review
Recovery reviewer conditionally approved the scope after requiring controller 1 mount-file checks, image compatibility, PostgreSQL volume/bind/image comparison, and HAProxy inclusion. All four conditions were checked before deployment; final verification remains pending.
