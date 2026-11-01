## MODIFIED Requirements

### Requirement: Domain shared consumption cap
Afterglow MUST evaluate domain-shared CPU, memory and approved GPU-model consumption for its own controlled admission paths using standard Keystone and Placement APIs. CPU MUST account for VCPU plus PCPU. It MUST fail closed on unknown membership or incomplete accounting. It MUST NOT claim global atomic quota enforcement for direct Nova or other-service calls. Stock Nova project quotas and scheduler remain native authorities.

#### Scenario: Direct Nova caller
- **WHEN** an authorized caller bypasses Afterglow
- **THEN** stock native policies MUST remain authoritative and Afterglow MUST NOT claim its domain policy intercepted that request

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

## REMOVED Requirements

### Requirement: Consumer-incarnation-safe failure handling
**Reason**: Afterglow MUST NOT patch native Placement writers or manage native scheduler rollback as part of API-only flavor control.
**Migration**: Leave actual allocation writes and native failure recovery to stock Nova/Placement. Preserve unknown outcomes and never delete or rewrite native allocations from Afterglow reconciliation.
