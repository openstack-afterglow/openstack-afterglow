# Afterglow

**Language:** [한국어](README.md) · English

> Next-generation OpenStack dashboard — Horizon's feature completeness combined with Skyline's modern UX

[![CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/test.yml/badge.svg)](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/test.yml)
[![Docker Build](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/docker-build.yml/badge.svg)](https://github.com/openstack-afterglow/openstack-afterglow/actions/workflows/docker-build.yml)
[![License](https://img.shields.io/github/license/openstack-afterglow/openstack-afterglow)](LICENSE)

Afterglow is an open-source web dashboard for OpenStack clouds. It keeps Horizon's feature completeness and stability while delivering a modern SvelteKit UI/UX, and bundles **k3s-based Kubernetes provisioning** (a Magnum replacement) and a **squashfs/NFS-based Palimpsest library layer** for AI/ML workloads.

## Live service

Afterglow currently runs as the [DMS Cloud research-cloud delivery console](https://cloud.dmslab.re.kr). Its operational flow lets researchers and teaching teams request resources within a project, lets operators allocate them under quota and permission policies, exposes usage, state, and topology, and reuses environments through library layers and snapshots.

The repository implements these operational surfaces:

- **Compute** — allocate Nova VMs with GPU, vCPU, memory, and storage within project quotas, combining images, networks, and keypairs.
- **Kubernetes** — configure k3s control-plane and worker nodes on OpenStack VMs through cloud-init, then track cluster state and workloads.
- **Shared data and libraries** — use Manila CephFS/NFS shares and snapshots; compose squashfs content-addressable immutable AI/ML layers with OverlayFS inside VMs for reuse.
- **Operations and observability** — manage projects, users, roles, quotas, Grafana and Prometheus integrations, and audit logs from one console.

The browser's SvelteKit application calls the configured FastAPI `/api/v1` API base directly, and the backend talks to OpenStack services through `openstacksdk`. SvelteKit is the UI/auth shell, not an API relay. Redis provides cache and session storage. The current architecture source of truth is the [root architecture](ARCHITECTURE.md); see the [Palimpsest layer documentation](docs/palimpsest.md) for domain detail. After code/config changes, run `python3 scripts/check_architecture.py --stamp --summary "<review summary>"` and `python3 scripts/check_architecture.py --staged` to check freshness.


## Features

- **Full OpenStack service management** — Nova · Glance · Cinder · Neutron · Manila · Octavia in a single dashboard
- **k3s cluster provisioning** — deploy k3s directly onto VMs without Magnum (OCCM · Cinder/Manila CSI · Keystone Auth · Barbican KMS plugins)
- **squashfs/NFS library layer (Palimpsest)** — store content-addressable immutable layer chains on Manila shares and compose them with OverlayFS in consumer VMs
- **Monitoring integration** — Grafana JWT embed, Prometheus HTTP SD, automated monitoring security groups
- **Defense-in-depth security** — IDOR guards, HKDF key-separated encryption, kubeconfig audit log, production boot guard

## Quick Start

```bash
git clone git@github.com:openstack-afterglow/openstack-afterglow.git
cd openstack-afterglow
cp afterglow.conf.example afterglow.conf   # set your OpenStack credentials
cp .env.example .env                       # local compose only: replace SECRET_KEY or keep dev-only allow flag
docker compose up -d                 # http://localhost:3000
```

`afterglow.conf` is the only application configuration file. The `AFTERGLOW_ALLOW_INSECURE=1` flag in `.env.example` is only for local Docker Compose development; never set it in Kubernetes or production.

### Public MCP/OAuth

Public MCP is disabled by default. Enable it with `SERVICE_MCP_ENABLED=true`, `MCP_PUBLIC_URL` (the MCP resource URL), and `MCP_OAUTH_CONSENT_URL` (the Afterglow consent UI). A bare origin in `MCP_PUBLIC_URL` resolves to `/api/v1/mcp`. Configure the external OIDC login callback separately with `GITLAB_OIDC_REDIRECT_URI`; MCP client OAuth `redirect_uri` values are managed per client through DCR/CIMD.
For a separate MCP host, the Helm chart routes the resource and `/.well-known` discovery paths to the backend and includes that host in TLS. With raw Kubernetes manifests, add equivalent host, resource, and `/.well-known` ingress routes yourself.

See the documentation below for Kubernetes / ArgoCD / kolla-ansible deployment and full configuration.

## Documentation

📖 Full docs: **<https://openstack-afterglow.github.io/openstack-afterglow/en/>**

| Document | Contents |
|---|---|
| [Root architecture](ARCHITECTURE.md) | Current ownership, runtime, data boundaries, and update rules |
| [Deployment detail](docs/en/deployment.md) | Docker Compose · Kubernetes · ArgoCD · kolla-ansible |
| [k3s cluster](docs/en/k3s.md) | k3s provisioning, node topology, CoreOS migration |
| [API detail](docs/api-reference.md) _(Korean)_ | Complete REST API |
| [Security model](docs/security.md) _(Korean)_ | Authn/authz, IDOR guards, HKDF crypto, audit log |
| [Targeted testing](docs/testing.md) _(Korean)_ | Fast local feature-test target guide |
| [Architecture detail](docs/en/architecture.md) | Historical/domain detail linked from the root source of truth |

Release changes: [CHANGELOG](CHANGELOG.md) · work log: [`openspec/`](openspec/) (`openspec list`, migrated from milestone.md).

## Tech Stack

| Component | Stack |
|---|---|
| Frontend | SvelteKit · TypeScript · Tailwind CSS v4 |
| Backend | FastAPI · openstacksdk (Python) |
| Cache / session | Redis 7 |
| Deployment | Docker Compose · Kubernetes (Kustomize) · ArgoCD · kolla-ansible |

## Development

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload   # backend :8000
cd frontend && npm install && npm run dev                       # frontend :3000
npm run test:list                                               # discover targeted local test lanes
npm run test:target -- auth                                     # example targeted auth/session checks
npm test                                                        # backend unit + frontend full tests
npm run test:all                                                # full pre-commit gate
```

## License

MIT License — [LICENSE](LICENSE)
