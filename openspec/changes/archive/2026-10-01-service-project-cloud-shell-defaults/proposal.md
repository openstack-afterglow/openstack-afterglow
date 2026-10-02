## Why

The desktop Cloud Shell launcher is already in the served frontend, but the local Compose stack mounts a preserved `.local-services/afterglow.conf` snapshot, not the root config the operator updated. Its snapshot lacks Cloud Shell enablement and settings. Cloud Shell also currently requires a global network ID and egress-only security group despite the request for project defaults.

While verifying the rollout, the Cloud Shell Zun client proved incompatible with stock Zun: requests carried no microversion header (Zun served 1.1 and rejected list `command`, typed `mounts`, `tty`, `auto_remove`), the explicit `privileged: false` hit Zun's `RULE_DENY_EVERYBODY` policy, forced delete is admin-only, and keystoneauth's default `raise_exc=True` turned the 404 that proves deletion into an exception, so every cleanup reported failure and kept the user lease. With the user's approval the fix and a live create/delete verification were added to this change.

## What Changes

- Default Cloud Shell API/bootstrap interface to `public`.
- Preserve dedicated-project Zun/Cinder ownership, as explicitly selected by the user. Resolve networking in that dedicated project, never the caller's selected project.
- An omitted/empty network ID resolves the project's existing authoritative default-network policy and provisioning path. Require usable external connectivity and project ownership; do not select arbitrary networks or replace stale defaults.
- Default security group selection to the dedicated project's `default` group. Preserve project isolation; inherit that group's rules without creating a floating IP or changing its rules.
- Keep explicit project-owned network/security-group overrides supported. Network ID and security group are no longer mandatory boot prerequisites when defaults are used.
- Cloud Shell Zun calls send `OpenStack-API-Version: container 1.36`, omit `privileged`, delete with owner-scoped `stop=true`, and pass `raise_exc=False` so the existing status mapping handles 404/409. General Containers UI Zun calls keep their 1.1 contract.
- Synchronize config examples, generated K8s/Helm and Kolla paths.
- With the user's approval: grant the backend service user `member` on the existing `cloud_shell` project, set the local `nova.default_external_network` policy to `private_provider`, retain local secrets/datastore/service settings, apply only the Cloud Shell configuration to the active snapshot, rebuild/recreate backend, frontend and notion-worker, and verify the actual public capability, header entry, default network provisioning and Zun create/delete.

## Capabilities

### New Capabilities

None. Existing Cloud Shell provisioning uses project network defaults and a stock-Zun-compatible request contract.

### Modified Capabilities

Cloud Shell networking/default configuration, Zun request/cleanup contract, and the approved local configuration rollout.

## Impact

Dedicated project, per-user/per-project workspace fingerprints, quotas, authorization, consent, HMAC resource ownership, cleanup and single-user lease semantics stay intact. Default security-group rules replace the former egress-only default requirement by explicit user choice. Under default policies `member` now suffices for the service user; Kolla still grants project `admin`. No change to user/admin sidebar placement or tablet/mobile launcher hiding. No unrelated source/config changes or production deployment.
