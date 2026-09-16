# Restore Afterglow GPU quota ownership

## Why

Drover is the K3s/Kubernetes control-plane service. GPU quota policy decides which Nova GPU flavors a project may see and create, so it belongs beside Afterglow's existing Nova vCPU/RAM and Cinder quota authority. The 2026-08 service extraction incorrectly moved `gpu_quotas` into Drover, coupling ordinary VM flavor discovery and admission to the K3s service.

## Decision

Afterglow is the sole authority for GPU quota policy and usage:

- vCPU/RAM/instance quota remains Nova-owned and is surfaced by Afterglow.
- GPU default/project quota, GPU flavor visibility, GPU VM admission, and dashboard availability are Afterglow-owned.
- Drover retains K3s GPU capacity, placement, allocatable-resource, and node scheduling logic, but has no GPU quota database, API, SDK method, or quota admission gate.
- No compatibility proxy or dual writer remains after cutover.

## Cutover

1. Add an immutable, forward-only Afterglow migration that recreates `gpu_quotas`; never edit or replay the already-applied `074_drop_drover_tables.sql`.
2. Provide an audited, maintenance-window-only Drover-to-Afterglow import. It preserves ID/project/default (`__default__`)/limit/timestamps, rejects invalid values and canonical alias collisions, refuses divergent destination rows, and verifies exact row values before release.
3. Quiesce quota writes and GPU admissions, run the import, verify it, roll all Afterglow API/worker instances to the local authority, then drain old instances.
4. Release the Drover removal only after all Afterglow callers are local. Drover applies a new forward migration to drop its former table and removes quota endpoints, service/model, SDK methods, quota-only Stampede gate/tests/docs. K3s GPU capacity and scheduling remain.

## Scope

This Afterglow checkout implements the local schema/service/callers/tests/import tooling. The checked-out sibling `../drover` implements the Drover API/SDK/schema removal. The frontend stable `/api/v1/admin/gpu-quotas/*` contract remains unchanged.

## Acceptance

- No Afterglow GPU quota decision, flavor filtering, dashboard quota view, or admin GPU quota CRUD calls Drover.
- Afterglow local quota decisions are fail-closed on its own DB failure, preserve project-over-default and `-1` unlimited semantics, and correctly count Nova GPU flavor aliases.
- An audited import prevents silent data loss or canonical alias collisions.
- Drover exposes no GPU quota routes/state after the ordered cutover, while K3s GPU scheduling/allocatable checks still work.
- vCPU/RAM/instance quota paths remain Nova/Afterglow paths and are unchanged.
