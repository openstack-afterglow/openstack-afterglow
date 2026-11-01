# managed-compute-flavors

## Purpose

Reconcile retained-host standard CPU/GPU shapes using explicit administrator-approved PCI attachment templates, domain-model project access, immutable ownership and stock Nova/Placement APIs without native source patches.
## Requirements
### Requirement: Hardware-supported bounded standard catalog
The system MUST reconcile bounded standard CPU/RAM/GPU flavors from retained included same-host supported Nova/Placement inventory, independently of transient free capacity. Only explicit administrator host removal MAY remove a host's support contribution. Shared CPU MUST fit VCPU and dedicated CPU MUST fit separately retained PCPU inventory; one class MUST NOT imply the other.

#### Scenario: Cross-host false fit
- **WHEN** CPU, RAM and GPU fit only on different hosts
- **THEN** automation MUST NOT synthesize a combined shape

#### Scenario: Temporarily busy or disconnected host
- **WHEN** a supported host is allocated, down, disconnected or absent from discovery
- **THEN** retained host support and stable flavor identity MUST remain until explicit host retirement while runtime creation availability remains separate

#### Scenario: Dedicated GPU on a PCPU-only host
- **WHEN** a host provides PCPU but no VCPU and an approved GPU profile requires dedicated CPU
- **THEN** automation MUST generate only shapes fitting that PCPU support and MUST NOT invent shared VCPU capacity

### Requirement: Verified scheduling metadata
GPU flavors MUST use enabled administrator-approved profiles for exact naming, resource requirements and extra specs. GPU and approved companion request counts MUST scale with GPU count. These annotations MUST NOT be described as native domain quota enforcement.

#### Scenario: Unapproved GPU
- **WHEN** a new GPU is observed without a saved enabled profile
- **THEN** no automatic GPU flavor MUST be generated

### Requirement: Ownership-safe publication and lifecycle
Managed generated IDs MUST be deterministic and ownership-marked. New generated flavors MUST remain private until immutable shape/spec readback succeeds. Automation MUST automatically include verified CPU-only manual flavors under their existing IDs without deleting or replacing them or mutating existing VM shapes. Such inclusion MUST use durable per-ID ownership and complete native readback, preserve native hardware specifications and descriptions, and reconcile private access only for positively identified domain-policy projects. Public Nova flavors MUST remain public and direct Nova requests MUST NOT be represented as subject to Afterglow admission. GPU or otherwise unverified manual flavors MUST NOT be adopted. Each GPU shape MUST be accessible to every enabled project in enabled active domains whose GPU allocation permits that shape, independent of temporary usage or project opt-in. No custom Nova extension MUST be required.

#### Scenario: Per-domain model access and newly created project
- **WHEN** one domain allows 4090 and another allows only 3060lhr, and a new project is added to the first domain
- **THEN** complete reconciliation MUST grant the new project the permitted 4090 shapes without granting either domain the other's GPU model

#### Scenario: Readback or directory failure
- **WHEN** shape/spec readback or complete identity directory cannot be verified
- **THEN** automation MUST NOT publish incomplete flavors or revoke ACLs based on partial evidence

#### Scenario: Existing CPU flavor included
- **WHEN** a complete native observation proves an existing manual flavor is CPU-only and the operator has enabled automation
- **THEN** automation MUST preserve its native ID, name, description and hardware specifications while establishing a durable ownership claim and reconciling positively identified private project access; existing VM references MUST NOT change

#### Scenario: Unknown or ambiguous manual hardware
- **WHEN** a manual flavor requests unverified PCI, GPU or other accelerator resources, or its native specifications or ownership cannot be verified
- **THEN** automation MUST NOT treat it as CPU-only, rewrite its scheduling metadata or revoke access based on incomplete evidence

#### Scenario: Public manual CPU flavor
- **WHEN** an existing verified CPU flavor is public in Nova
- **THEN** Afterglow MUST preserve native public visibility and identify that authorized direct Nova requests bypass Afterglow admission

#### Scenario: Existing Nova CPU name
- **WHEN** an existing CPU flavor has a noncanonical immutable native name
- **THEN** Afterglow MUST retain that name and ID for native operations and MAY display the canonical `cpu.{vcpus}c_{ramGiB}g` separately when complete CPU evidence is available

### Requirement: Functional console and tutorial parity
Admin domain and manager quota screens MUST expose pool usage/remaining and optional project caps; admin flavor screens MUST expose actual automation status and actions. Tutorial behavior MUST match API semantics, and stale authority/scope responses MUST NOT enable writes.

#### Scenario: Scope changes during edit
- **WHEN** a user changes domain or loses authority during a pending read/write
- **THEN** the old response MUST NOT populate or authorize the new context

### Requirement: Hardware authority and non-destructive withdrawal
Scheduling templates MUST use explicit administrator approval joined to standard Nova/Placement inventory, never model-name guessing. Unsupported owned shapes MUST be withdrawn without native flavor deletion only after explicit host/profile/policy changes. Existing ownership and graph-lease guards MUST remain.

#### Scenario: Profile hardware specification changes
- **WHEN** an approved profile's hardware extra specs change
- **THEN** a new deterministic shape identity MUST be created and existing VM flavor identity MUST remain untouched

