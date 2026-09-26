## Why

The previous provider-only rollout verified basic hotplug/reboot connectivity but did not assert Pod policy-route presence after reboot. The user now requires that gap to be closed, real provider-network cluster and LoadBalancer behavior after secondary NIC attachment to be verified, and the verified release merged and deployed through Kolla Ansible.

## What Changes

- Fix the owner of the priority 29999 Pod-CIDR main-table rule so it survives boot and network reconfiguration without depending on a polling recovery window.
- Preserve the existing metadata/MAC-based provider NIC pin, secondary-NIC connected-subnet-only routing and DNS/RA isolation.
- Extend the prior real lifecycle probe to assert routing rules, cross-node Pod/API traffic, provider node addresses, and actual Kubernetes LoadBalancer/Octavia creation and data-plane success before and after secondary NIC attachment and reboot.
- After full gates and supported architecture builds/runtime proof, bump affected release versions, merge reviewed dev-to-main PRs, publish immutable artifacts and deploy via the existing Kolla inventory and role integration.

## Capabilities

### New Capabilities

None; this closes correctness and verification gaps in the provider-only cluster contract.

### Modified Capabilities

- Persistent K3s Pod routing and live network lifecycle verification.
- Verified Afterglow/Drover release promotion and Kolla deployment.

## Impact

Drover owns guest bootstrap/network behavior; Afterglow owns release integration and user-visible BFF verification. Preserve all unrelated local work using an isolated Afterglow worktree, production secrets, storage, inventory, and rollback references. The user explicitly authorizes this task's dev-to-main PR merges, version bumps, and production deployment. Do not repair unrelated compute-host uplinks or MTU configuration. Test VMs may be placed on healthy hosts as in the prior run. No assertion of live Fedora CoreOS coverage without actually exercising it.

## Outcome (2026-09-26)

- Root cause of the reboot gap: systemd-networkd removed the unmarked priority-29999 rule as a foreign rule on provider NIC reconfiguration. Drover `v0.2.24` marks it `protocol kernel` (Ubuntu) and persists it on the pinned NetworkManager profile (FCOS).
- Enabling OCCM exposed six more defects, all fixed in Drover `v0.2.24`: wrong SDK app-credential signature in reconciliation; guest auth against the unreachable internal Keystone; provider network rendered as both internal and public (removed `InternalIP`); K3s ServiceLB competing with OCCM; agents missing `cloud-provider=external`; OCCM Service LBs orphaned on cluster delete. HA joiners with OCCM aborted bootstrap and now reuse the `cloud-config` Secret.
- Shared infrastructure: the Octavia controller client certificate expired 2026-09-09; with user approval it was renewed with the existing client CA and key (canonical `kolla-ansible octavia-certificates`, then `reconfigure --tags octavia`), valid until 2027-09-26.
- Afterglow releases as `1.26.0` (MINOR, because `v1.25.0..dev` adds the VM resize endpoints) with the operator lock and backend Drover SDK pin promoted to `v0.2.24`.
