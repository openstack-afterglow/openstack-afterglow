## ADDED Requirements

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
