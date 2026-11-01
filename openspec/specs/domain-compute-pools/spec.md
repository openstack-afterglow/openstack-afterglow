# domain-compute-pools

## Purpose

Evaluate Afterglow-controlled domain-shared CPU, memory and approved GPU-model consumption with optional project ceilings using stock APIs, while preserving native project quotas and explicitly excluding global direct-Nova enforcement.
## Requirements
### Requirement: Domain shared consumption cap
Afterglow MUST evaluate domain-shared CPU, memory and approved GPU-model consumption for its own controlled admission paths using standard Keystone and Placement APIs. CPU MUST account for VCPU plus PCPU. It MUST fail closed on unknown membership or incomplete accounting. It MUST NOT claim global atomic quota enforcement for direct Nova or other-service calls. Stock Nova project quotas and scheduler remain native authorities.

#### Scenario: Direct Nova caller
- **WHEN** an authorized caller bypasses Afterglow
- **THEN** stock native policies MUST remain authoritative and Afterglow MUST NOT claim its domain policy intercepted that request

### Requirement: Optional project caps and exact authority
A domain manager for the exact domain or a fresh system-scope administrator MAY set a project cap no greater than the pool limit. Project caps MUST NOT reserve capacity or be summed as allocations. Unset caps MUST share the pool.

#### Scenario: Unauthorized or cross-domain change
- **WHEN** a project administrator or manager of another domain submits a project cap
- **THEN** the write MUST be denied without native policy mutation

#### Scenario: Project cap is lower than shared headroom
- **WHEN** a project has an explicit cap below available domain headroom
- **THEN** both project cap and shared domain cap MUST be enforced

### Requirement: Explicit safe transition and observable native status
Enabling a pool MUST require explicit policy configuration and standard API/accounting prerequisites. GPU identities MUST come from approved administrator profiles. Responses MUST identify control_scope as afterglow and expose policy readiness without a custom Nova extension or native-global-enforcement claim.

#### Scenario: Stock Nova extension API absent
- **WHEN** stock Nova lacks os-domain-compute capabilities but standard APIs and approved policy are available
- **THEN** Afterglow policy and flavor automation MUST remain usable without patching Nova

### Requirement: Paused and uncertain authority remain fail-closed
Only absent pool metadata MUST retain unmanaged behavior. An explicit disabled pool MUST reject Afterglow-controlled nonempty admission without changing running VM allocations. Readers MUST distinguish paused/unavailable from zero and expose cap-limited headroom without disclosing sibling identities to consumers.

#### Scenario: Explicit pause
- **WHEN** a configured pool is disabled
- **THEN** Afterglow MUST deny new controlled admission and preserve existing allocations without claiming external Nova requests are intercepted

### Requirement: Confirmed project deletion and stale-cap recovery
Project deletion MUST preflight cap cleanup under the shared graph lease and remove policy entries only after confirmed native deletion. Recovery of an externally deleted project cap MUST require exact native absence, complete directory absence and zero raw Placement usage.

#### Scenario: A deleted project still consumes resources
- **WHEN** a stale cap references an absent project but raw Placement usage remains
- **THEN** cap recovery MUST be denied and the management view MUST expose the unresolved state without relaxing admission

### Requirement: Independent native project quota administration
Afterglow MUST allow explicitly authorized native CPU/RAM project quota updates, native allocation-budget policy and future-project defaults independently of domain pool metadata or pool readiness. A pool cap MUST NOT substitute for native Nova quota. Native budget/usage/reservation, exact authority, revision, readback and unknown-operation guards MUST remain. No automatic quota expansion is permitted.

#### Scenario: GPU-only domain blocked by native quota
- **WHEN** a domain allows an approved GPU flavor but the target native project CPU/RAM quota is insufficient
- **THEN** the flavor MUST remain blocked until an authorized native quota adjustment succeeds, after which fresh eligibility MUST allow it if all other conditions permit, without changing pool metadata or GPU access

#### Scenario: Future native defaults in an active GPU pool
- **WHEN** CPU/RAM defaults are configured and a disabled project is created in an active GPU-only pool domain
- **THEN** native CPU/RAM defaults MUST be applied and read back before project enable, not stripped because pool metadata exists

#### Scenario: Paused or unavailable pool observation
- **WHEN** native quota data and caller authority are verified but the pool is paused or its independent UI lookup fails
- **THEN** explicit native quota correction MUST remain available without relaxing pool admission or bypassing native allocation-budget checks

