## ADDED Requirements

### Requirement: Evidence-bound re-adoption of orphaned wanted flavors
The reconciler SHALL record a durable claim for an existing native flavor without a local claim only when the flavor ID equals a current wanted shape ID, the flavor is private, its name is an accepted immutable name of that shape, and its description is exactly `afterglow:domain-compute-v1:` followed by a 48-hex token; the recorded token SHALL be that native token. Marked flavors outside the wanted set SHALL NOT receive claims and SHALL remain retained without ACL or visibility changes. Manual CPU flavors carrying an ownership marker without a claim SHALL be reported as retained with control state `foreign_marker`, SHALL NOT be adopted or mutated, and SHALL NOT make the run status unavailable.

#### Scenario: Orphaned standard flavor
- **WHEN** a standard shape's native flavor carries exact ownership evidence but the state has no claim
- **THEN** the claim is recorded from the native token and the normal spec/ACL drift checks continue

#### Scenario: Unsupported marked flavor
- **WHEN** a marked managed flavor is outside the wanted set and unclaimed
- **THEN** it is reported retained and no tenant access is revoked
