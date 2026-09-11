---
layout: home
title: English
lang: en
nav_order: 99
has_children: true
permalink: /en/
---

# Afterglow

**Language:** [한국어](../) · English

> Next-generation OpenStack dashboard — Horizon's feature completeness + Skyline's modern UX

Afterglow is an open-source web dashboard for OpenStack cloud environments. It preserves Horizon's stability and feature coverage while adopting Skyline's modern UI/UX. It also ships a **k3s-based Kubernetes provisioning** stack that replaces Magnum.

## Live service

Afterglow currently runs as the [DMS Cloud research-cloud delivery console](https://cloud.dmslab.re.kr). The live service connects resource requests from researchers and teaching teams with operator allocation under quota and permission policies, usage and topology observability, and environment reuse through library layers and snapshots.

### Operational surface and implementation

| Operational surface | Implementation |
|---|---|
| VM, GPU, vCPU, and storage | Nova VM creation with project quotas, images, networks, and keypairs |
| Kubernetes clusters | cloud-init-based k3s control-plane and worker-node configuration, with state and workload tracking |
| Shared data space | Manila CephFS/NFS shares and snapshots |
| AI/ML libraries | Store squashfs/NFS content-addressable immutable layer chains on Manila shares and compose them with OverlayFS in consumer VMs for reuse |
| Operations | Projects, users, roles, quotas, Grafana, Prometheus, and audit logs |

The browser's SvelteKit application calls the configured FastAPI `/api/v1` API base directly; SvelteKit is the UI/auth shell, not an API relay. The backend talks to OpenStack services through `openstacksdk`, while Redis provides cache and session support. The current architecture source of truth is the [root `ARCHITECTURE.md`](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md); see the [Palimpsest layer documentation](../palimpsest.md) for detailed flows.


---

## Quick Links

| Document | Description |
|---|---|
| [Getting started](deployment.md) | Docker Compose / Kubernetes deployment |
| [k3s cluster](k3s.md) | k3s provisioning and node management |
| [Drover behavior specification](drover-workflow.md) | Planned vs current Drover cluster creation behavior and provisioning workflow |
| [Root architecture](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md) | Current system boundaries, ownership, operational limits, and update rules |
| [Architecture detail](architecture.md) | Documentation-site domain entry point |
| [API reference](../api-reference.md) _(Korean)_ | Complete REST API specification |
| [kolla-ansible deployment](../deployment.md#kolla-ansible-배포) | Single-playbook deployment inside OpenStack |
| [Targeted testing](../testing.md) _(Korean)_ | Guide to choosing fast local feature-test targets |

---

## Highlights

### k3s Cluster Provisioning
Installs k3s directly onto OpenStack VMs to deliver a Kubernetes environment on demand. No complex Magnum setup — master and worker nodes are configured automatically through cloud-init.

### squashfs/NFS Library Layer
Each layer stores a `.sqsh` artifact on its own Manila NFS share. A consumer VM mounts the share read-only and composes the chain with OverlayFS. See the [squashfs layer pipeline](../squashfs-layer-pipeline.md) for the operational implementation.

### Monitoring Integration
Provides Grafana embed support (`GET /api/v1/grafana/dashboards` — returns dashboard UIDs and base URL) and exposes VM targets for Prometheus via http_sd (`GET /api/v1/sd/prometheus/targets`). Monitoring ingress security groups are attached automatically on project and instance creation.

### kolla-ansible Integration
Deploys Afterglow inside an existing OpenStack cluster using a single kolla-ansible playbook (`deploy/kolla/`).

### Complete OpenStack Service Coverage
Nova, Glance, Cinder, Neutron, Manila, Octavia — every core service managed from a single dashboard.

---

## Technology Stack

| Component | Stack |
|---|---|
| Frontend | SvelteKit + TypeScript + Tailwind CSS v4 |
| Backend | FastAPI + openstacksdk (Python) |
| Cache | Redis 7 |
| Deployment | Docker Compose / Kubernetes (Kustomize) / ArgoCD |
| CI/CD | GitHub Actions (multi-platform Docker build) |

---

[GitHub repository](https://github.com/openstack-afterglow/openstack-afterglow){: .btn .btn-primary }

---

## Release Notes

### v1.13.9 (2026-05-01)

#### New Features
- **kolla-ansible integration**: `deploy/kolla/` role and `install.sh` — single-playbook deployment inside OpenStack
- **Union Mount layer v2**: Fork API, seal/unseal, Manila Snapshot backup/restore, background build worker, volume transfer auto-detach/rollback, NFS export security hardening
- **Monitoring integration**: Grafana embed JWT, Prometheus http_sd targets, auto-attach monitoring SG
- **Octavia Ingress**: per-project manager user + App Credential auth model
- **Account settings page** (`/dashboard/account`): profile, password, theme, projects, keypairs
- Floating IP shows connected instance info
- Instance volume `delete_on_termination` toggle
- Volume snapshot per-project filtering

#### Improvements
- Sidebar redesigned — Identity & Access section, topology promoted
- API calls use `Promise.allSettled` for per-call error isolation
- ArgoCD auto-sync: kustomization digest auto-updated after image push

#### Bug Fixes
- Admin libraries ~0.5s infinite re-render loop fixed (`untrack`)
- Admin volumes action buttons condensed into `...` dropdown
- Nova error messages preserved on volume detach failure

---

### v1.13.8 and earlier

See [GitHub Releases](https://github.com/openstack-afterglow/openstack-afterglow/releases).
