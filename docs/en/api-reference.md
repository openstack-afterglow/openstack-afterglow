---
title: API Reference
parent: English
lang: en
nav_order: 3
has_children: true
---

# Afterglow API Reference

The Afterglow backend is a REST API implemented with FastAPI, serving as a single gateway that communicates with every OpenStack service.
This page is an API domain index. Each domain document describes, per endpoint, the **input parameters, parameter dependencies, limitations,
output schema, usage examples, and error responses**.

> Some domain pages are currently available in Korean only; those links point to the Korean documentation.

---

## API Versioning Rule

All routers are **mounted solely under `/api/v1`** (transition completed on 2026-06-18). Every path in this documentation is based on `/api/v1/...`.

As an exception, only the **three legacy endpoints** that are baked into cloud-init and whose paths cannot be changed without redeploying existing VMs are dual-mounted on both `/api` and `/api/v1`.

| Endpoint | Purpose |
|-----------|------|
| `POST /api/k3s/callback` | k3s server VM → backend kubeconfig/node_token callback |
| `POST /api/instances/{id}/health/report` | VM health agent report |
| `POST /api/instances/{id}/credentials/rotate-cephx` | VM cephx credential rotation |

> Adding new legacy `/api` paths is prohibited. Except for the three above, only `/api/v1` is valid for all paths.

---

## Authentication Headers

Every endpoint that requires authentication must include the following headers.

| Header | Description |
|------|------|
| `Authorization` | `Bearer <access_token>` — access JWT from the `POST /api/v1/auth/login` response |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

`POST /api/v1/auth/login`, `GET /api/v1/health`, and `GET /api/v1/metrics` do not require authentication.
Prometheus SD (`/api/v1/sd/...`) and the baked paths for VM agents use a separate Bearer token (see each document).

> **Optional services**: Some domains are mounted only when enabled in the `[services]` section (or the relevant section)
> of `afterglow.conf`. Refer to the "optional" marking in the tables below.

---

## API Domain Index

### Authentication & Users

| Document | Base Path | Description |
|------|-----------|------|
| [Auth](api/auth.md) | `/api/v1/auth` | Keystone token issuance/renewal, session management, project scope switching |
| [Profile](../api/profile.md) | `/api/v1/profile` | User profile view/edit, password change, activity log |
| [Projects & Invitations](../api/projects.md) | `/api/v1/projects`, `/api/v1/invitations` | Project self-service, member/manager/invitation management |

### Admin

| Document | Base Path | Description |
|------|-----------|------|
| [Admin](../api/admin.md) | `/api/v1/admin` | Cluster overview, users/projects/quotas/groups/roles, Flavor·GPU·images, migration, orphaned resources, worker runtime, etc. (all endpoints `require_admin`) |

### Compute

| Document | Base Path | Description |
|------|-----------|------|
| [Instances](api/instances.md) | `/api/v1/instances` | VM creation/query/control/deletion, OverlayFS creation (SSE), volumes·interfaces·security groups·FIP·metrics |
| [Instance Health](../api/instance-health.md) | `/api/v1/instances` | VM health agent report/query, cephx credential rotation (baked paths) |
| [Images](../api/images.md) | `/api/v1/images` | Glance image catalog, upload, property/member management |
| [Flavors](../api/flavors.md) | `/api/v1/flavors` | Nova flavor list |
| [Keypairs](../api/keypairs.md) | `/api/v1/keypairs` | SSH keypair creation/deletion |

### Storage

| Document | Base Path | Description |
|------|-----------|------|
| [Volumes](api/volumes.md) | `/api/v1/volumes`, `/api/v1/volume-snapshots` | Cinder volumes, backups, snapshots, transfers, auto backup |
| [File Storage](api/file-storage.md) | `/api/v1/file-storage` | Manila CephFS shares, access rules — *optional* |
| [Share Snapshots·Networks (Share Mgmt)](../api/share-management.md) | `/api/v1/share-snapshots`, `/api/v1/share-networks`, `/api/v1/security-services` | Manila snapshots/networks/security services — *optional* |

### Network

| Document | Base Path | Description |
|------|-----------|------|
| [Networks](api/networks.md) | `/api/v1/networks` | Neutron networks, subnets, Floating IP, topology |
| [Routers](api/routers.md) | `/api/v1/routers` | Neutron routers, interfaces, gateways |
| [Load Balancers](api/loadbalancers.md) | `/api/v1/loadbalancers` | Octavia LB, listeners, pools, members, health monitors |
| [Security Groups](api/security-groups.md) | `/api/v1/security-groups` | Neutron security groups, rule management |

### Union Layers

| Document | Base Path | Description |
|------|-----------|------|
| [Palimpsest layers](api/union.md) | `/api/v1/palimpsest`, `/api/v1/admin/libraries`, `/api/v1/libraries/squashfs` | Layered VM — squashfs layer build/consume, digest search, parent chain. (The old `/api/v1/union` surface was removed.) |

### Containers · Kubernetes

| Document | Base Path | Description |
|------|-----------|------|
| [Containers](../api/containers.md) | `/api/v1/clusters`, `/api/v1/containers` | Magnum clusters, Zun containers — *optional* |
| [k3s Clusters (k3s)](api/k3s.md) | `/api/v1/k3s/clusters` | Lightweight Kubernetes provisioning (SSE), scale, kubeconfig, certificates, nodegroups — *optional* |
| [k3s Resource Management](api/k3s-resources.md) | `/api/v1/k3s/clusters/...` | In-cluster k8s resources (pods/deployments/services/configmaps/secrets/shell) — *optional* |

### Data · Keys · Add-on Services

| Document | Base Path | Description |
|------|-----------|------|
| [Database (Trove)](../api/database.md) | `/api/v1/database-instances` | Trove DBaaS instances, databases/users, backups — *optional* |
| [Object Storage (Swift)](../api/object-storage.md) | `/api/v1/object-storage` | Swift containers/objects, upload, download tokens, trash — *optional* |
| [Key Management (Barbican)](../api/secrets.md) | `/api/v1/secrets`, `/api/v1/secret-containers`, `/api/v1/secret-orders` | Barbican secrets/containers/orders, ACLs, quotas — *optional* |
| [VPN (VPNaaS)](../api/vpn.md) | `/api/v1/vpn/servers` | VPN servers/clients, config download, agent callback — *optional* |

### Dashboard · System

| Document | Base Path | Description |
|------|-----------|------|
| [Dashboard](../api/dashboard.md) | `/api/v1/dashboard`, `/api/v1/libraries` | Project resource summary, quotas, library catalog |
| [System Services](../api/system-services.md) | `/api/v1/announcements`, `/api/v1/tutorials`, `/api/v1/sd`, `/api/v1/grafana`, `/api/v1/site-config`, `/api/v1/user-dashboard` | Announcements, tutorials, Prometheus SD, Grafana embed, site config, personal dashboard |
| [Chat](../api/chat.md) | `/api/v1/chat` | Lumen AI API proxy & SSE streaming (BFF) — *optional* |
| [Metrics](../api/metrics.md) | `/api/v1/metrics`, `/api/v1/health` | Prometheus metrics, health check (no authentication required) |

---

## Architecture Documentation

The current system boundaries, ownership, runtime, and authoritative data stores are documented in the [root `ARCHITECTURE.md`](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md). This site's [architecture detail](architecture.md) is a domain entry point, not a copy of the root snapshot. See the [class and workflow diagrams](../class-diagrams/) for module relationships.
