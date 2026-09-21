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
