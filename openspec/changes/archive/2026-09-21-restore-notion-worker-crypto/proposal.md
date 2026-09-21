## Why

The production Notion synchronization worker is running but every cycle fails before API-key decryption because the worker-only dependency set omits `afterglow-crypto`. The repository already owns the package under `services/afterglow-crypto`; making that source authoritative and proving it exists in the built worker image restores synchronization without weakening encryption or introducing a second crypto implementation.

## What Changes

- Resolve `afterglow-crypto` from the repository-owned `services/afterglow-crypto` package for backend and worker environments.
- Include the crypto package in the worker-only dependency group used by the production image build.
- Add an image-level smoke contract that imports the package and exercises the Notion configuration encryption/decryption boundary inside the final worker image.
- Document the package ownership, image build invariant, and production recovery verification sequence.
- Build and publish a Linux amd64 worker image, roll it out through Kolla-Ansible, and verify the running digest plus an advancing live Notion synchronization timestamp.

## Capabilities

### New Capabilities
- `notion-worker-runtime`: Defines the worker image dependency, encryption, publication, and live synchronization recovery contract.

### Modified Capabilities

None.

## Impact

- Dependency metadata and lock state: `backend/pyproject.toml`, `backend/uv.lock`
- Worker image and image smoke tooling: `Dockerfile`, `scripts/`, `package.json`
- Operational contracts: `ARCHITECTURE.md`, `docs/deployment.md`, `CHANGELOG.md`
- Production: `ghcr.io/openstack-afterglow/afterglow-worker`, `/etc/kolla/config/afterglow/globals.yml`, and the `afterglow_notion_worker` containers on DMSLab controllers
- No API, database schema, encryption format, or stored ciphertext change

## Verification evidence

- Published worker manifest: `ghcr.io/openstack-afterglow/afterglow-worker@sha256:3936ad2543c088a0db7b2a1068401858be578ade9139fde8290c450ee79fd09e` (commit `51d7e818`, Docker Build & Push run 35623925700).
- Image smoke against the published digest: `afterglow-crypto=0.1.1`, module resolved at `/app/.venv/lib/python3.12/site-packages/afterglow_crypto/__init__.py`.
- Kolla rollout from `/etc/kolla` (`prechecks` then `reconfigure`, `--tags afterglow`): 0 failed hosts.
- `dms-controller1/2/3` `afterglow_notion_worker`: pinned digest, image id `sha256:b824c430331db039f1060c040b6399e83406fd508f9ee31f8dc3d7cb37d9e648`, `running`, restart count 0, zero `ModuleNotFoundError` after restart.
- Live cycle: `Notion target 1 동기화 완료 (instances=40)` on all three controllers; `notion_targets.last_sync` advanced to `2026-09-21T16:26:54` after the 16:24 restart.
- Unchanged surfaces: `afterglow_backend`/`afterglow_frontend` remain `v1.21.0` and healthy; public frontend 200 and `/api/v1/health` `{"status":"ok"}`.
