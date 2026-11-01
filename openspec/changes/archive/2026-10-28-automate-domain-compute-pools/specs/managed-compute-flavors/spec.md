## ADDED Requirements

### Requirement: Hardware-supported bounded standard catalog
The system MUST automatically reconcile CPU and GPU flavors from verified same-host supported Nova/Placement resources using bounded standard CPU/RAM and GPU-count combinations. It MUST distinguish supported capacity from transient free capacity.

#### Scenario: Cross-host false fit
- **WHEN** CPU, RAM and requested GPU are only sufficient on different hosts
- **THEN** no managed flavor MUST be published on the assumption that those independent maxima form one usable host

#### Scenario: Temporarily busy supported host
- **WHEN** a supported host becomes fully allocated
- **THEN** stable flavor identity MUST remain and creation eligibility MUST reflect current shortage instead of destructive catalog churn

### Requirement: Verified scheduling metadata
GPU flavors MUST carry validated `pci_passthrough:alias` GPU and required audio aliases. Managed GPU flavors MUST include `afterglow:access_mode=gpu_quota`; CPU flavors MUST include the domain quota marker. These metadata MUST NOT be treated as native quota enforcement.

#### Scenario: Unknown audio association
- **WHEN** no native evidence establishes an alias/audio association
- **THEN** the reconciler MUST report unavailable metadata instead of guessing a schedulable flavor

### Requirement: Ownership-safe publication and lifecycle
Managed IDs MUST be deterministic and ownership-marked. New flavors MUST remain private until specs and native access prerequisites are verified. Automation MUST NOT adopt/delete manual flavors or mutate existing VM shapes. Publication and automatic project access MUST respect enabled domain pools and native enforcement readiness.

#### Scenario: Partial create or missing readback
- **WHEN** creation succeeds but extra specs or native readback fails
- **THEN** the flavor MUST NOT become publicly usable as an incomplete CPU-only or GPU-bypassing flavor

#### Scenario: Concurrent reconciler or disabled automation
- **WHEN** another replica owns the reconcile lease or automation is disabled during a pass
- **THEN** a stale worker MUST NOT publish further flavor or access mutations

### Requirement: Functional console and tutorial parity
Admin domain and manager quota screens MUST expose pool usage/remaining and optional project caps; admin flavor screens MUST expose actual automation status and actions. Tutorial behavior MUST match API semantics, and stale authority/scope responses MUST NOT enable writes.

#### Scenario: Scope changes during edit
- **WHEN** a user changes domain or loses authority during a pending read/write
- **THEN** the old response MUST NOT populate or authorize the new context

### Requirement: Hardware authority and non-destructive withdrawal
GPU/audio classification MUST use verified configured aliases and exhaustive actual compute-host PCI class/BDF/sibling evidence, not the mutable display-name catalog. Unsupported shapes MUST be withdrawn by access/visibility changes, not physical flavor deletion. Manual mutation endpoints MUST serialize ownership checks with automation, including partially staged ownership claims.

#### Scenario: Manual mutation races reconciliation
- **WHEN** a manual specs/access/delete request overlaps a managed or staging claim
- **THEN** the shared graph lease and fresh ownership check MUST prevent manual mutation of the managed shape

#### Scenario: A display catalog does not recognize a verified GPU
- **WHEN** native hardware evidence verifies a GPU whose model name is absent locally
- **THEN** its physical resource class MUST remain the quota identity rather than being misclassified or omitted
