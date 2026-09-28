## Investigation and implementation

- [x] Recover prior lifecycle and deployment evidence; protect unrelated work.
- [x] Identify and fix rule ownership across reboot and network reconfiguration.
- [x] Preserve provider NIC pin and secondary NIC isolation across supported renderers.
- [x] Enable OCCM through the existing Kolla setting (currently disabled), preserve other plugin settings, and verify real Octavia LoadBalancer behavior.
- [x] Review Main's OCCM SDK app-credential signature fix and prove reconciliation with a real LoadBalancer/Octavia data plane (the source fix alone is not proof).
- [x] Integrate the sibling's guest-auth fix for internal Keystone unreachable from a provider-only NIC; verify guest authentication over an actually reachable path.
- [x] Fix OCCM node addressing, controller ownership, Service LB deletion and HA joiner bootstrap found during live verification.
- [x] Renew the expired Octavia client certificate with the existing CA (user-approved).

## Verification

- [x] Run real provider-only cluster lifecycle with explicit Pod-rule assertions after reboot.
- [x] Add internal NICs and verify provider node IP, cluster/API and cross-node Pod connectivity.
- [x] Create a real Kubernetes LoadBalancer and verify Octavia members and reachable data plane before and after reboot.
- [x] Run full required gates and actual supported-architecture image builds/runtime probes.

## Release and deployment

- [x] Prepare Afterglow `1.26.0` canonical and generated version metadata, frontend lock version metadata, and source-scoped changelog notes.
- [x] Publish an immutable Drover `v0.2.24` with matching distribution version, then review and promote the operator Drover tag and resolved `uv.lock`.
- [x] Main completes final architecture review/stamp after source and release inputs are settled.
- [x] Merge verified dev-to-main PRs and publish the canonical release artifacts.
- [x] Keep OCCM floating IPs that Services asked to retain (review finding): publish Drover `v0.2.25`, then promote the operator lock and backend SDK pin in Afterglow `1.26.1`.
- [ ] Merge the verified `1.26.1` dev-to-main PR and publish its release artifacts.
- [ ] Deploy released artifacts through existing Kolla Ansible inventory.
- [ ] Verify final readiness, authenticated paths, release identity, and a live cluster deletion that keeps a `keep-floatingip` Service's IP while deleting an unannotated one; record evidence and archive.

## Evidence (2026-09-26)

- Drover: PR #27 merged as `cacc2573` (tree-equal to validated dev `15658e81`), annotated tag `v0.2.24`. Local gate 676 passed / 3 skipped, SDK 111, ruff, architecture; `CI` and `Docker Build & Push` green on the dev head. API/worker images built and executed on linux/amd64 and linux/arm64.
- Live (DMSLab, dev images revision `c17f5e6` deployed through `kolla-ansible reconfigure --tags drover` on all three controllers): fresh two-node provider cluster via the authenticated Afterglow API with no manual patches. OCCM initialized both nodes with provider `InternalIP`. Pod→API TLS, cross-node Pod HTTP and OCCM Octavia LB HTTP passed before/after internal NIC attach, after `netplan apply` (rule missing 0/480 and 0/469 samples), and after reboot (0 missing in 682/571 samples while K3s active). The first post-reboot check ran before CoreDNS was Ready; it passed after system Pods became Ready. Cluster delete removed the OCCM Traefik LB (`k3s delete: OCCM Service LB ... fully deleted`) plus VMs, volumes, SG and app credential; remaining project differences belonged to a concurrent Packer build.
- Test-only interventions: owned test VMs and one owned amphora were cold-migrated off `dms-compute3` (known NO-CARRIER uplink). Not verified live: FCOS guests (no `k3s.fcos_image` policy), HA clusters with OCCM (regression test only).
- Afterglow `1.26.0`: PR #84 merged as `a0481469` with annotated tag `v1.26.0`; `test:gate`, PR and tag CI passed.
- Retained-FIP follow-up (2026-09-27): Drover PR #28 merged as `a18f207a` (tree-equal to validated dev `9274ccd3`), annotated tag `v0.2.25`; `CI`, `Docker Build & Push` (dev, main, tag) and `Release` green. Local gate 679 passed / 3 skipped, SDK 111, ruff, architecture. The regression test fails on the v0.2.24 cleanup, which deleted all four OCCM-described IPs. Local API/worker builds for linux/amd64 and linux/arm64 and the published amd64 manifests (`drover-api@sha256:bd42594d45734fd237de0442c5fd9d5506b2096dfa162b7a333aba10cbda1d98`, `drover-worker@sha256:76388aeac83da940d76aad5ca22343e85196f24dece67d2f5e55f16356e02345`, revision `a18f207a`) each kept the retained IP in a fake-connection cleanup. The local API builds served `/v1/health/live` 200 on both architectures. Not live-verified yet: this needs the deployed release.
