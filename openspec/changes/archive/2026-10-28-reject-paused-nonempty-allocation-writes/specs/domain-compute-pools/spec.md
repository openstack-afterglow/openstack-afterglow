## MODIFIED Requirements

### Requirement: Paused and uncertain authority remain fail-closed
Only absent pool metadata MUST retain unmanaged behavior. An explicit disabled pool MUST reject every nonempty allocation admission and recheck without treating zero/decreasing snapshot deltas as trustworthy non-growth proof. This includes nonempty migration, resize, heal and revert writes until explicit reactivation; ordinary all-empty native releases MUST remain allowed. Readers MUST distinguish paused/unavailable from zero and expose cap-limited headroom without sibling project identities or project-derived domain forecasts.

#### Scenario: Explicit pause
- **WHEN** a configured pool is disabled
- **THEN** existing VM allocations MUST remain and new native allocations MUST be denied rather than falling back to stale project ceilings

#### Scenario: Paused same-generation recreation below the ceiling
- **WHEN** a stale request appears zero-delta after target deletion and native migration-allocation move recreate the target at the same generation with fewer resources
- **THEN** paused nonempty admission MUST fail closed rather than acknowledging actual growth even when full totals remain below the pool ceiling

#### Scenario: Paused explicit release
- **WHEN** a paused domain sends a valid all-empty native allocation release
- **THEN** the release MUST remain allowed and MUST NOT restore historical allocations
