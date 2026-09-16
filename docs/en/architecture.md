---
title: Architecture
parent: English
lang: en
nav_order: 4
---

# Afterglow Architecture Detail

The source of truth for this page is the root [`ARCHITECTURE.md`](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md). The root document describes the current `dev` checkout: Afterglow's dashboard and FastAPI gateway/BFF ownership, OpenStack boundaries, authentication/session model, VM SSE/rollback flow, extracted-service boundaries, deployment, and security limits.

This page remains a documentation-site entry point for domain detail. When this page or an older plan disagrees with the current source, read the root document and source first.

## Detailed documents

- [API reference](../api-reference.md): `/api/v1` routes and legacy VM callback contracts
- [Security model](../security.md): authentication, authorization, owner checks, encryption, and known limits
- [Drover behavior specification](drover-workflow.md): planned versus current SSE/callback phases
- [Palimpsest](../palimpsest.md) and [squashfs layer pipeline](../squashfs-layer-pipeline.md): retained layer domain
- [Deployment](deployment.md): Compose, Kubernetes, ArgoCD, and kolla-ansible prerequisites

When code, configuration, schema, dependency, deployment, or tests change, review the affected domain detail and the root architecture in the same change. After reviewing source, run these commands from the repository root:

```bash
python3 scripts/check_architecture.py --stamp --summary "Reviewed paths and structural impact"
python3 scripts/check_architecture.py --staged
```

This page is not a copy of the root snapshot. Read historical Union plans as historical material, separately from the current Palimpsest boundary.
