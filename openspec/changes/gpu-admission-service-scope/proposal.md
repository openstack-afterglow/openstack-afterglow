## Why

Drover's internal GPU admission must evaluate the requested project's native flavor access and GPU usage without authenticating Afterglow's service password in that tenant project. Authentication scope and resource ownership are separate contracts; a successful administrator flavor lookup alone does not prove that a private flavor is shared to the requested project.

## What Changes

- Bind admission authentication only to the existing DB resource policy `openstack.service_project` through `resource_policy_store.get_service_project_connection()`. Do not add service-user tenant memberships or fall back to an admin project/environment setting.
- Check native public/private flavor visibility for the explicit request project; fetch empty extra specs explicitly, and fail closed on access/metadata errors (including metadata 404).
- Require an explicit `project_id` in `gpu_inventory.require_gpu_quota` and migrate its production/test callers. Preserve target-project Nova usage filtering and server ownership checks when authenticated outside that project.
- Preserve existing alias classification/normalization, Afterglow DB default-plus-project quota authority, absent/zero denial and unlimited `-1`, HTTP contract and native Drover provisioning ownership. Do not change quotas, reservations, schema, capacity or memberships.
- Author boundary and quota-usage regressions, and update the existing architecture, Korean/English API reference, testing guide and Unreleased changelog without a version bump.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Internal K3s GPU admission authentication and explicit requested-project flavor visibility/quota usage.

## Impact

Source authority: [`internal_k3s.py`](../../../backend/app/api/internal_k3s.py) (`_get_project_flavor`, `k3s_gpu_admission`), [`resource_policy_store.py`](../../../backend/app/services/resource_policy_store.py) (`get_service_project_connection`), [`gpu_inventory.py`](../../../backend/app/services/gpu_inventory.py) (`require_gpu_quota`), and [`gpu_quota.py`](../../../backend/app/services/gpu_quota.py) (`get_effective_gpu_quotas`, `_get_project_gpu_usage`, `check_gpu_quota`). The existing DB policy is reused, not a new configuration or authentication convention. Ordinary instance admission continues to use its own authenticated caller connection with an explicit target project.

Baseline is `9cbfecad419b7d6c64e3a21b06a0cd80b1f44f93` (`v1.30.12` peeled commit); canonical manifests prepare patch `1.30.13`. Focused64, K3s16/9, instances548/209 and final `test:gate` passed (backend4431/frontend2569/contract174/functional35, Ruff check/format). Working architecture stamp and staged check passed. Candidate ASGI using real DB/Keystone/Nova returned200/`gpu_required=true` and auth401/malformed400/schema422; independent tenant visibility/zero servers and clean SDK/DB teardown were verified. Artifact qualification, rollout and deployed native HTTP acceptance remain pending; do not archive as verified.

The post-gates, post-rollout [protected native smoke](../../../docs/testing.md#gpu-admission-service-scope-2026-10-12) uses flavor `fe5a5a4c-a568-481d-982b-469967f64808`, shared to project `test`. Candidate and independent tenant checks have confirmed visibility/specs, real unlimited `RTX3060LHR` quota and zero usage; repeat the final deployed acceptance against the running source. Use protected operator/tenant/host tools only; never expose credentials/raw exceptions, fabricate headroom or change quotas, memberships, flavor sharing, capacity or cloud resources for the smoke.

Target acceptance requires actual HTTP 200 with `gpu_required=true` for that exact test-project/flavor pair. A legitimate 409 proves quota fail-closed behavior but does not pass target acceptance; report insufficient real headroom as a blocker without changing quota, capacity, membership or sharing, and without a substitute flavor. Preserve the parent's already observed pre-fix 503 as reproduction evidence; do not rerun it simply to confirm the reported failure.
