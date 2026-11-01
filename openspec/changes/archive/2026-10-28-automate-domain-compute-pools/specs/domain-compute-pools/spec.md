## ADDED Requirements

### Requirement: Domain shared consumption cap
The system MUST enforce one native domain shared CPU, memory and GPU-model usage cap for enabled pools, including direct Nova API callers. CPU MUST account for VCPU and PCPU. It MUST fail closed if domain/project membership, usage completeness or native integration prerequisites cannot be verified.

#### Scenario: Two projects share remaining capacity
- **WHEN** two projects in one domain concurrently request the last available GPU or CPU capacity through direct Nova calls
- **THEN** accepted allocated usage MUST NOT exceed the domain cap after native allocation rechecks

#### Scenario: Native create bypass attempt
- **WHEN** a caller bypasses Afterglow and uses a manual/public flavor in Nova
- **THEN** the same enabled domain pool MUST constrain actual resource usage regardless of flavor ownership/access_mode metadata

### Requirement: Optional project caps and exact authority
A domain manager for the exact domain or a fresh system-scope administrator MAY set a project cap no greater than the pool limit. Project caps MUST NOT reserve capacity or be summed as allocations. Unset caps MUST share the pool.

#### Scenario: Unauthorized or cross-domain change
- **WHEN** a project administrator or manager of another domain submits a project cap
- **THEN** the write MUST be denied without native policy mutation

#### Scenario: Project cap is lower than shared headroom
- **WHEN** a project has an explicit cap below available domain headroom
- **THEN** both project cap and shared domain cap MUST be enforced

### Requirement: Explicit safe transition and observable native status
Enabling a pool MUST require explicit policy configuration and validated native prerequisites. Legacy project GPU policy or aggregate native project limits MUST NOT silently become a domain consumption cap. Enabled policy metadata alone MUST NOT be reported as verified native enforcement.

#### Scenario: Unsupported native accounting
- **WHEN** native PCI accounting or version-compatible enforcement is missing
- **THEN** activation/publication MUST be rejected or explicitly unavailable, never reported as native enforced

#### Scenario: Resource reallocation
- **WHEN** resize, unshelve, restore, migration, revert or rescheduling allocates resources
- **THEN** the native pool MUST cover the relevant allocations without double charging a settled allocation as a new independent VM or allowing a bypass

### Requirement: Paused and uncertain authority remain fail-closed
Only absent pool metadata MUST retain unmanaged behavior. An explicit disabled pool MUST block new compute allocations without replacing actual consumption with legacy project limits. Readers MUST distinguish paused/unavailable from zero and expose cap-limited headroom without sibling project identities or project-derived domain forecasts.

#### Scenario: Explicit pause
- **WHEN** a configured pool is disabled
- **THEN** existing VM allocations MUST remain and new native allocations MUST be denied rather than falling back to stale project ceilings

### Requirement: Consumer-incarnation-safe failure handling
Every nonempty allocation write MUST have a complete postcheck even when its apparent delta is zero. A failed uncertain existing-consumer write MUST NOT restore a nonempty historical snapshot. Safe new-consumer claims MAY be cleared with generation/shape fences; all-empty releases MUST NOT be resurrected after an observation failure.

#### Scenario: Same-generation consumer recreation
- **WHEN** a consumer is deleted/recreated between a snapshot and write with the same apparent generation
- **THEN** an over-pool write MUST NOT be acknowledged as successful and unrelated consumers MUST be preserved

### Requirement: Confirmed project deletion and stale-cap recovery
Project deletion MUST preflight cap cleanup under the shared graph lease and remove policy entries only after confirmed native deletion. Recovery of an externally deleted project cap MUST require exact native absence, complete directory absence and zero raw Placement usage.

#### Scenario: A deleted project still consumes resources
- **WHEN** a stale cap references an absent project but raw Placement usage remains
- **THEN** cap recovery MUST be denied and the management view MUST expose the unresolved state without relaxing admission
