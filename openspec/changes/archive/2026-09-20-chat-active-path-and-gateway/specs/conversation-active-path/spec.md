## ADDED Requirements

### Requirement: Active path is authoritative for normal conversation reads
The system SHALL maintain an indexed root-to-leaf projection for each non-empty conversation and SHALL use that projection for default conversation resume, context preparation, and history reads. The immutable parent-linked message graph SHALL remain available for audit and explicit branch operations.

#### Scenario: Resume selected branch
- **WHEN** a conversation has multiple historical branches and one active leaf
- **THEN** the normal resume path contains only projected ancestors of that active leaf in root-to-leaf order

#### Scenario: Empty conversation
- **WHEN** a conversation has no active leaf
- **THEN** its active-path projection is empty and normal history reads return no messages

### Requirement: Writers update graph and projection atomically
Message append, assistant completion, regeneration, retry, branch switch, fork, and any direct active-leaf mutation SHALL update the historical graph, active leaf, and projection in one MariaDB transaction under the existing run/revision fences.

#### Scenario: Admission conflict rolls back
- **WHEN** durable admission loses its active-leaf fence or finds a nonterminal run
- **THEN** no user message, run, leaf update, or active-path row from that attempt is committed

#### Scenario: Branch switch during active run
- **WHEN** a caller attempts to switch the active branch while a nonterminal run owns the conversation
- **THEN** the system rejects the switch and leaves the graph and projection unchanged

### Requirement: Migration backfills and validates every active path
The migration SHALL create the projection additively, backfill every valid legacy conversation from `active_leaf_id` and `parent_id`, and fail closed on missing nodes, cycles, cross-conversation ancestry, duplicate membership, non-contiguous positions, or a projected leaf that differs from `active_leaf_id`.

#### Scenario: Legacy branched conversation
- **WHEN** migration encounters a valid conversation whose active leaf is on one of several branches
- **THEN** it inserts exactly the selected branch with contiguous zero-based positions and preserves every non-selected message

#### Scenario: Corrupt legacy leaf
- **WHEN** migration cannot reconstruct a valid root-to-leaf chain for a non-null active leaf
- **THEN** migration fails instead of publishing a partial projection

### Requirement: Projection integrity is repairable from immutable history
An operator integrity command or service helper SHALL detect projection drift and SHALL rebuild a conversation only while holding its conversation lock and while no nonterminal run is mutating it.

#### Scenario: Missing projected row
- **WHEN** integrity checking finds a valid historical chain but a missing projection row
- **THEN** repair replaces the complete projection from immutable ancestry and verifies the final leaf before commit
