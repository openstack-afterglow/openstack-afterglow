## Context

Current managed_flavors owns RuntimeSetting compute.managed_flavors and standard shape reconciliation. compute_pools reads Keystone afterglow_compute_pool metadata but blocks readers/writers on a custom Nova endpoint. Shared dev has concurrent uncommitted work; preserve it and do not deploy.

## Goals / Non-Goals

Goals: stock Nova/Placement only; retained observed inventory until explicit host removal; exact administrator GPU approval and naming; per-GPU-shape domain-wide ACL inheritance; honest Afterglow-only limits.
Non-goals: global atomic domain quota enforcement across direct CLI/other services, custom Nova source changes, direct Placement allocation writes, automatic VM/flavor deletion, production changes.

## Decisions

### Shared policy contract

Add service app.services.flavor_automation_policy backed by RuntimeSetting key compute.flavor_automation_policy, with existing graph lease + SQL revision/readback. Public policy:
- revision: nonnegative integer.
- hosts: array of {id: root provider UUID, name: native compute service host, removed: bool, observed_at: ISO time, cpu: supported VCPU inventory, pcpu: optional supported PCPU inventory, ram: supported inventory, gpu: {resource_class: integer}}. PCPU never derives from VCPU. Keep previous support on down/disabled/missing/shrunk observations. New verified hosts may be discovered automatically; removed entries NEVER reactivate automatically.
- gpu_profiles: array of {name: unique lowercase slug such as 3060lhr or 4090, display_name, enabled, resource_class: primary physical GPU RC, resource_requirements: per-GPU positive integer map, extra_specs: exact per-GPU string map, alias_resource_classes: optional exact alias-to-RC map}. Primary count MUST be1; multiple aliases need explicit mapping. Every physical GPU and companion MUST have native pci_passthrough:alias attachment coverage; Placement quantities alone reserve but do not attach hardware. Reject alias/explicit request overlap. Identical companion aliases may be shared across profiles only when their RC mapping agrees. GPU count scales alias quantities; unrelated specs remain exact. Shared/default profiles fit VCPU, dedicated fits PCPU; mixed/isolated-emulator policies are unsupported rather than guessed. Reject protected ownership annotations, malformed requests and ambiguous alias identities.
- GET /api/v1/admin/flavor-automation/policy returns stored policy without mutation. PUT same path accepts {revision, gpu_profiles} and preserves hosts. POST /api/v1/admin/flavor-automation/discover merges verified standard-API observations. PUT /api/v1/admin/flavor-automation/hosts/{id} accepts {revision, removed:bool}; explicit retirement disables a still-present native nova-compute service and verifies readback before acknowledging exclusion. No force-down, delete or live migration; absent native service may be retired from verified complete directory absence. Re-inclusion does not silently enable native maintenance-disabled services; explain this in UI.
- Async load_policy() returns validated policy for other backend services, no native calls or writes; async capabilities() returns approved alias/classification projection from profiles for compute_pools. Core implementation owner may add helpers, preserving these public fields/interfaces and messaging peers if required.

### Automation and domain policy

Managed flavor status keeps its existing response shape/readiness but checks standard API/persisted policy rather than extension qualification. Host discovery/reconciliation merges observations and consumes all retained nonremoved host inventory. Profiles define gpu.{name}.{count}gpu.{cpu}c.{ramGiB}g naming. CPU defaults remain bounded existing grid. Reuse immutable ownership marker and namespace, create new IDs for changed hardware specs; never mutate old native IDs or existing VMs.

compute_pools uses approved policy capabilities and existing standard native Keystone/Placement reads. Replace native_enforcement response with policy_ready:boolean and control_scope:'afterglow'; do not fabricate native verified bits. API writes preserve fresh caller authorization, graph lease, revision and native metadata readback. Stock native project quota remains independent authoritative protection; Afterglow pool policy does not promise external-call enforcement.

Per shape, include every enabled project in enabled domains with active pool metadata whose GPU resource limit is positive or unlimited and sufficient for that shape (zero/missing denies); all required GPU identities must match. GPU access must not depend on configuring unrelated CPU/RAM limits. Absent CPU/MEMORY_MB limits mean no additional Afterglow domain cap for those resources (native project quotas still apply); explicit zero denies. ACL visibility is authorization, not reservation: temporary pool exhaustion must not withdraw catalog access. Disabled/deleted domains/projects lose access on a complete verified pass; incomplete directory cannot cause destructive ACL withdrawal. New projects gain access on next pass. No optional project cap changes domain flavor visibility, though creation admission can enforce it.

### Existing consumer cutover

Pool evaluation checks Afterglow policy evidence, not global fleet proof. Exact profile mappings classify primary GPU vs explicit companion resources. Preserve quota fail-closed behavior for unknown accounting and native errors; avoid custom extension GETs. User/admin/MCP/K3s/Palimpsest existing consumers continue through shared pool/eligibility helpers. Remove obsolete native integration source package after no production hooks/callers depend on it, retaining historical docs as history; migration never changes existing Keystone metadata or activates automation implicitly.

## Risks / Trade-offs

- Last-observed inventory is catalog authority, NOT live placement availability. Nova decides actual placement; excluded native service is disabled via explicit admin action only.
- GPU alias config is not fully discoverable from stock API. Administrator profile is explicit scheduling intent, not a claim of fresh native config verification; exact standard Placement resources and existing native scheduler enforce actual feasibility.
- Afterglow policy checks are bypassable by authorized external API callers and are not atomic domain-wide allocation enforcement. Do not claim otherwise or auto-rewrite native project quotas.
- Old and new app writers must not share enabled automation during rollout; existing DB setting key/schema remains unchanged and no deployment is performed.
- Process only verified observations; preserve state on outage, unknown native write and partial directories. No unknown mutation replay or destructive cleanup.
