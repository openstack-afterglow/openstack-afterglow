## MODIFIED Requirements

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
Managed IDs MUST be deterministic and ownership-marked. New flavors MUST remain private until immutable shape/spec readback succeeds. Automation MUST NOT adopt/delete manual flavors or mutate existing VM shapes. Each GPU shape MUST be accessible to every enabled project in enabled active domains whose GPU allocation permits that shape, independent of temporary usage or project opt-in. No custom Nova extension MUST be required.

#### Scenario: Per-domain model access and newly created project
- **WHEN** one domain allows 4090 and another allows only 3060lhr, and a new project is added to the first domain
- **THEN** complete reconciliation MUST grant the new project the permitted 4090 shapes without granting either domain the other's GPU model

#### Scenario: Readback or directory failure
- **WHEN** shape/spec readback or complete identity directory cannot be verified
- **THEN** automation MUST NOT publish incomplete flavors or revoke ACLs based on partial evidence

### Requirement: Hardware authority and non-destructive withdrawal
Scheduling templates MUST use explicit administrator approval joined to standard Nova/Placement inventory, never model-name guessing. Unsupported owned shapes MUST be withdrawn without native flavor deletion only after explicit host/profile/policy changes. Existing ownership and graph-lease guards MUST remain.

#### Scenario: Profile hardware specification changes
- **WHEN** an approved profile's hardware extra specs change
- **THEN** a new deterministic shape identity MUST be created and existing VM flavor identity MUST remain untouched
