# Tasks

- [x] Inspect release contracts and wireguard deployment baseline; obtain one-release PR merge authorization.
- [x] Synchronize Afterglow 1.25.0 version sources with the canonical version script.
- [x] Validate, merge, and publish Lumen 0.3.0.
- [x] Validate, merge, and publish Palimpsest 0.2.0 with required native KVM proof (and 0.2.1 hotfix).
- [x] Validate, merge, and publish Drover 0.2.23.
- [x] Validate, merge, and publish Waygate 0.1.4.
- [x] Promote the four immutable service tags and regenerate the operator lock.
- [x] Validate, merge, and publish Afterglow 1.25.0 and its images.
- [x] Verify published image architectures, runtime versions, and revision/digest provenance.
- [x] Preserve rollback inputs and migrate wireguard's legacy role links safely.
- [x] Configure the explicitly authorized Palimpsest production inventory, dedicated credentials/database, persistent storage and endpoint.
- [x] Deploy through standard Kolla Ansible and verify enabled container health/readiness.
- [x] Exercise authenticated dashboard/OpenStack/service paths and document gaps.
- [x] Record release/deployment evidence, update architecture review, and archive the change.

## Evidence (2026-09-25)

### Releases (merged dev→main, annotated tag on the merge commit, tree-equal to the validated head)

| Repo | PR | Merge | Tag | Release |
|---|---|---|---|---|
| Lumen | #14 | `42d6184b` | v0.3.0 | GitHub release + 8 wheels; `Lumen Package Release` and `Docker Build & Push` green |
| Drover | #26 | `96fdf876` | v0.2.23 | GitHub release + wheel; `Release` and `Docker Build & Push` green |
| Waygate | #3 | `39d72477` | v0.1.4 | GitHub release + wheel (manual `gh release create`, workflow publishes images only) |
| Palimpsest | #5 → #6 | `0474b1f6` → `a28224a9` | v0.2.0 → v0.2.1 | `Test` incl. **Required native KVM proof** green on both; Hub images published from v0.2.0 |
| Afterglow | #80 → #81 | `d5d94736` → `44e87f88` | v1.25.0 | Tag workflow green: all Layered Tests, backend/frontend/worker amd64 + Cloud Shell amd64/arm64, manifests |

Palimpsest v0.2.1 is a role-only hotfix (`SSL_VERIFY` rendered as a boolean; `community.docker.docker_container` rejects non-string env). Regression contract added; fails on 0.2.0 source. Hub stays 0.2.0.

### Image provenance and runtime proof

Every production ref is an immutable `@sha256` per-arch (linux/amd64) digest whose manifest `org.opencontainers.image.revision` equals the merge SHA (`scripts/ci/image-revision.js verify`). Runtime proof executed for all 12 images on **both** architectures: published amd64 pulls, published arm64 for Lumen (multi-arch), and native arm64 source builds from the tagged checkout for the amd64-only images. Each container reported its package version and `platform.machine()`; Afterglow API additionally imported `app.main` and ran the arch-correct OpenTofu v1.8.3; the worker passed `scripts/worker-image-smoke.py` (crypto round-trip); the frontend reported `package.json` 1.25.0 on x64/arm64.

### wireguard-dmslab rollout

- Backup before any change: `/etc/kolla/afterglow-release-backups/20260924T231244Z/` (plugin-checkout local patch + HEAD, role links, installed distributions, globals/secrets/multinode copies); git stash `pre-v1.25.0-local-role-edits`. Config files also have `.before-release-20260924T231413Z` copies.
- Legacy `waygate`/`palimpsest` role symlinks removed per `install.sh`'s documented recovery; `uv sync --locked --inexact --no-install-project` installed drover 0.2.23 / lumen 0.3.0 / waygate 0.1.4 / palimpsest-local 0.2.1 (kolla-ansible moved to the lock's pinned 21.2.0). `install.sh` verified all roles.
- `kolla-ansible precheck --tags afterglow,waygate,drover,lumen,palimpsest`: failed=0 on all hosts.
- `kolla-ansible reconfigure --tags afterglow,waygate,drover,lumen`: 27 containers on 3 controllers recreated on the pinned digests; all API tiers healthy.
- Palimpsest: `[palimpsest]` = dms-controller1 (single local `palimpsest_hub` volume); dedicated `palimpsest_kolla` DB/user, Keystone user `palimpsest` (admin on `palimpsest-service`), generated secrets stored only in `secrets.yml` (0600). Public route `palimpsest.dmslab.re.kr` (Cloudflare CNAME → `openstack.dmslab.re.kr`, mirroring the Lumen record) under the existing `*.dmslab.re.kr` certificate. Ports **8021/18021** — the repo sample's 8020/18020 collides with this deployment's Afterglow backend override (`afterglow_backend_port: 8020`, `_listen_port: 18020`; VIP 8000 is Heat). `afterglow_service_palimpsest_enabled: true` set and Afterglow reconfigured.
- Steady state: 29 containers running; every API healthy, restarts=0 except `lumen_worker` (5/5/6), all inside the four HAProxy reconcile windows (VIP unreachable ~20 s; Lumen worker exits on startup DB failure and is restarted by policy). Zero worker errors in the following minutes.

### Authenticated smoke (public API, service account `afterglow_admin` on `afterglow-service`, run on the deployment host)

Login 200 → `/projects/current/permissions`, `/auth/me`, `/dashboard/overview` (Nova quotas) 200; `/dashboard/k3s-stats` `available: true` (Drover); `/chat/models` 29 (Lumen); `/waygate/` discovery via internal VIP 200; `/palimpsest/hub/`, `/palimpsest/hub/health`, `/palimpsest/layers` 200. Public `/v1/health` 200 for cloud/drover/waygate/lumen/palimpsest hosts. Keystone catalog for `palimpsest`: internal/admin `http://172.30.0.253:8021`, public `https://palimpsest.dmslab.re.kr`.

### Gaps and follow-ups

- Palimpsest PyPI publish for v0.2.0/v0.2.1: refused (`invalid-publisher`, no trusted publisher registered for `release.yml` / environment `pypi`). No GitHub release object for Palimpsest. Kolla consumes the git tag, so deployment is unaffected. Requires PyPI project settings.
- Not exercised live: VM create/delete, K3s cluster lifecycle, Waygate gateway VM/handshake, Lumen provider inference, Cloud Shell sessions, Palimpsest layer push/build. These remain read-only/health/catalog verifications.
- `lumen_worker` exits on a startup DB connection failure instead of retrying like the other workers; benign under restart policy but noisy during HAProxy reconciles. Candidate Lumen follow-up.
- Repo sample `globals.afterglow.sample.yml` assigns Palimpsest 8020/18020 while this deployment's Afterglow backend uses those; the live globals now carry the explicit 8021/18021 override.
