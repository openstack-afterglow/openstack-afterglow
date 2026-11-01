## MODIFIED Requirements

### Requirement: Consumer-incarnation-safe failure handling
Every nonempty allocation write MUST have a complete postcheck even when its apparent delta is zero. A failed uncertain consumer write MUST NOT restore a historical snapshot or clear a nonempty allocation without an independent incarnation/serialization guarantee. Matching generation, shape and owner, including an initially empty snapshot, MUST NOT constitute that guarantee. Already empty claims MAY be resolved without a native write; all-empty native releases MUST NOT be resurrected after an observation failure. Uncertain reservations MUST be reported by exact consumer ID for reconciliation, even when raw reserved usage temporarily exceeds the cap.

#### Scenario: Same-generation consumer recreation
- **WHEN** a consumer is deleted/recreated between a snapshot and write with the same apparent generation
- **THEN** an over-pool write MUST NOT be acknowledged as successful and unrelated consumers MUST be preserved

#### Scenario: Initially empty consumer replaced after commit
- **WHEN** a successful claim is deleted and independently recreated with the same UUID, shape, owner and generation before an old allocation/scheduler failure handler runs
- **THEN** the replacement MUST remain intact and the old operation MUST fail with the exact unresolved consumer ID rather than clearing it
